"""wlbs-scan cloud client — stdlib only, zero extra dependencies.

Credentials stored in ~/.wlbs/config.json
Hub server default: http://111.231.112.127:8765
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

CLOUD_URL = os.environ.get("WLBS_CLOUD_URL", "http://111.231.112.127:8765")
CONFIG_PATH = Path.home() / ".wlbs" / "config.json"
_TIMEOUT = 15


# ── Config helpers ─────────────────────────────────────────────

def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def get_token() -> Optional[str]:
    return _load_config().get("token")


def get_api_key() -> Optional[str]:
    # env var takes priority over stored config
    return os.environ.get("WLBS_API_KEY") or _load_config().get("api_key")


def get_email() -> Optional[str]:
    return _load_config().get("email")


# ── HTTP helpers ───────────────────────────────────────────────

def _request(method: str, path: str, body: Optional[dict] = None,
             token: Optional[str] = None, api_key: Optional[str] = None) -> dict:
    url = CLOUD_URL.rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if api_key:
        headers["x-api-key"] = api_key
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_bytes = e.read()
        try:
            detail = json.loads(body_bytes).get("detail", body_bytes.decode("utf-8", errors="replace"))
        except Exception:
            detail = body_bytes.decode("utf-8", errors="replace")
        raise CloudError(e.code, detail)
    except urllib.error.URLError as e:
        raise CloudError(0, f"network error: {e.reason}")


def _get(path: str, params: Optional[dict] = None,
         token: Optional[str] = None, api_key: Optional[str] = None) -> dict:
    if params:
        path = path + "?" + urllib.parse.urlencode(params)
    return _request("GET", path, token=token, api_key=api_key)


def _post(path: str, body: dict,
          token: Optional[str] = None, api_key: Optional[str] = None) -> dict:
    return _request("POST", path, body=body, token=token, api_key=api_key)


class CloudError(Exception):
    def __init__(self, code: int, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"[{code}] {detail}")


# ── Auth flows ─────────────────────────────────────────────────

def cmd_send_code(email: str) -> dict:
    """Request email verification code."""
    return _post("/api/auth/send-code", {"email": email})


def cmd_register(email: str, password: str, code: str) -> dict:
    """Register with email + password + verification code."""
    result = _post("/api/auth/register", {
        "email": email,
        "password": password,
        "code": code,
    })
    # auto-login after register
    cfg = _load_config()
    cfg["email"] = email
    _save_config(cfg)
    return result


def cmd_login(email: str, password: str) -> dict:
    """Login and persist token."""
    result = _post("/api/auth/login", {"email": email, "password": password})
    token = result.get("token") or result.get("access_token", "")
    cfg = _load_config()
    cfg["email"] = email
    cfg["token"] = token
    cfg["tier"] = result.get("tier", "free")
    _save_config(cfg)
    return result


def cmd_whoami() -> dict:
    """Return current user info."""
    token = get_token()
    if not token:
        raise CloudError(0, "not logged in — run: wlbs-scan . --login")
    return _get("/api/auth/me", token=token)


# ── API key management ─────────────────────────────────────────

def cmd_keygen(note: str = "") -> dict:
    """Generate a wlbs API key (requires login)."""
    token = get_token()
    if not token:
        raise CloudError(0, "not logged in — run: wlbs-scan . --login")
    result = _post("/api/wlbs/keygen", {"note": note}, token=token)
    key = result.get("key", "")
    if key:
        cfg = _load_config()
        cfg["api_key"] = key
        _save_config(cfg)
    return result


def cmd_set_api_key(key: str) -> None:
    """Manually set a wlbs API key in local config."""
    cfg = _load_config()
    cfg["api_key"] = key
    _save_config(cfg)


# ── Sync ───────────────────────────────────────────────────────

def cmd_sync(store_path: Path, project_name: str = "", pull: bool = True) -> dict:
    """Upload local world-lines and optionally pull community data."""
    api_key = get_api_key()
    if not api_key:
        raise CloudError(0, "no API key — run: wlbs-scan . --keygen  or  --set-api-key KEY")

    # Load local world_lines.json
    wlbs_dir = store_path / ".wlbs"
    wl_file = wlbs_dir / "world_lines.json"
    world_lines: dict = {}
    if wl_file.exists():
        try:
            data = json.loads(wl_file.read_text(encoding="utf-8"))
            world_lines = data.get("world_lines", {})
        except Exception:
            pass

    # compute project hash
    import hashlib
    h = hashlib.md5(str(store_path).encode()).hexdigest()[:16]
    pname = project_name or store_path.name

    upload_result = _post("/snapshot/upload", {
        "project_name": pname,
        "project_hash": h,
        "world_lines": world_lines,
    }, api_key=api_key)

    pull_result: dict = {}
    if pull:
        # Get last sync time
        cfg = _load_config()
        since = cfg.get("last_sync", 0.0)
        pull_result = _get("/snapshot/pull",
                           params={"since": since, "limit": 50},
                           api_key=api_key)
        # Merge community world-lines into local store
        items = pull_result.get("items", [])
        if items and wl_file.exists():
            _merge_community_snapshots(wl_file, items)
        # Update last sync time
        import time
        cfg["last_sync"] = time.time()
        _save_config(cfg)

    return {"upload": upload_result, "pull": pull_result}


def _merge_community_snapshots(wl_file: Path, items: list) -> None:
    """Merge pulled community world-lines: only add failure/fix events for new nodes."""
    try:
        local = json.loads(wl_file.read_text(encoding="utf-8"))
    except Exception:
        return
    local_wl = local.get("world_lines", {})
    merged = 0
    for snap in items:
        for node_id, wl_data in snap.get("world_lines", {}).items():
            if node_id not in local_wl:
                # new node from community — add with community tag
                events = wl_data.get("events", [])
                # tag events as community
                for ev in events:
                    ev["community"] = True
                local_wl[node_id] = {"events": events}
                merged += 1
    if merged > 0:
        local["world_lines"] = local_wl
        wl_file.write_text(json.dumps(local, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_cloud_stats() -> dict:
    """Get cloud stats (public endpoint)."""
    return _get("/stats", api_key=get_api_key())


def cmd_account_status(api_key: Optional[str] = None, hub_url: Optional[str] = None) -> dict:
    """Query account status for points / tier / expiry."""
    key = api_key or get_api_key()
    if not key:
        raise CloudError(0, "no API key configured")
    global CLOUD_URL
    old = CLOUD_URL
    if hub_url:
        CLOUD_URL = hub_url
    try:
        return _get("/account/status", api_key=key)
    finally:
        CLOUD_URL = old


def cmd_redeem(email: str, api_key: Optional[str] = None, hub_url: Optional[str] = None) -> dict:
    key = api_key or get_api_key()
    if not key:
        raise CloudError(0, "no API key configured")
    global CLOUD_URL
    old = CLOUD_URL
    if hub_url:
        CLOUD_URL = hub_url
    try:
        return _post("/account/redeem", {"email": email}, api_key=key)
    finally:
        CLOUD_URL = old


def cmd_upload_trace(trace: dict, api_key: Optional[str] = None, hub_url: Optional[str] = None) -> dict:
    key = api_key or get_api_key()
    if not key:
        raise CloudError(0, "no API key configured")
    global CLOUD_URL
    old = CLOUD_URL
    if hub_url:
        CLOUD_URL = hub_url
    try:
        return _post("/traces/upload", trace, api_key=key)
    finally:
        CLOUD_URL = old


def cmd_download_crystals(api_key: Optional[str] = None, hub_url: Optional[str] = None) -> dict:
    key = api_key or get_api_key()
    if not key:
        raise CloudError(0, "no API key configured")
    global CLOUD_URL
    old = CLOUD_URL
    if hub_url:
        CLOUD_URL = hub_url
    try:
        return _get("/crystals/download", api_key=key)
    finally:
        CLOUD_URL = old


def auto_upload_task_outcome(task_record: dict, api_key: Optional[str] = None, hub_url: Optional[str] = None) -> dict | None:
    """Best-effort upload of a distilled task trajectory for Pro users.

    The payload is intentionally small and detached from repository-local paths.
    """
    trace = {
        "trajectory": [
            {
                "turn": 1,
                "expert": "route",
                "file_type": task_record.get("final_target", ""),
                "success": task_record.get("result") == "pass",
                "passed": task_record.get("tests_after", {}).get("pass", 0),
                "failed": task_record.get("tests_after", {}).get("fail", 0),
            }
        ],
        "outcome": "success" if task_record.get("result") == "pass" else "failure",
        "failure_type": task_record.get("detail", "")[:120],
        "turns_used": 1,
        "final_passed": task_record.get("tests_after", {}).get("pass", 0),
        "final_failed": task_record.get("tests_after", {}).get("fail", 0),
        "fingerprint": {
            "task_type": "repair_route",
            "language": "python",
            "complexity_level": "medium",
            "complexity_signals": task_record.get("symptom_feature_vector", []),
        },
        "confidence_score": 0.9 if task_record.get("result") == "pass" else 0.5,
    }
    try:
        return cmd_upload_trace(trace, api_key=api_key, hub_url=hub_url)
    except Exception:
        return None


# ── Interactive register/login prompts ─────────────────────────

def interactive_register() -> None:
    print("wlbs-scan cloud registration")
    print("=============================")
    email = input("Email: ").strip()
    if not email:
        print("Cancelled."); return
    print(f"Sending verification code to {email}...")
    try:
        cmd_send_code(email)
        print("Code sent. Check your inbox.")
    except CloudError as e:
        print(f"Failed to send code: {e.detail}"); return
    code = input("Verification code: ").strip()
    if not code:
        print("Cancelled."); return
    import getpass
    pw = getpass.getpass("Password (min 8 chars): ")
    if len(pw) < 8:
        print("Password too short."); return
    try:
        cmd_register(email, pw, code)
        print(f"Registered successfully as {email}")
        print("Logging in...")
        cmd_login(email, pw)
        print("Logged in. Generating API key...")
        result = cmd_keygen(note="auto")
        print(f"API key: {result.get('key', '')}")
        print(f"Saved to {CONFIG_PATH}")
    except CloudError as e:
        print(f"Error: {e.detail}")


def interactive_login() -> None:
    print("wlbs-scan cloud login")
    print("=====================")
    email = input("Email: ").strip()
    if not email:
        print("Cancelled."); return
    import getpass
    pw = getpass.getpass("Password: ")
    try:
        result = cmd_login(email, pw)
        tier = result.get("tier", "free")
        print(f"Logged in as {email} (tier: {tier})")
        print(f"Credentials saved to {CONFIG_PATH}")
    except CloudError as e:
        print(f"Login failed: {e.detail}")
