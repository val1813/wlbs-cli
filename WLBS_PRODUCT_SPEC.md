# wlbs-scan 产品改造任务书
## 工程师执行版 · 2026-03-26

**改造目标：**
把 wlbs-scan 从一个开发者工具，改造成一个有完整商业闭环的产品：
- 免费版：安装即用，快速识别代码错误
- Pro版：API接入，共享经验库，越用越强

**改造原则：**
- `wlbs_scan.py` 核心逻辑**一行不动**
- 所有新功能以新增文件/新增参数的方式叠加
- 不引入复杂依赖，保持零依赖原则（新增的 server 除外）

---

## 任务一：`--advise` 命令（advisory JSON输出）

### 要做什么
现有的 `--suggest` 是给人看的彩色终端输出，语气是命令式。
新增 `--advise` 命令，输出标准 JSON，语气是建议式，专门给 agent/脚本消费。

### 为什么
CC/Codex/Cursor 用户通过 Rules 文件让模型自动调 wlbs-scan，
模型需要能 parse 的 JSON，不是终端彩色文本。

### 怎么实现

**第一步：在 `main()` 的 argparse 里加参数**

在 `wlbs_scan.py` 的 `main()` 函数里，找到 `p.add_argument("--suggest"...)` 这行，
在它后面加：

```python
p.add_argument("--advise", metavar="NODE",
               help="Output advisory JSON for agent consumption (suggestion tone, not directive)")
p.add_argument("--min-confidence", type=float, default=0.0, metavar="FLOAT",
               help="Only output suggestions with confidence >= this value (use with --advise)")
```

**第二步：在 `scan()` 函数里加处理逻辑**

在 `scan()` 函数里，找到 `if args.suggest:` 这个分支，
在它**之前**加：

```python
if args.advise:
    node = args.advise
    if node not in graph.nodes:
        print(json.dumps({"error": f"unknown node: {node}"}))
        return
    suggestion = build_repair_suggestion(graph, store, node)
    target = suggestion["recommended_target"]
    target_node = graph.nodes[target]
    focus_node = graph.nodes[node]

    # 计算置信度
    confidence = min(0.99, round(
        0.4 * target_node.curvature +
        0.3 * (1.0 if any("singularity" in r for r in suggestion["reasoning_chain"]) else 0.0) +
        0.2 * min(focus_node.failure_count / 5, 1.0) +
        0.1 * (1.0 if target != node else 0.0),
        2
    ))

    if confidence < args.min_confidence:
        print(json.dumps({"advisory": None, "reason": "below min_confidence threshold"}))
        return

    # 备选建议（symptom节点本身，如果target!=focus）
    alternatives = []
    if target != node and focus_node.failure_count > 0:
        alternatives.append({
            "text": f"{node} itself may also have direct defects worth checking",
            "confidence": round(min(0.99, focus_node.curvature * 0.8), 2),
            "tone": "note",
            "reasoning": [f"{node} has {focus_node.failure_count} direct failure event(s)"]
        })

    # 开放问题（让模型知道wlbs也有不确定的地方）
    open_questions = []
    if target_node.git_change_count > 5:
        open_questions.append(f"Has {target} been modified recently? (git changes: {target_node.git_change_count})")
    if focus_node.failure_count == 1:
        open_questions.append("Is this a one-off failure or a recurring pattern?")
    if not open_questions:
        open_questions.append(f"Is the failure pattern consistent across multiple test runs?")

    payload = {
        "schema": "wlbs-advisory-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symptom": node,
        "advisory": {
            "primary_suggestion": {
                "text": f"{target} may be worth investigating first",
                "confidence": confidence,
                "tone": "suggestion",
                "reasoning": suggestion["reasoning_chain"],
            },
            "alternative_suggestions": alternatives,
            "what_to_read_first": [target] + ([node] if target != node else []),
            "action_chain": suggestion["action_chain"],
            "open_questions": open_questions,
            "similar_past_tasks": [],  # Phase 2 填充
        },
        "metadata": {
            "nodes_analyzed": len(graph.nodes),
            "world_line_events": store.total_failures + store.total_fixes,
            "symptom_kappa": round(focus_node.curvature, 3),
            "target_kappa": round(target_node.curvature, 3),
        }
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return
```

