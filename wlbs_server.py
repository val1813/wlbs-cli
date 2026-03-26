#!/usr/bin/env python3
"""
wlbs-scan experience hub server (V3-aligned).

Default deployment:
    uvicorn wlbs_server:app --host 0.0.0.0 --port 8765 --workers 2

This server is intended to own only wlbs-scan data.
Do not point it at unrelated application databases.
"""
from __future__ import annotations

import json
import os
import random
import secrets
import smtplib
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

# ── Email config ───────────────────────────────────────────────
SMTP_HOST = os.environ.get("WLBS_SMTP_HOST", "smtp.mxhichina.com")
SMTP_PORT = int(os.environ.get("WLBS_SMTP_PORT", "465"))
SMTP_USER = os.environ.get("WLBS_SMTP_USER", "hello@kaiwucl.com")
SMTP_PASS = os.environ.get("WLBS_SMTP_PASS", "LYlNHG7kY9RuFWQD")
SMTP_FROM = os.environ.get("WLBS_SMTP_FROM", "hello@kaiwucl.com")

# ── Verification code store (in-memory, TTL 10min) ─────────────
_VERIFY_CODES: dict[str, tuple[str, float]] = {}  # email -> (code, expire_ts)
_VERIFY_TTL = 600


DATA_DIR = Path(os.environ.get("WLBS_DATA_DIR", str(Path.home() / ".wlbs" / "server")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
CRYSTALS_PATH = DATA_DIR / "shared_crystals.jsonl"
TRACES_PATH = DATA_DIR / "raw_traces.jsonl"
KEYS_PATH = DATA_DIR / "api_keys.json"
POINTS_PATH = DATA_DIR / "points.json"

PORT = int(os.environ.get("WLBS_PORT", "8765"))
RATE_LIMITS: dict[str, list[float]] = {}

app = FastAPI(title="wlbs Experience Hub", version="0.6.2")


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_keys() -> dict:
    return _load_json(KEYS_PATH, {})


def _save_keys(keys: dict) -> None:
    _save_json(KEYS_PATH, keys)


def _load_points() -> dict:
    return _load_json(POINTS_PATH, {})


def _save_points(points: dict) -> None:
    _save_json(POINTS_PATH, points)


def _verify_key(api_key: str) -> dict | None:
    if not api_key:
        return None
    return _load_keys().get(api_key)


def _get_tier(api_key: str) -> str:
    info = _verify_key(api_key)
    if not info:
        return "none"
    first_used = info.get("first_used_at")
    if first_used:
        elapsed_days = (time.time() - float(first_used)) / 86400
        if elapsed_days > 30:
            return "expired"
    return info.get("plan", "free")


def _mark_first_use(api_key: str) -> None:
    keys = _load_keys()
    if api_key in keys and not keys[api_key].get("first_used_at"):
        keys[api_key]["first_used_at"] = time.time()
        _save_keys(keys)


def add_key(user: str, plan: str = "pro") -> str:
    keys = _load_keys()
    key = f"wlbs_{plan[:3]}_{secrets.token_hex(8)}"
    keys[key] = {
        "user": user,
        "plan": plan,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "first_used_at": None,
    }
    _save_keys(keys)
    return key


def _add_points(api_key: str, amount: float) -> None:
    points = _load_points()
    points[api_key] = round(points.get(api_key, 0.0) + amount, 3)
    _save_points(points)


def _get_points(api_key: str) -> float:
    return _load_points().get(api_key, 0.0)


def _calculate_points(trace: dict, tier: str) -> float:
    outcome = trace.get("outcome", "failure")
    confidence = float(trace.get("confidence_score", 0))
    if tier == "pro":
        base_success = 0.5
        bonus_success = 0.3
        failure_score = 0.1
    else:
        base_success = 0.3
        bonus_success = 0.1
        failure_score = 0.05
    points = 0.0
    if outcome == "success":
        points += base_success
        if confidence >= 0.8:
            points += bonus_success
    elif outcome in {"failure", "partial"}:
        points += failure_score
    return round(points, 3)


def _validate_trace(trace: dict) -> tuple[bool, str]:
    turns = int(trace.get("turns_used", 0))
    outcome = trace.get("outcome", "")
    traj = trace.get("trajectory", [])
    if not (1 <= turns <= 15):
        return False, f"turns_used={turns} invalid"
    if outcome not in {"success", "failure", "partial"}:
        return False, "invalid outcome"
    if not traj:
        return False, "empty trajectory"
    return True, "ok"


def _distill_on_server(trace: dict) -> dict | None:
    outcome = trace.get("outcome", "failure")
    fp = trace.get("fingerprint", {})
    turns = int(trace.get("turns_used", 0))
    if outcome == "success":
        rule = (
            f"{fp.get('task_type', 'bug_fix')} ({fp.get('language', 'python')}): "
            f"resolved in {turns} turns."
        )
    else:
        rule = (
            f"{fp.get('task_type', 'bug_fix')} ({fp.get('language', 'python')}): "
            f"{trace.get('failure_type', 'failure')} not resolved in {turns} turns."
        )
    confidence = round(0.5 + (0.3 if outcome == "success" else 0.0) + (0.2 if turns <= 5 else 0.0), 2)
    return {
        "rule": rule,
        "rule_type": "positive" if outcome == "success" else "negative",
        "outcome": outcome,
        "task_type": fp.get("task_type", ""),
        "language": fp.get("language", ""),
        "complexity_signals": fp.get("complexity_signals", []),
        "turns_used": turns,
        "confidence": confidence,
        "confidence_score": confidence,
        "contributed_at": datetime.now(timezone.utc).isoformat(),
    }


def _rate_limit(bucket: str, limit: int, window_seconds: int = 3600) -> None:
    now = time.time()
    history = RATE_LIMITS.get(bucket, [])
    history = [ts for ts in history if now - ts < window_seconds]
    if len(history) >= limit:
        raise HTTPException(429, f"rate limit exceeded for {bucket}")
    history.append(now)
    RATE_LIMITS[bucket] = history


class TraceUpload(BaseModel):
    trajectory: list[dict]
    outcome: str
    failure_type: str = ""
    turns_used: int
    final_passed: int = 0
    final_failed: int = 0
    fingerprint: dict = {}
    confidence_score: float = 0.0


@app.get("/health")
def health():
    total = 0
    if CRYSTALS_PATH.exists():
        total = sum(1 for line in CRYSTALS_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
    return {"status": "ok", "total_crystals": total, "port": PORT}


@app.post("/traces/upload")
async def upload_trace(request: Request, x_api_key: Optional[str] = Header(None)):
    info = _verify_key(x_api_key or "")
    if not info:
        raise HTTPException(401, "Invalid API key")
    _rate_limit(f"trace:{x_api_key}", limit=60)
    _mark_first_use(x_api_key)
    tier = _get_tier(x_api_key)
    trace = await request.json()
    valid, reason = _validate_trace(trace)
    if not valid:
        return {"accepted": False, "reason": reason}
    with TRACES_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    crystal = _distill_on_server(trace)
    if crystal:
        with CRYSTALS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(crystal, ensure_ascii=False) + "\n")
        trace["confidence_score"] = crystal.get("confidence", 0)
    points = _calculate_points(trace, tier)
    _add_points(x_api_key, points)
    return {"accepted": True, "rule_generated": crystal is not None, "points_earned": points}


@app.post("/snapshot/upload")
async def upload_snapshot(request: Request, x_api_key: Optional[str] = Header(None)):
    info = _verify_key(x_api_key or "")
    if not info:
        raise HTTPException(401, "Invalid API key")
    body = await request.json()
    record = {
        "project_name": body.get("project_name", ""),
        "project_hash": body.get("project_hash", ""),
        "node_count": len(body.get("world_lines", {})),
        "world_lines": body.get("world_lines", {}),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    snapshots_path = DATA_DIR / "snapshots.jsonl"
    with snapshots_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"ok": True, "snapshot_id": secrets.token_hex(4), "node_count": record["node_count"]}


@app.get("/snapshot/pull")
def pull_snapshots(since: float = 0.0, limit: int = 50, x_api_key: Optional[str] = Header(None)):
    info = _verify_key(x_api_key or "")
    if not info:
        raise HTTPException(401, "Invalid API key")
    _rate_limit(f"snapshot:{x_api_key}", limit=30)
    snapshots_path = DATA_DIR / "snapshots.jsonl"
    if not snapshots_path.exists():
        return {"items": [], "count": 0}
    items = []
    for line in snapshots_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if since:
                ts = datetime.fromisoformat(record.get("uploaded_at", "1970-01-01T00:00:00+00:00")).timestamp()
                if ts < since:
                    continue
            items.append(record)
        except Exception:
            continue
    items = items[-limit:]
    return {"items": items, "count": len(items)}


@app.get("/crystals/download")
def download_crystals(x_api_key: Optional[str] = Header(None)):
    tier = _get_tier(x_api_key or "")
    if tier == "none":
        raise HTTPException(401, "Pro subscription required for shared experience library")
    if tier == "expired":
        raise HTTPException(403, "Key expired")
    _rate_limit(f"crystals:{x_api_key}", limit=30)
    _mark_first_use(x_api_key)
    if not CRYSTALS_PATH.exists():
        return {"crystals": [], "total": 0}
    lines = [line for line in CRYSTALS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    crystals = [json.loads(line) for line in lines[-200:]]
    return {"crystals": crystals, "total": len(lines)}


@app.get("/account/status")
def account_status(x_api_key: Optional[str] = Header(None)):
    info = _verify_key(x_api_key or "")
    if not info:
        raise HTTPException(401, "Invalid API key")
    _mark_first_use(x_api_key)
    tier = _get_tier(x_api_key)
    points = _get_points(x_api_key)
    first_used = info.get("first_used_at")
    expires_at = None
    if first_used:
        expires_ts = float(first_used) + 30 * 86400
        expires_at = datetime.fromtimestamp(expires_ts, tz=timezone.utc).isoformat()
    return {
        "tier": tier,
        "points": round(points, 1),
        "points_needed": 100,
        "key_expires_at": expires_at,
        "resets_at": "December 31",
    }


@app.post("/account/redeem")
async def redeem(request: Request, x_api_key: Optional[str] = Header(None)):
    info = _verify_key(x_api_key or "")
    if not info:
        raise HTTPException(401, "Invalid API key")
    body = await request.json()
    email = str(body.get("email", "")).strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email required")
    points = _get_points(x_api_key)
    if points < 100:
        return {"success": False, "message": f"Need 100 points, you have {points:.1f}"}
    pts = _load_points()
    pts[x_api_key] = round(pts.get(x_api_key, 0.0) - 100, 3)
    _save_points(pts)
    new_key = add_key(email, plan="pro")
    return {
        "success": True,
        "message": f"Key generated for {email}.",
        "new_key": new_key,
    }


@app.get("/stats")
def stats():
    keys = _load_keys()
    points = _load_points()
    crystals = 0
    if CRYSTALS_PATH.exists():
        crystals = sum(1 for line in CRYSTALS_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
    return {
        "active_keys": len(keys),
        "points_accounts": len(points),
        "shared_crystals": crystals,
        "version": "0.6.2",
    }


# ── Email sender ──────────────────────────────────────────────

def _send_email(to: str, subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_FROM, [to], msg.as_string())


# ── Auth: send verification code ──────────────────────────────

@app.post("/api/auth/send-code")
async def send_code(request: Request):
    body = await request.json()
    email = str(body.get("email", "")).strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email required")
    _rate_limit(f"send-code:{email}", limit=5, window_seconds=3600)
    code = str(random.randint(100000, 999999))
    _VERIFY_CODES[email] = (code, time.time() + _VERIFY_TTL)
    try:
        _send_email(
            email,
            "Your wlbs-scan verification code",
            f"Your verification code is: {code}\n\nValid for 10 minutes.\n\n-- wlbs-scan team"
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to send email: {e}")
    return {"sent": True, "email": email}


# ── Auth: verify code → auto-create free key ──────────────────

@app.post("/api/auth/verify")
async def verify_code(request: Request):
    body = await request.json()
    email = str(body.get("email", "")).strip().lower()
    code = str(body.get("code", "")).strip()
    if not email or not code:
        raise HTTPException(400, "Email and code required")
    entry = _VERIFY_CODES.get(email)
    if not entry:
        raise HTTPException(400, "No code found for this email. Request a new one.")
    stored_code, expire_ts = entry
    if time.time() > expire_ts:
        _VERIFY_CODES.pop(email, None)
        raise HTTPException(400, "Code expired. Request a new one.")
    if code != stored_code:
        raise HTTPException(400, "Invalid code.")
    _VERIFY_CODES.pop(email, None)
    # Check if already has a key — return highest-tier non-expired key
    keys = _load_keys()
    matches = [(k, info) for k, info in keys.items() if info.get("email", "").lower() == email]
    if matches:
        # Prefer pro over free, then non-expired over expired
        tier_order = {"pro": 2, "free": 1}
        def _key_score(item):
            k, info = item
            tier = info.get("plan", "free")
            expired = _get_tier(k) == "expired"
            return (0 if expired else 1, tier_order.get(tier, 0))
        best_k, best_info = max(matches, key=_key_score)
        _mark_first_use(best_k)
        return {"key": best_k, "email": email, "plan": best_info.get("plan", "free"), "existing": True}
    # Create new free key
    key = add_key(email, plan="free")
    _mark_first_use(key)
    return {"key": key, "email": email, "plan": "free", "existing": False}


ADMIN_TOKEN = os.environ.get("WLBS_ADMIN_TOKEN", "")


@app.post("/admin/genkey")
async def admin_genkey(request: Request):
    """Admin endpoint to generate API keys. Requires WLBS_ADMIN_TOKEN header."""
    if not ADMIN_TOKEN:
        raise HTTPException(403, "Admin token not configured on server")
    auth = request.headers.get("x-admin-token", "")
    if auth != ADMIN_TOKEN:
        raise HTTPException(403, "Invalid admin token")
    body = await request.json()
    email = str(body.get("email", "")).strip()
    plan = str(body.get("plan", "pro")).strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email required")
    if plan not in ("free", "pro"):
        plan = "pro"
    key = add_key(email, plan)
    return {"key": key, "email": email, "plan": plan}


def _check_admin(request: Request):
    if not ADMIN_TOKEN:
        raise HTTPException(403, "Admin token not configured")
    auth = request.headers.get("x-admin-token", "") or request.query_params.get("token", "")
    if auth != ADMIN_TOKEN:
        raise HTTPException(403, "Invalid admin token")


@app.get("/admin/users")
def admin_users(request: Request):
    _check_admin(request)
    keys = _load_keys()
    points = _load_points()
    users = []
    for k, info in keys.items():
        tier = _get_tier(k)
        first_used = info.get("first_used_at")
        expires_at = None
        if first_used:
            expires_ts = float(first_used) + 30 * 86400
            expires_at = datetime.fromtimestamp(expires_ts, tz=timezone.utc).isoformat()
        users.append({
            "key": k,
            "email": info.get("email", ""),
            "plan": info.get("plan", "free"),
            "tier": tier,
            "points": round(points.get(k, 0.0), 1),
            "created_at": info.get("created_at", ""),
            "first_used_at": first_used,
            "expires_at": expires_at,
        })
    users.sort(key=lambda u: str(u.get("created_at") or ""), reverse=True)
    return {"users": users, "total": len(users)}


@app.delete("/admin/key/{key}")
def admin_delete_key(key: str, request: Request):
    _check_admin(request)
    keys = _load_keys()
    if key not in keys:
        raise HTTPException(404, "Key not found")
    del keys[key]
    _save_keys(keys)
    pts = _load_points()
    pts.pop(key, None)
    _save_points(pts)
    return {"deleted": key}


@app.post("/admin/setpoints")
async def admin_set_points(request: Request):
    _check_admin(request)
    body = await request.json()
    key = str(body.get("key", "")).strip()
    pts_val = float(body.get("points", 0))
    keys = _load_keys()
    if key not in keys:
        raise HTTPException(404, "Key not found")
    pts = _load_points()
    pts[key] = round(pts_val, 1)
    _save_points(pts)
    return {"key": key, "points": pts[key]}


@app.get("/admin/crystals")
def admin_crystals(request: Request, limit: int = 50, offset: int = 0):
    _check_admin(request)
    crystals = []
    if CRYSTALS_PATH.exists():
        lines = [l for l in CRYSTALS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        total = len(lines)
        for line in reversed(lines[max(0, total-offset-limit):total-offset] if offset < total else []):
            try:
                crystals.append(json.loads(line))
            except Exception:
                pass
    else:
        total = 0
    return {"crystals": crystals, "total": total}


# ── Admin HTML dashboard ───────────────────────────────────────

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>wlbs-scan 管理后台</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh}
.topbar{background:#1a1d2e;border-bottom:1px solid #2d3148;padding:14px 28px;display:flex;align-items:center;justify-content:space-between}
.logo{font-size:18px;font-weight:700;color:#7c6aff;letter-spacing:.5px}span.ver{font-size:12px;color:#666;margin-left:8px}
.nav{display:flex;gap:4px}
.nav button{background:none;border:none;color:#94a3b8;padding:7px 14px;border-radius:6px;cursor:pointer;font-size:13px;transition:.15s}
.nav button.active,.nav button:hover{background:#2d3148;color:#e2e8f0}
.main{padding:28px}
.stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:28px}
.stat{background:#1a1d2e;border:1px solid #2d3148;border-radius:10px;padding:20px}
.stat .num{font-size:32px;font-weight:700;color:#7c6aff}
.stat .lbl{font-size:12px;color:#64748b;margin-top:4px}
.card{background:#1a1d2e;border:1px solid #2d3148;border-radius:10px;padding:20px;margin-bottom:20px}
.card h3{font-size:14px;font-weight:600;color:#94a3b8;margin-bottom:16px;text-transform:uppercase;letter-spacing:.5px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:8px 12px;color:#64748b;border-bottom:1px solid #2d3148;font-weight:500}
td{padding:9px 12px;border-bottom:1px solid #1e2235;vertical-align:middle}
tr:hover td{background:#1e2235}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600}
.badge.pro{background:#2d1f6e;color:#a78bfa}
.badge.free{background:#1a2e1a;color:#4ade80}
.badge.expired{background:#2e1a1a;color:#f87171}
.btn{padding:5px 12px;border-radius:6px;border:none;cursor:pointer;font-size:12px;font-weight:600;transition:.15s}
.btn-red{background:#2e1a1a;color:#f87171}.btn-red:hover{background:#f87171;color:#fff}
.btn-blue{background:#1a1f2e;color:#60a5fa}.btn-blue:hover{background:#60a5fa;color:#fff}
.btn-green{background:#1a2e1a;color:#4ade80}.btn-green:hover{background:#4ade80;color:#000}
input,select{background:#0f1117;border:1px solid #2d3148;color:#e2e8f0;padding:8px 12px;border-radius:6px;font-size:13px;outline:none}
input:focus,select:focus{border-color:#7c6aff}
.form-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:16px}
.msg{padding:10px 16px;border-radius:6px;font-size:13px;margin-top:12px;display:none}
.msg.ok{background:#1a2e1a;color:#4ade80;display:block}
.msg.err{background:#2e1a1a;color:#f87171;display:block}
.tab{display:none}.tab.active{display:block}
.key-mono{font-family:monospace;font-size:11px;color:#94a3b8}
.trunc{max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#login{display:flex;align-items:center;justify-content:center;min-height:100vh;background:#0f1117}
.login-box{background:#1a1d2e;border:1px solid #2d3148;border-radius:14px;padding:40px;width:360px;text-align:center}
.login-box h2{color:#7c6aff;margin-bottom:24px;font-size:20px}
.login-box input{width:100%;margin-bottom:14px}
.login-box .btn-login{width:100%;padding:10px;background:#7c6aff;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer}
.login-box .btn-login:hover{background:#6d58f0}
</style>
</head>
<body>
<div id="login">
  <div class="login-box">
    <h2>wlbs-scan 管理后台</h2>
    <input type="password" id="tokenInput" placeholder="Admin Token" onkeydown="if(event.key==='Enter')doLogin()">
    <button class="btn-login" onclick="doLogin()">登录</button>
    <div id="loginErr" class="msg err" style="display:none"></div>
  </div>
</div>

<div id="app" style="display:none">
  <div class="topbar">
    <div><span class="logo">wlbs-scan</span><span class="ver">管理后台</span></div>
    <div class="nav">
      <button class="active" onclick="showTab('users',this)">用户 & Keys</button>
      <button onclick="showTab('crystals',this)">经验库</button>
      <button onclick="showTab('genkey',this)">生成 Key</button>
    </div>
  </div>
  <div class="main">
    <div class="stats-row" id="statsRow"></div>

    <!-- Users tab -->
    <div class="tab active" id="tab-users">
      <div class="card">
        <h3>用户 & Key 列表</h3>
        <div class="form-row"><input id="searchUser" placeholder="搜索邮箱或 key..." oninput="filterUsers()" style="width:280px"><button class="btn btn-blue" onclick="loadUsers()">刷新</button></div>
        <table><thead><tr><th>邮箱</th><th>Plan</th><th>状态</th><th>积分</th><th>Key</th><th>创建时间</th><th>操作</th></tr></thead>
        <tbody id="usersBody"></tbody></table>
      </div>
    </div>

    <!-- Crystals tab -->
    <div class="tab" id="tab-crystals">
      <div class="card">
        <h3>经验库（共享晶体）</h3>
        <button class="btn btn-blue" onclick="loadCrystals()" style="margin-bottom:14px">刷新</button>
        <table><thead><tr><th>规则</th><th>类型</th><th>任务类型</th><th>语言</th><th>置信度</th><th>轮次</th><th>贡献时间</th></tr></thead>
        <tbody id="crystalsBody"></tbody></table>
      </div>
    </div>

    <!-- GenKey tab -->
    <div class="tab" id="tab-genkey">
      <div class="card">
        <h3>生成新 Key</h3>
        <div class="form-row">
          <input id="newEmail" placeholder="用户邮箱" style="width:220px">
          <select id="newPlan"><option value="pro">Pro</option><option value="free">Free</option></select>
          <button class="btn btn-green" onclick="genKey()">生成</button>
        </div>
        <div id="genkeyResult" class="msg"></div>
      </div>
    </div>
  </div>
</div>

<script>
let TOKEN = '';
let allUsers = [];

function doLogin(){
  TOKEN = document.getElementById('tokenInput').value.trim();
  fetch('/admin/users?token='+encodeURIComponent(TOKEN))
    .then(r=>{ if(!r.ok) throw new Error('invalid'); return r.json(); })
    .then(()=>{ document.getElementById('login').style.display='none'; document.getElementById('app').style.display='block'; loadAll(); })
    .catch(()=>{ let e=document.getElementById('loginErr'); e.textContent='Token 错误'; e.style.display='block'; });
}

function loadAll(){ loadStats(); loadUsers(); }

function loadStats(){
  fetch('/stats').then(r=>r.json()).then(d=>{
    document.getElementById('statsRow').innerHTML=
      `<div class="stat"><div class="num">${d.active_keys}</div><div class="lbl">活跃 Keys</div></div>`+
      `<div class="stat"><div class="num">${d.shared_crystals}</div><div class="lbl">经验晶体</div></div>`+
      `<div class="stat"><div class="num">${d.points_accounts}</div><div class="lbl">积分账户</div></div>`+
      `<div class="stat"><div class="num">0.6.0</div><div class="lbl">版本</div></div>`;
  });
}

function loadUsers(){
  fetch('/admin/users?token='+encodeURIComponent(TOKEN))
    .then(r=>r.json()).then(d=>{ allUsers=d.users; renderUsers(allUsers); });
}

function filterUsers(){
  const q=document.getElementById('searchUser').value.toLowerCase();
  renderUsers(allUsers.filter(u=>u.email.toLowerCase().includes(q)||u.key.toLowerCase().includes(q)));
}

function renderUsers(users){
  const tbody=document.getElementById('usersBody');
  if(!users.length){tbody.innerHTML='<tr><td colspan=7 style="color:#666;text-align:center;padding:24px">暂无用户</td></tr>';return;}
  tbody.innerHTML=users.map(u=>{
    const badge=u.tier==='pro'?'pro':u.tier==='expired'?'expired':'free';
    const pts=u.points||0;
    const created=u.created_at?new Date(u.created_at*1000).toLocaleDateString('zh-CN'):'-';
    return `<tr>
      <td class="trunc" title="${u.email}">${u.email}</td>
      <td><span class="badge ${badge}">${u.tier}</span></td>
      <td><span class="badge ${badge}">${u.plan}</span></td>
      <td>${pts}</td>
      <td class="key-mono trunc" title="${u.key}">${u.key}</td>
      <td>${created}</td>
      <td>
        <button class="btn btn-blue" style="margin-right:4px" onclick="editPoints('${u.key}',${pts})">积分</button>
        <button class="btn btn-red" onclick="deleteKey('${u.key}','${u.email}')">删除</button>
      </td>
    </tr>`;
  }).join('');
}

function deleteKey(key,email){
  if(!confirm('确认删除 '+email+' 的 key？')) return;
  fetch('/admin/key/'+encodeURIComponent(key)+'?token='+encodeURIComponent(TOKEN),{method:'DELETE'})
    .then(r=>r.json()).then(()=>loadUsers());
}

function editPoints(key,cur){
  const v=prompt('设置积分（当前：'+cur+'）',cur);
  if(v===null||v==='') return;
  fetch('/admin/setpoints?token='+encodeURIComponent(TOKEN),{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({key,points:parseFloat(v)})
  }).then(r=>r.json()).then(()=>loadUsers());
}

function loadCrystals(){
  fetch('/admin/crystals?token='+encodeURIComponent(TOKEN)+'&limit=100')
    .then(r=>r.json()).then(d=>{
      const tbody=document.getElementById('crystalsBody');
      if(!d.crystals.length){tbody.innerHTML='<tr><td colspan=7 style="color:#666;text-align:center;padding:24px">暂无经验</td></tr>';return;}
      tbody.innerHTML=d.crystals.map(c=>{
        const badge=c.rule_type==='positive'?'free':'expired';
        const ts=c.contributed_at?c.contributed_at.slice(0,16).replace('T',' '):'-';
        return `<tr>
          <td style="max-width:280px;word-break:break-word">${c.rule||'-'}</td>
          <td><span class="badge ${badge}">${c.rule_type||'-'}</span></td>
          <td>${c.task_type||'-'}</td>
          <td>${c.language||'-'}</td>
          <td>${c.confidence||'-'}</td>
          <td>${c.turns_used||'-'}</td>
          <td>${ts}</td>
        </tr>`;
      }).join('');
    });
}

function genKey(){
  const email=document.getElementById('newEmail').value.trim();
  const plan=document.getElementById('newPlan').value;
  const res=document.getElementById('genkeyResult');
  if(!email){res.className='msg err';res.textContent='请输入邮箱';return;}
  fetch('/admin/genkey?token='+encodeURIComponent(TOKEN),{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({email,plan})
  }).then(r=>r.json()).then(d=>{
    res.className='msg ok';
    res.textContent='Key: '+d.key;
    loadUsers();
  }).catch(()=>{res.className='msg err';res.textContent='生成失败';});
}

function showTab(name,btn){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.nav button').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  btn.classList.add('active');
  if(name==='crystals') loadCrystals();
}
</script>
</body>
</html>
"""


@app.get("/admin")
def admin_dashboard():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=ADMIN_HTML)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