### 验收标准
```bash
wlbs-scan . --advise rbac --json
# 输出合法 JSON，包含 schema / advisory / primary_suggestion / tone="suggestion"

wlbs-scan . --advise rbac --min-confidence 0.9
# 如果置信度不够，输出 {"advisory": null, "reason": "below min_confidence threshold"}

python -c "import json,subprocess; d=json.loads(subprocess.check_output(['wlbs-scan','.','--advise','rbac'])); assert d['advisory']['primary_suggestion']['tone']=='suggestion'"
# 通过
```

---

## 任务二：`--record-outcome` 命令（任务记忆写入）

### 要做什么
新增 `--record-outcome` 命令，让 agent/用户把任务结果写进 world-line。
这是学习闭环的入口——不只记录"这里失败了"，而是记录"整件事怎么打的"。

### 为什么
现有的 `--record-failure` 和 `--record-fix` 只记录节点级事件。
`--record-outcome` 记录任务级结果，包括 agent 选择了哪里、最终对不对、测试数量变化。
这些数据是后续策略学习的原材料。

### 怎么实现

**第一步：加参数**

在 `main()` 的 argparse 里加：

```python
p.add_argument("--record-outcome", action="store_true",
               help="Record a complete task outcome into world-line task memory")
p.add_argument("--symptom", metavar="NODE",
               help="Symptom node for --record-outcome")
p.add_argument("--final-target", metavar="NODE",
               help="Node that was actually fixed (may differ from wlbs suggestion)")
p.add_argument("--result", choices=["pass", "fail"],
               help="Task outcome: pass or fail")
p.add_argument("--tests-before", metavar="PASS/TOTAL",
               help="Test counts before fix, e.g. 4/6")
p.add_argument("--tests-after", metavar="PASS/TOTAL",
               help="Test counts after fix, e.g. 6/6")
p.add_argument("--task-id", metavar="ID",
               help="Task ID (auto-generated if omitted)")
```

**第二步：在 `main()` 里加处理逻辑**

在 `if args.record_fix:` 块之后加：

```python
if args.record_outcome:
    if not args.symptom or not args.result:
        print(colored("  Error: --record-outcome requires --symptom and --result", RED))
        sys.exit(1)

    # 自动生成 task_id
    task_id = args.task_id or f"T{datetime.now().strftime('%Y%m%d-%H%M%S')}-{args.symptom[:8]}"
    final_target = args.final_target or args.symptom

    # 解析测试数量
    def _parse_counts(s):
        if not s: return {}
        parts = s.split("/")
        try:
            return {"pass": int(parts[0]), "total": int(parts[1])} if len(parts)==2 else {}
        except: return {}

    before = _parse_counts(args.tests_before)
    after  = _parse_counts(args.tests_after)

    # 读取 wlbs 当时的建议（看建议是否被采纳）
    graph = build_graph(root, lang=args.lang)
    compute_curvature(graph, store=store)
    wlbs_suggested = None
    if args.symptom in graph.nodes:
        suggestion = build_repair_suggestion(graph, store, args.symptom)
        wlbs_suggested = suggestion["recommended_target"]

    suggestion_followed = (wlbs_suggested == final_target) if wlbs_suggested else None

    # 写入 world-line（节点级）
    if args.result == "pass":
        store.record_fix(final_target, f"task={task_id}|symptom={args.symptom}")
    else:
        store.record_failure(args.symptom, f"task={task_id}|target={final_target}")

    # 写入任务级记忆（追加到 world_lines.json 的 task_memory 字段）
    wl_path = root / ".wlbs" / "world_lines.json"
    try:
        data = json.loads(wl_path.read_text(encoding="utf-8")) if wl_path.exists() else {}
    except Exception:
        data = {}

    task_memory = data.get("task_memory", {})
    task_memory[task_id] = {
        "task_id": task_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "symptom": args.symptom,
        "wlbs_suggested_target": wlbs_suggested,
        "final_target": final_target,
        "suggestion_followed": suggestion_followed,
        "result": args.result,
        "tests_before": before,
        "tests_after": after,
        "detail": args.detail or "",
    }

    # 更新 routing_stats
    stats = data.get("routing_stats", {"total_tasks": 0, "followed": 0, "correct": 0})
    stats["total_tasks"] = stats.get("total_tasks", 0) + 1
    if suggestion_followed:
        stats["followed"] = stats.get("followed", 0) + 1
    if suggestion_followed and args.result == "pass":
        stats["correct"] = stats.get("correct", 0) + 1
    data["task_memory"] = task_memory
    data["routing_stats"] = stats

    wl_path.parent.mkdir(parents=True, exist_ok=True)
    wl_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    icon = colored("✓", GREEN) if args.result == "pass" else colored("✗", RED)
    print(f"  {icon} Outcome recorded: {task_id}")
    print(colored(f"    symptom={args.symptom}  target={final_target}  result={args.result}", GRAY))
    if suggestion_followed is not None:
        followed_str = "followed ✓" if suggestion_followed else "not followed"
        print(colored(f"    wlbs suggestion: {wlbs_suggested} ({followed_str})", GRAY))
    return
```

**第三步：升级 `--history` 显示任务记录**

在 `print_history()` 函数末尾加：

```python
# 读取任务级记忆
wl_path = store.path
try:
    data = json.loads(wl_path.read_text(encoding="utf-8")) if wl_path.exists() else {}
except Exception:
    data = {}

task_memory = data.get("task_memory", {})
if task_memory:
    print()
    print(colored("  Task Memory:", WHITE, BOLD))
    for task_id, task in sorted(task_memory.items(), reverse=True)[:5]:
        result_icon = colored("✓", GREEN) if task["result"] == "pass" else colored("✗", RED)
        followed = ""
        if task.get("suggestion_followed") is True:
            followed = colored(" (suggestion followed ✓)", GREEN)
        elif task.get("suggestion_followed") is False:
            followed = colored(" (different path taken)", YELLOW)
        print(f"    {result_icon} {task_id}")
        print(colored(f"       {task['symptom']} → {task['final_target']}{followed}", GRAY))

    stats = data.get("routing_stats", {})
    if stats.get("total_tasks", 0) > 0:
        total = stats["total_tasks"]
        correct = stats.get("correct", 0)
        print()
        print(colored(f"  Routing accuracy: {correct}/{total} ({correct*100//total}%)", CYAN))
```

### 验收标准
```bash
wlbs-scan . --record-outcome --symptom rbac --final-target roles --result pass \
            --tests-before 4/6 --tests-after 6/6

wlbs-scan . --history
# 能看到 Task Memory 段落，显示刚才的记录

# 检查 world_lines.json 有 task_memory 字段
python -c "import json; d=json.load(open('.wlbs/world_lines.json')); assert 'task_memory' in d"
```

---

## 任务三：HTTP 服务（`wlbs_server.py`，新建文件）

### 要做什么
新建 `wlbs_server.py`，约150行，提供三个 HTTP 端点：
- 上传本地脱敏晶体到共享库
- 下载共享库经验到本地
- 查询健康状态

这个文件**部署在 VPS 上**，用户的 CLI 通过 `--sync` 命令与它通信。

### 怎么实现

**新建 `wlbs_server.py`（部署在 VPS）：**

```python
#!/usr/bin/env python3
"""
wlbs-scan 共享经验库服务端
部署：uvicorn wlbs_server:app --host 0.0.0.0 --port 8765
"""
from __future__ import annotations
import json, hashlib, time
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

try:
    from fastapi import FastAPI, HTTPException, Header
    from pydantic import BaseModel
except ImportError:
    raise SystemExit("pip install fastapi uvicorn pydantic")

app = FastAPI(title="wlbs-scan Experience Hub")

# ── 配置 ───────────────────────────────────────────────
STORAGE_DIR = Path("./hub_data")
CRYSTALS_PATH = STORAGE_DIR / "shared_crystals.jsonl"
KEYS_PATH = STORAGE_DIR / "api_keys.json"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

def _load_keys() -> dict:
    if not KEYS_PATH.exists():
        return {}
    return json.loads(KEYS_PATH.read_text(encoding="utf-8"))

def _verify_key(api_key: str) -> bool:
    keys = _load_keys()
    return api_key in keys

def _add_key(api_key: str, user: str, plan: str = "pro"):
    """手动调用添加新用户 key"""
    keys = _load_keys()
    keys[api_key] = {"user": user, "plan": plan, "created_at": datetime.now(timezone.utc).isoformat()}
    KEYS_PATH.write_text(json.dumps(keys, indent=2, ensure_ascii=False), encoding="utf-8")

# ── 数据模型 ───────────────────────────────────────────
class CrystalUpload(BaseModel):
    crystals: list[dict]          # 脱敏后的晶体列表
    client_version: str = "0.5.0"

class SyncResponse(BaseModel):
    uploaded: int
    downloaded: int
    total_in_hub: int

# ── 脱敏函数（上传前在客户端执行）────────────────────
def _sanitize_crystal(crystal: dict) -> dict | None:
    """
    去掉隐私字段，只保留可共享的规则层。
    在客户端（--sync命令里）调用，不是服务端。
    """
    rule = str(crystal.get("distillation", {}).get("rule", "")).strip()
    confidence = float(crystal.get("distillation", {}).get("confidence", 0))
    outcome = crystal.get("outcome", "failure")
    turns = int(crystal.get("turns_used", 99))

    # 质量门槛
    if not rule:
        return None
    if confidence < 0.6:
        return None
    if turns > 10:
        return None

    fp = crystal.get("fingerprint", {})
    return {
        "rule": rule,
        "rule_type": crystal.get("distillation", {}).get("rule_type", "positive"),
        "confidence": round(confidence, 3),
        "outcome": outcome,
        "task_type": fp.get("task_type", ""),
        "language": fp.get("language", ""),
        "complexity_level": fp.get("complexity_level", ""),
        "complexity_signals": fp.get("complexity_signals", []),
        "turns_used": turns,
        "contributed_at": datetime.now(timezone.utc).isoformat(),
        # 不包含：文件名、代码内容、错误详情、用户信息
    }

# ── 端点 ───────────────────────────────────────────────
@app.get("/health")
def health():
    count = 0
    if CRYSTALS_PATH.exists():
        count = sum(1 for line in CRYSTALS_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
    return {"status": "ok", "total_crystals": count, "ts": datetime.now(timezone.utc).isoformat()}

@app.post("/crystals/upload")
def upload_crystals(payload: CrystalUpload, x_api_key: Optional[str] = Header(None)):
    if not x_api_key or not _verify_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    accepted = 0
    with CRYSTALS_PATH.open("a", encoding="utf-8") as f:
        for crystal in payload.crystals:
            sanitized = _sanitize_crystal(crystal)
            if sanitized:
                f.write(json.dumps(sanitized, ensure_ascii=False) + "\n")
                accepted += 1

    return {"accepted": accepted, "rejected": len(payload.crystals) - accepted}

@app.get("/crystals/download")
def download_crystals(x_api_key: Optional[str] = Header(None), limit: int = 200):
    if not x_api_key or not _verify_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    if not CRYSTALS_PATH.exists():
        return {"crystals": [], "total": 0}

    lines = [l.strip() for l in CRYSTALS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    # 返回最新的 limit 条
    recent = lines[-limit:]
    crystals = []
    for line in recent:
        try:
            crystals.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return {"crystals": crystals, "total": len(lines)}

@app.get("/stats")
def stats(x_api_key: Optional[str] = Header(None)):
    """共享库统计，付费用户可见"""
    if not x_api_key or not _verify_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    if not CRYSTALS_PATH.exists():
        return {"total": 0, "by_language": {}, "by_outcome": {}}

    by_lang: dict[str, int] = {}
    by_outcome: dict[str, int] = {}
    total = 0
    for line in CRYSTALS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            c = json.loads(line)
            lang = c.get("language", "unknown")
            outcome = c.get("outcome", "unknown")
            by_lang[lang] = by_lang.get(lang, 0) + 1
            by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
            total += 1
        except Exception:
            continue

    return {"total": total, "by_language": by_lang, "by_outcome": by_outcome}
```

**VPS 部署命令：**
```bash
pip install fastapi uvicorn pydantic
uvicorn wlbs_server:app --host 0.0.0.0 --port 8765

# 后台运行
nohup uvicorn wlbs_server:app --host 0.0.0.0 --port 8765 > wlbs_server.log 2>&1 &

# 添加用户key（手动执行）
python -c "from wlbs_server import _add_key; _add_key('key_用户付款后生成', '用户名')"
```

---

## 任务四：`--sync` 命令（客户端 CLI，加进 `wlbs_scan.py`）

### 要做什么
用户执行 `wlbs-scan . --sync --api-key <key>`，
自动完成：上传本地晶体 + 下载共享经验 + 合并到本地。

### 怎么实现

**第一步：加参数**

```python
p.add_argument("--sync", action="store_true",
               help="Upload local crystals to hub and download shared experience (requires --api-key)")
p.add_argument("--api-key", metavar="KEY",
               help="API key for Pro features (--sync, --contribute)")
p.add_argument("--hub-url", metavar="URL", default="http://YOUR_VPS_IP:8765",
               help="wlbs hub server URL")
```

**第二步：加处理逻辑**

在 `main()` 里，`if args.reset:` 之前加：

```python
if args.sync:
    if not args.api_key:
        print(colored("  Error: --sync requires --api-key", RED))
        print(colored("  Get your key at: https://kaiwucl.com/pro", GRAY))
        sys.exit(1)
    _sync_with_hub(root, args.api_key, args.hub_url)
    return
```

**第三步：实现 `_sync_with_hub()` 函数**

在 `wlbs_scan.py` 末尾（`if __name__=="__main__":` 之前）加：

```python
def _sync_with_hub(root: Path, api_key: str, hub_url: str):
    """上传本地经验晶体，下载共享经验库。"""
    try:
        import urllib.request, urllib.error
    except ImportError:
        print(colored("  Error: urllib not available", RED))
        return

    crystals_path = root / ".opencraft" / "living_state" / "experience_crystals.jsonl"
    shared_path   = root / ".wlbs" / "shared_rules.json"

    # ── 上传 ──────────────────────────────────────────
    uploaded = 0
    if crystals_path.exists():
        lines = crystals_path.read_text(encoding="utf-8").splitlines()
        to_upload = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                crystal = json.loads(line)
                # 脱敏：只保留规则层
                rule = str(crystal.get("distillation", {}).get("rule", "")).strip()
                confidence = float(crystal.get("distillation", {}).get("confidence", 0))
                if rule and confidence >= 0.6 and int(crystal.get("turns_used", 99)) <= 10:
                    fp = crystal.get("fingerprint", {})
                    to_upload.append({
                        "rule": rule,
                        "rule_type": crystal.get("distillation", {}).get("rule_type", "positive"),
                        "confidence": round(confidence, 3),
                        "outcome": crystal.get("outcome", "failure"),
                        "task_type": fp.get("task_type", ""),
                        "language": fp.get("language", ""),
                        "complexity_signals": fp.get("complexity_signals", []),
                        "turns_used": int(crystal.get("turns_used", 0)),
                    })
            except Exception:
                continue

        if to_upload:
            try:
                body = json.dumps({"crystals": to_upload, "client_version": __version__}).encode()
                req = urllib.request.Request(
                    f"{hub_url}/crystals/upload",
                    data=body,
                    headers={"Content-Type": "application/json", "x-api-key": api_key},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                    uploaded = result.get("accepted", 0)
            except Exception as e:
                print(colored(f"  Upload failed: {e}", YELLOW))

    # ── 下载 ──────────────────────────────────────────
    downloaded = 0
    try:
        req = urllib.request.Request(
            f"{hub_url}/crystals/download?limit=200",
            headers={"x-api-key": api_key},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            shared_crystals = result.get("crystals", [])
            downloaded = len(shared_crystals)
            shared_path.parent.mkdir(parents=True, exist_ok=True)
            shared_path.write_text(
                json.dumps({"crystals": shared_crystals, "synced_at": datetime.now(timezone.utc).isoformat()},
                           indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
    except Exception as e:
        print(colored(f"  Download failed: {e}", YELLOW))

    # ── 结果 ──────────────────────────────────────────
    print(colored(f"  ✓ Sync complete", GREEN))
    print(colored(f"    Uploaded: {uploaded} crystals", GRAY))
    print(colored(f"    Downloaded: {downloaded} shared rules → .wlbs/shared_rules.json", GRAY))
    print(colored(f"    Run 'wlbs-scan . --suggest' to use shared experience", GRAY))
```

### 验收标准
```bash
# 测试（用测试key）
wlbs-scan . --sync --api-key test_key_pro

# 应该看到：
# ✓ Sync complete
#   Uploaded: N crystals
#   Downloaded: M shared rules → .wlbs/shared_rules.json
```

---

## 任务五：权限和用户管理

### 要做什么
免费用户和付费用户的功能区分，API key 的管理流程。

### 功能区分

| 功能 | 免费 | Pro |
|---|---|---|
| `wlbs-scan .` 扫描 | ✅ | ✅ |
| `--suggest / --advise` | ✅ | ✅ |
| `--record-outcome` | ✅ | ✅ |
| 本地 world-line 记忆 | ✅ | ✅ |
| `--sync` 共享经验库 | ❌ | ✅ |
| 下载全员共享规则 | ❌ | ✅ |
| 云端规则同步 | ❌ | ✅ |

### API key 管理（早期手动）

**服务端操作（你在VPS上执行）：**

```bash
# 用户付款后，SSH进VPS，执行：
python -c "
from wlbs_server import _add_key
_add_key('wlbs_pro_生成一个随机字符串', '用户姓名或邮箱')
"
# 把生成的 key 发给用户
```

**key 格式建议：** `wlbs_pro_` + 16位随机字符，例如 `wlbs_pro_a3f9k2m7x8p1q4r6`

生成方法：
```python
import secrets
key = "wlbs_pro_" + secrets.token_hex(8)
print(key)
```

**用户侧保存 key（避免每次输入）：**

在 `--sync` 逻辑里支持从环境变量读取：

```python
# 在 _sync_with_hub 调用前加
if not args.api_key:
    import os
    args.api_key = os.environ.get("WLBS_API_KEY", "")
```

用户只需要设置一次：
```bash
# Windows
setx WLBS_API_KEY "wlbs_pro_你的key"

# Mac/Linux
echo 'export WLBS_API_KEY="wlbs_pro_你的key"' >> ~/.bashrc
```

---

## 文件清单

| 操作 | 文件 | 说明 |
|---|---|---|
| 修改 | `wlbs_scan.py` | 加 `--advise` / `--record-outcome` / `--sync` 参数和逻辑 |
| 新建 | `wlbs_server.py` | VPS服务端，部署在你的服务器 |
| 修改 | `pyproject.toml` | 加 `[project.optional-dependencies]` |
| 新建 | `.vscode/` 目录下4个文件 | IDE兼容（之前已给） |

**`pyproject.toml` 追加：**
```toml
[project.optional-dependencies]
server = ["fastapi>=0.100.0", "uvicorn>=0.20.0", "pydantic>=2.0.0"]
```

用户安装服务端依赖：`pip install wlbs-scan[server]`

---

## 执行顺序

```
Day 1    任务一：--advise 命令
         任务二：--record-outcome 命令
         验收：两个命令跑通

Day 2    任务三：wlbs_server.py 写完
         部署到 BandwagonHost VPS
         测试 /health 端点通

Day 3    任务四：--sync 命令
         端到端测试：本地 → VPS → 下载回来

Day 4    任务五：key管理流程走通
         测试：无key被拒绝，有key正常访问
         整体验收
```

---

## 最终验收

全部完成后，以下流程必须跑通：

```bash
# 免费用户全流程
pip install wlbs-scan
wlbs-scan .                          # 扫描正常
wlbs-scan . --advise rbac            # advisory JSON输出
wlbs-scan . --record-outcome --symptom rbac --final-target roles --result pass
wlbs-scan . --history                # 能看到 Task Memory

# Pro用户全流程
wlbs-scan . --sync --api-key wlbs_pro_xxx   # 上传+下载
# 服务端能看到上传的晶体
curl -H "x-api-key: wlbs_pro_xxx" http://VPS_IP:8765/stats
# 返回共享库统计

# 无效key被拒绝
wlbs-scan . --sync --api-key invalid_key
# 输出错误提示，不崩溃
```

---

> 文档版本：v1.0 · 2026-03-26
> wlbs-scan v0.5 → v0.6 改造
> 核心原则：wlbs_scan.py 一行不动，所有改动以新增参数和新建文件方式叠加
