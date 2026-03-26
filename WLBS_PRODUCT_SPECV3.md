# wlbs-scan 产品改造任务书 v3

## 工程师执行版 · 2026-03-26

\---

## 产品结构（最终决策）

```
免费版（无需 API key）：
  - 本地扫描，识别错误
  - 手动执行 --status 查看风险文件
  - 本地 world-line 自动记录（不需要用户操作）
  - 不能访问共享经验库
  - 积分获取系数 0.3（慢，）

付费版 Pro（9.9/月，1个 API key）：
  - 免费版所有功能
  - 任务结束自动查询云端经验，自动输出建议
  - 轨迹自动上传（用户零感知）
  - 访问共享经验库（无数量限制，限频保护服务器）
  - 积分获取系数 0.5（约1.7个月换1个key）
  - --dashboard 打开热力图 Web 界面

积分系统：
  100积分 = 1个key（30天有效，从首次使用开始计）
  每年12月清零
  服务端计算，客户端只读，无法篡改
```

\---

## 积分规则（服务端计算）

|事件|免费系数|Pro系数|
|-|-|-|
|成功任务轨迹上传（outcome=success）|+0.3|+0.5|
|高质量加成（confidence≥0.8）|+0.1|+0.3|
|失败任务上传（负向经验也有价值）|+0.05|+0.1|

```
```

**积分安全原则：**

* 积分只在服务端计算和存储
* 用户只能 GET 查询，不能 POST 修改
* 每次轨迹上传后服务端自动加分，与上传原子操作绑定
* Key有效期从首次调用API开始计30天，不是生成时

\---

## 任务一：自动记录（不需要用户手动操作）

### 要做什么

现在 `--record-failure` / `--record-fix` 需要用户手动执行。
改成：`--pytest` 跑完后自动写入 world-line，用户零操作。

### 现状

`--pytest` 已经能自动解析 pytest 结果并调用 `store.record\_failure` / `store.record\_fix`。
这部分**已经做好了**，不需要改。

### 需要改的

去掉文档和 README 里"需要手动执行 --record-failure"的说法。
确认 `--pytest` 的自动记录逻辑覆盖以下场景：

```bash
# 这一条命令，自动完成扫描+测试+记录
wlbs-scan . --pytest tests/

# 验证：跑完后 world-line 有新事件
wlbs-scan . --history
```

如果用户用的是 `pytest` 命令直接跑（不通过 wlbs），加一个 `pytest` 插件钩子：

**新建 `wlbs\_pytest\_plugin.py`：**

```python
"""
pytest 插件：测试结束后自动写入 wlbs world-line。
安装：pip install wlbs-scan
使用：在 conftest.py 里加 pytest\_plugins = \['wlbs\_pytest\_plugin']
或者：pytest --wlbs .
"""
import subprocess, shutil
from pathlib import Path

def pytest\_addoption(parser):
    parser.addoption("--wlbs", metavar="PROJECT\_ROOT", default=None,
                     help="Enable wlbs-scan auto-record after test run")

def pytest\_terminal\_summary(terminalreporter, exitstatus, config):
    root = config.getoption("--wlbs")
    if not root or not shutil.which("wlbs-scan"):
        return
    # 收集失败的测试模块
    failed = terminalreporter.stats.get("failed", \[])
    passed = terminalreporter.stats.get("passed", \[])
    for report in failed:
        node\_id = report.nodeid.split("::")\[0].replace("/", ".").replace("\\\\", ".").removesuffix(".py")
        subprocess.run(\["wlbs-scan", root, "--record-failure", node\_id,
                       "--detail", str(report.longreprtext)\[:200]],
                      capture\_output=True, timeout=5)
    for report in passed:
        node\_id = report.nodeid.split("::")\[0].replace("/", ".").replace("\\\\", ".").removesuffix(".py")
        subprocess.run(\["wlbs-scan", root, "--record-fix", node\_id],
                      capture\_output=True, timeout=5)
```

在 `pyproject.toml` 里注册：

```toml
\[project.entry-points."pytest11"]
wlbs = "wlbs\_pytest\_plugin"
```

\---

## 任务二：`--status` 命令（风险查询）

### 要做什么

新增 `--status`，显示当前项目风险状态 + 账户积分信息。

**免费用户：** 手动执行 `wlbs-scan . --status`，看到风险文件列表。
**Pro用户：** 任务结束后自动触发，同时在对话上下文里追加建议文件。

### 在 `wlbs\_scan.py` 里加参数

```python
p.add\_argument("--status", action="store\_true",
               help="Show current risk status and account info")
```

### 在 `scan()` 函数里加处理逻辑

在 `if args.suggest:` 之前加：

```python
if args.status:
    sings = find\_singularities(graph)
    high\_risk = sorted(
        \[n for n in graph.nodes.values() if n.curvature >= 0.4],
        key=lambda n: n.curvature, reverse=True
    )\[:10]

    print()
    print(colored("━"\*55, CYAN, BOLD))
    print(colored("  wlbs-scan Status", WHITE, BOLD))
    print(colored("━"\*55, CYAN, BOLD))

    if sings:
        print()
        print(colored("  ⚠ Singularities detected (likely root causes):", YELLOW, BOLD))
        for s in sings\[:3]:
            node = graph.nodes\[s.id]
            print(colored(f"    ★ {s.id}  κ={node.curvature:.3f}  "
                         f"failures={node.failure\_count}", RED))

    if high\_risk:
        print()
        print(colored("  High-risk files to investigate:", WHITE, BOLD))
        for node in high\_risk\[:5]:
            flag = " ← SINGULARITY" if node.id in {s.id for s in sings} else ""
            bar  = "█" \* int(node.curvature \* 10) + "░" \* (10 - int(node.curvature \* 10))
            print(f"    {colored(bar, RED if node.curvature>=0.7 else YELLOW)}  "
                  f"{colored(node.id, WHITE)}  κ={node.curvature:.3f}{colored(flag, RED)}")

    # 账户积分（有api-key时查询服务端）
    if args.api\_key:
        points\_info = \_query\_points(args.api\_key, args.hub\_url)
        if points\_info:
            print()
            print(colored("  Account:", WHITE, BOLD))
            print(colored(f"    Points: {points\_info.get('points', 0):.1f} / 100 needed for 1 key", CYAN))
            print(colored(f"    Tier:   {points\_info.get('tier', 'free')}", GRAY))
            expires = points\_info.get('key\_expires\_at', '')
            if expires:
                print(colored(f"    Key expires: {expires\[:10]}", GRAY))
    else:
        print()
        print(colored("  Add --api-key <key> to see account info", GRAY))

    print()
    print(colored("━"\*55, CYAN))
    print()
    return
```

加辅助函数：

```python
def \_query\_points(api\_key: str, hub\_url: str) -> dict | None:
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{hub\_url}/account/status",
            headers={"x-api-key": api\_key}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read())
    except Exception:
        return None
```

\---

## 任务三：Pro 用户自动建议输出

### 要做什么

Pro 用户任务结束后，wlbs 自动把高风险节点写入 `.wlbs/current\_advice.md`。
模型通过 CLAUDE.md / .cursorrules 配置自动读取这个文件。

用户配置一次，之后永久生效，无感知。

### 新建 `\_write\_auto\_advice()` 函数（加在 `wlbs\_scan.py` 末尾）

```python
def \_write\_auto\_advice(graph: BehaviorGraph, store: WorldLineStore,
                       root: Path, api\_key: str, hub\_url: str):
    """
    Pro用户专属：任务结束后自动生成建议文件。
    写入 .wlbs/current\_advice.md，模型通过 rules 文件自动读取。
    """
    sings    = find\_singularities(graph)
    high\_risk = sorted(
        \[n for n in graph.nodes.values() if n.curvature >= 0.5],
        key=lambda n: n.curvature, reverse=True
    )\[:5]

    if not high\_risk and not sings:
        # 没有高风险节点，清空建议文件
        advice\_path = root / ".wlbs" / "current\_advice.md"
        advice\_path.write\_text("<!-- wlbs: no high-risk nodes detected -->", encoding="utf-8")
        return

    lines = \["<!-- wlbs-scan auto-advice (Pro) -->",
             f"<!-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} -->", ""]

    if sings:
        lines.append("## ⚠ Likely Root Causes (Singularities)")
        for s in sings\[:2]:
            node = graph.nodes\[s.id]
            suggestion = build\_repair\_suggestion(graph, store, s.id)
            lines.append(f"- \*\*{s.id}\*\* (κ={node.curvature:.2f}): "
                        f"{suggestion\['reasoning\_chain']\[0] if suggestion\['reasoning\_chain'] else 'high curvature upstream node'}")
        lines.append("")

    lines.append("## High-Risk Files")
    for node in high\_risk:
        flag = " ★ SINGULARITY" if node.id in {s.id for s in sings} else ""
        lines.append(f"- `{node.id}` — κ={node.curvature:.2f}, "
                    f"failures={node.failure\_count}{flag}")

    lines.extend(\["", "## Suggestion",
                  "Investigate the singularity nodes first before modifying symptom files."])

    advice\_path = root / ".wlbs" / "current\_advice.md"
    advice\_path.parent.mkdir(parents=True, exist\_ok=True)
    advice\_path.write\_text("\\n".join(lines), encoding="utf-8")
```

### 在主扫描流程末尾调用

在 `scan()` 函数末尾（`print\_report` 之后）加：

```python
# Pro用户自动建议
if args.api\_key and not args.json and not args.ci:
    \_write\_auto\_advice(graph, store, root, args.api\_key, args.hub\_url)
```

### 用户一次性配置（写进 README）

**Claude Code 用户**，在项目根目录建 `CLAUDE.md`：

```markdown
## wlbs-scan Integration
Before investigating any bug, read `.wlbs/current\_advice.md` if it exists.
This file contains auto-generated risk analysis for the current project state.
```

**Cursor 用户**，在 `.cursorrules` 里加：

```
Before debugging, check .wlbs/current\_advice.md for risk analysis.
```

\---

## 任务四：实时热力图 Dashboard（`--dashboard` 命令）

### 要做什么

新建 `wlbs\_dashboard.py`，用户执行 `wlbs-scan . --dashboard` 后：

1. 启动本地 HTTP 服务（端口 7890）
2. 自动打开浏览器
3. 显示实时热力图 + 账户信息 + 积分 + 兑换入口

### 在 `wlbs\_scan.py` 里加参数

```python
p.add\_argument("--dashboard", action="store\_true",
               help="Open interactive risk heatmap in browser (Pro: includes account info)")
```

在 `main()` 里加处理：

```python
if args.dashboard:
    \_launch\_dashboard(root, args.api\_key or "", args.hub\_url)
    return
```

### 新建 `wlbs\_dashboard.py`

```python
#!/usr/bin/env python3
"""
wlbs-scan Dashboard — 实时热力图 Web 界面
内部调用，不直接执行。由 wlbs\_scan.py --dashboard 启动。
"""
from \_\_future\_\_ import annotations
import json, threading, webbrowser, time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# 使用标准库 http.server，零依赖
PORT = 7890

def build\_dashboard\_html(graph\_data: dict, account\_data: dict | None) -> str:
    nodes     = graph\_data.get("nodes", \[])
    sings     = set(graph\_data.get("singularities", \[]))
    task\_mem  = graph\_data.get("task\_memory", {})

    # 热力图数据
    heatmap\_rows = ""
    for node in nodes\[:50]:
        kappa    = float(node.get("curvature", 0))
        nid      = node.get("id", "")
        failures = int(node.get("failures", 0))
        is\_sing  = nid in sings
        pct      = int(kappa \* 100)

        if kappa >= 0.7:
            color = f"rgba(248,81,73,{0.4 + kappa \* 0.6:.2f})"
            text\_color = "#f85149"
            badge = '<span class="badge-sing">★ ROOT CAUSE</span>' if is\_sing else '<span class="badge-high">HIGH</span>'
        elif kappa >= 0.4:
            color = f"rgba(227,179,65,{0.3 + kappa \* 0.5:.2f})"
            text\_color = "#e3b341"
            badge = '<span class="badge-med">MED</span>'
        else:
            color = "rgba(63,185,80,0.15)"
            text\_color = "#3fb950"
            badge = '<span class="badge-low">LOW</span>'

        warn = ""
        if is\_sing:
            warn = f'<div class="warn-box">⚠ Likely root cause — investigate before touching downstream files</div>'

        heatmap\_rows += f"""
        <div class="node-card" style="border-left:4px solid {text\_color}; background:{color}">
          <div class="node-header">
            <span class="node-id">{nid}</span>
            {badge}
          </div>
          <div class="node-bar-wrap">
            <div class="node-bar" style="width:{pct}%; background:{text\_color}"></div>
          </div>
          <div class="node-meta">κ = {kappa:.3f} · failures = {failures}</div>
          {warn}
        </div>"""

    # 账户面板
    account\_html = ""
    if account\_data:
        points     = float(account\_data.get("points", 0))
        tier       = account\_data.get("tier", "free")
        expires    = account\_data.get("key\_expires\_at", "")\[:10]
        pct\_points = min(100, int(points))
        account\_html = f"""
        <div class="account-panel">
          <h2>Account</h2>
          <div class="account-row">
            <span class="acc-label">Plan</span>
            <span class="acc-value tier-{tier}">{tier.upper()}</span>
          </div>
          <div class="account-row">
            <span class="acc-label">Points</span>
            <span class="acc-value">{points:.1f} / 100</span>
          </div>
          <div class="points-bar-wrap">
            <div class="points-bar" style="width:{pct\_points}%"></div>
          </div>
          <div class="points-hint">100 points = 1 key (30 days). Resets every December.</div>
          {"<div class='acc-row'><span class='acc-label'>Key expires</span><span class='acc-value'>" + expires + "</span></div>" if expires else ""}
          <div class="redeem-section">
            <h3>Redeem Key</h3>
            <div class="redeem-row">
              <input id="redeemInput" type="text" placeholder="Enter email to receive key" />
              <button onclick="redeemKey()">Redeem (100pts)</button>
            </div>
            <div id="redeemMsg" class="redeem-msg"></div>
          </div>
        </div>"""
    else:
        account\_html = """
        <div class="account-panel">
          <h2>Account</h2>
          <p class="no-key">No API key configured.<br>
          <a href="https://kaiwucl.com/pro" target="\_blank">Upgrade to Pro →</a></p>
        </div>"""

    # 最近任务
    recent\_tasks = ""
    for tid, task in sorted(task\_mem.items(), reverse=True)\[:5]:
        icon   = "✓" if task.get("result") == "pass" else "✗"
        color  = "#3fb950" if task.get("result") == "pass" else "#f85149"
        target = task.get("final\_target", "")
        ts     = task.get("ts", "")\[:16]
        recent\_tasks += f"""
        <div class="task-row">
          <span style="color:{color}">{icon}</span>
          <span class="task-id">{tid}</span>
          <span class="task-target">→ {target}</span>
          <span class="task-ts">{ts}</span>
        </div>"""

    if not recent\_tasks:
        recent\_tasks = '<div class="no-tasks">No task history yet. Run wlbs-scan . --pytest tests/</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>wlbs-scan Dashboard</title>
<style>
\* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0d1117; color: #c9d1d9; font-size: 13px; }}
.topbar {{ background: #161b22; border-bottom: 1px solid #30363d;
          padding: 16px 32px; display: flex; align-items: center; gap: 16px; }}
.topbar h1 {{ font-size: 20px; color: #58a6ff; font-weight: 700; }}
.topbar .sub {{ color: #8b949e; font-size: 12px; }}
.topbar .refresh {{ margin-left: auto; background: #21262d; border: 1px solid #30363d;
                    color: #c9d1d9; padding: 6px 14px; border-radius: 6px;
                    cursor: pointer; font-size: 12px; }}
.topbar .refresh:hover {{ background: #30363d; }}
.layout {{ display: grid; grid-template-columns: 1fr 300px; gap: 0; height: calc(100vh - 57px); }}
.main {{ overflow-y: auto; padding: 24px 32px; }}
.sidebar {{ background: #161b22; border-left: 1px solid #30363d;
           overflow-y: auto; padding: 20px; }}
h2 {{ color: #58a6ff; font-size: 14px; font-weight: 600; margin-bottom: 16px; }}
h3 {{ color: #8b949e; font-size: 12px; font-weight: 600; margin: 16px 0 8px; text-transform: uppercase; }}

.node-card {{ border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; transition: transform 0.1s; }}
.node-card:hover {{ transform: translateX(4px); }}
.node-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
.node-id {{ font-family: 'SF Mono', Consolas, monospace; font-size: 13px; font-weight: 600; color: #e6edf3; }}
.node-bar-wrap {{ background: rgba(0,0,0,0.3); border-radius: 3px; height: 5px; margin-bottom: 6px; }}
.node-bar {{ height: 5px; border-radius: 3px; transition: width 0.3s; }}
.node-meta {{ font-size: 11px; color: #8b949e; }}
.warn-box {{ margin-top: 8px; padding: 6px 10px; background: rgba(248,81,73,0.1);
            border: 1px solid rgba(248,81,73,0.3); border-radius: 4px;
            font-size: 11px; color: #f85149; }}

.badge-sing {{ background: #3a1a5c; color: #d4b0f0; border: 1px solid #7f77dd;
              font-size: 10px; padding: 2px 6px; border-radius: 3px; }}
.badge-high {{ background: rgba(248,81,73,0.2); color: #f85149; border: 1px solid rgba(248,81,73,0.4);
              font-size: 10px; padding: 2px 6px; border-radius: 3px; }}
.badge-med  {{ background: rgba(227,179,65,0.2); color: #e3b341; border: 1px solid rgba(227,179,65,0.4);
              font-size: 10px; padding: 2px 6px; border-radius: 3px; }}
.badge-low  {{ background: rgba(63,185,80,0.1); color: #3fb950; border: 1px solid rgba(63,185,80,0.2);
              font-size: 10px; padding: 2px 6px; border-radius: 3px; }}

.account-panel {{ margin-bottom: 24px; }}
.account-row, .acc-row {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
.acc-label {{ color: #8b949e; font-size: 12px; }}
.acc-value {{ font-size: 12px; font-weight: 600; }}
.tier-pro {{ color: #58a6ff; }}
.tier-free {{ color: #8b949e; }}
.points-bar-wrap {{ background: #21262d; border-radius: 4px; height: 8px; margin: 8px 0; }}
.points-bar {{ height: 8px; border-radius: 4px; background: linear-gradient(90deg, #58a6ff, #3fb950); transition: width 0.5s; }}
.points-hint {{ font-size: 11px; color: #8b949e; margin-bottom: 12px; }}
.no-key {{ color: #8b949e; font-size: 12px; line-height: 1.8; }}
.no-key a {{ color: #58a6ff; text-decoration: none; }}

.redeem-section {{ margin-top: 16px; padding-top: 16px; border-top: 1px solid #30363d; }}
.redeem-row {{ display: flex; gap: 8px; margin-bottom: 8px; }}
.redeem-row input {{ flex: 1; background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
                    padding: 6px 10px; border-radius: 6px; font-size: 12px; }}
.redeem-row button {{ background: #238636; border: none; color: #fff; padding: 6px 12px;
                     border-radius: 6px; cursor: pointer; font-size: 12px; white-space: nowrap; }}
.redeem-row button:hover {{ background: #2ea043; }}
.redeem-msg {{ font-size: 11px; color: #8b949e; min-height: 16px; }}

.task-row {{ display: flex; gap: 8px; align-items: center; padding: 6px 0;
            border-bottom: 1px solid #21262d; font-size: 12px; }}
.task-id {{ font-family: monospace; font-size: 10px; color: #8b949e; flex: 1; }}
.task-target {{ color: #58a6ff; }}
.task-ts {{ color: #8b949e; font-size: 10px; }}
.no-tasks {{ color: #8b949e; font-size: 12px; padding: 8px 0; }}

.filter {{ margin-bottom: 16px; }}
.filter input {{ background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
               padding: 8px 14px; border-radius: 6px; font-size: 13px; width: 100%; }}
</style>
</head>
<body>
<div class="topbar">
  <h1>wlbs-scan</h1>
  <span class="sub">Behavior Risk Dashboard · Auto-refreshes every 10s</span>
  <button class="refresh" onclick="location.reload()">↺ Refresh</button>
</div>
<div class="layout">
  <div class="main">
    <h2>File Risk Heatmap</h2>
    <div class="filter">
      <input type="text" id="q" placeholder="Filter by file name..." oninput="filterCards()">
    </div>
    <div id="cards">{heatmap\_rows if heatmap\_rows else '<div style="color:#8b949e;padding:20px 0">No nodes analyzed yet. Run: wlbs-scan . --pytest tests/</div>'}</div>
  </div>
  <div class="sidebar">
    {account\_html}
    <h2>Recent Tasks</h2>
    {recent\_tasks}
  </div>
</div>
<script>
function filterCards() {{
  const q = document.getElementById('q').value.toLowerCase();
  document.querySelectorAll('#cards .node-card').forEach(c => {{
    c.style.display = c.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
function redeemKey() {{
  const email = document.getElementById('redeemInput').value.trim();
  const msg   = document.getElementById('redeemMsg');
  if (!email) {{ msg.textContent = 'Please enter an email address.'; return; }}
  msg.textContent = 'Sending request...';
  fetch('/redeem', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{email}})
  }})
  .then(r => r.json())
  .then(d => {{ msg.textContent = d.message || 'Done.'; }})
  .catch(() => {{ msg.textContent = 'Request failed. Please try again.'; }});
}}
// 10秒自动刷新
setTimeout(() => location.reload(), 10000);
</script>
</body>
</html>"""


def \_launch\_dashboard(root: Path, api\_key: str, hub\_url: str):
    """启动本地 dashboard 服务并打开浏览器。"""
    import wlbs\_scan as ws

    def get\_data():
        store = ws.WorldLineStore(root)
        graph = ws.build\_graph(root)
        ws.compute\_curvature(graph, store=store)
        graph\_data = ws.report\_json(graph, store)

        # 加入任务记忆
        wl\_path = root / ".wlbs" / "world\_lines.json"
        try:
            full = json.loads(wl\_path.read\_text(encoding="utf-8")) if wl\_path.exists() else {}
            graph\_data\["task\_memory"] = full.get("task\_memory", {})
        except Exception:
            graph\_data\["task\_memory"] = {}
        return graph\_data

    def get\_account():
        if not api\_key:
            return None
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{hub\_url}/account/status",
                headers={"x-api-key": api\_key}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    class Handler(BaseHTTPRequestHandler):
        def log\_message(self, \*args): pass  # 静默日志

        def do\_GET(self):
            graph\_data   = get\_data()
            account\_data = get\_account()
            html = build\_dashboard\_html(graph\_data, account\_data)
            self.send\_response(200)
            self.send\_header("Content-Type", "text/html; charset=utf-8")
            self.end\_headers()
            self.wfile.write(html.encode())

        def do\_POST(self):
            if self.path == "/redeem":
                length  = int(self.headers.get("Content-Length", 0))
                body    = json.loads(self.rfile.read(length))
                email   = body.get("email", "")
                # 调服务端兑换接口
                try:
                    import urllib.request
                    req = urllib.request.Request(
                        f"{hub\_url}/account/redeem",
                        data=json.dumps({"email": email}).encode(),
                        headers={"Content-Type": "application/json", "x-api-key": api\_key},
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        result = json.loads(resp.read())
                except Exception as e:
                    result = {"message": f"Error: {e}"}
                self.send\_response(200)
                self.send\_header("Content-Type", "application/json")
                self.end\_headers()
                self.wfile.write(json.dumps(result).encode())

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"  ✓ Dashboard running at http://127.0.0.1:{PORT}")
    print(f"  Press Ctrl+C to stop")

    # 延迟打开浏览器
    def open\_browser():
        time.sleep(0.5)
        webbrowser.open(f"http://127.0.0.1:{PORT}")
    threading.Thread(target=open\_browser, daemon=True).start()

    try:
        server.serve\_forever()
    except KeyboardInterrupt:
        print("\\n  Dashboard stopped.")
```

把 `\_launch\_dashboard` 函数引用加进 `wlbs\_scan.py`（import 方式或直接复制函数体）。

\---

## 任务五：轨迹自动上传（用户零感知）

### 位置

`opencraft/main.py` 第 1026 行，`living\_state.record\_experience(crystal)` 之后。

### 代码

```python
def \_auto\_upload\_trace(crystal, cfg):
    """
    任务结束后异步上传脱敏轨迹。
    - 只有配置了 hub.api\_key 的用户才上传
    - daemon 线程，失败静默，绝对不阻断主流程
    - 上传轨迹（事实），蒸馏在服务端发生
    """
    api\_key = cfg.get("hub.api\_key", "")
    hub\_url = cfg.get("hub.url", "")
    if not api\_key or not hub\_url:
        return

    def \_sanitize\_file(path: str) -> str:
        """文件名只保留扩展名类型，去掉路径和文件名。"""
        if not path: return ""
        ext = path.rsplit(".", 1)\[-1] if "." in path else "unknown"
        return f"\*.{ext}"

    def \_upload():
        try:
            import urllib.request, json as \_json
            trace = {
                "trajectory": \[
                    {
                        "turn":      step.turn,
                        "expert":    step.expert,
                        "file\_type": \_sanitize\_file(step.file),
                        "success":   step.success,
                        "passed":    step.passed,
                        "failed":    step.failed,
                    }
                    for step in crystal.trajectory
                ],
                "outcome":      crystal.outcome,
                "failure\_type": crystal.failure\_type,
                "turns\_used":   crystal.turns\_used,
                "final\_passed": crystal.final\_passed,
                "final\_failed": crystal.final\_failed,
                "fingerprint": {
                    "task\_type":          crystal.fingerprint.task\_type,
                    "language":           crystal.fingerprint.language,
                    "complexity\_level":   crystal.fingerprint.complexity\_level,
                    "complexity\_signals": crystal.fingerprint.complexity\_signals,
                },
            }
            body = \_json.dumps(trace, ensure\_ascii=False).encode()
            req  = urllib.request.Request(
                f"{hub\_url}/traces/upload",
                data=body,
                headers={"Content-Type": "application/json", "x-api-key": api\_key},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

    import threading
    threading.Thread(target=\_upload, daemon=True).start()
```

\---

## 任务六：服务端（`wlbs\_server.py`，完整版含积分）

```python
#!/usr/bin/env python3
"""
wlbs-scan 共享经验库服务端 v2（含积分系统）
部署：uvicorn wlbs\_server:app --host 0.0.0.0 --port 8765 --workers 2
"""
from \_\_future\_\_ import annotations
import json, secrets, time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter
from slowapi.util import get\_remote\_address
from pydantic import BaseModel

app     = FastAPI(title="wlbs Experience Hub")
limiter = Limiter(key\_func=get\_remote\_address)

STORAGE\_DIR   = Path("./hub\_data")
CRYSTALS\_PATH = STORAGE\_DIR / "shared\_crystals.jsonl"
TRACES\_PATH   = STORAGE\_DIR / "raw\_traces.jsonl"
KEYS\_PATH     = STORAGE\_DIR / "api\_keys.json"
POINTS\_PATH   = STORAGE\_DIR / "points.json"
STORAGE\_DIR.mkdir(parents=True, exist\_ok=True)

# ── Key 管理 ───────────────────────────────────────────
def \_load\_keys() -> dict:
    if not KEYS\_PATH.exists(): return {}
    return json.loads(KEYS\_PATH.read\_text(encoding="utf-8"))

def \_save\_keys(keys: dict):
    KEYS\_PATH.write\_text(json.dumps(keys, indent=2, ensure\_ascii=False), encoding="utf-8")

def \_verify\_key(api\_key: str) -> dict | None:
    if not api\_key: return None
    return \_load\_keys().get(api\_key)

def \_get\_tier(api\_key: str) -> str:
    info = \_verify\_key(api\_key)
    if not info: return "none"
    # 检查是否过期
    first\_used = info.get("first\_used\_at")
    if first\_used:
        elapsed\_days = (time.time() - float(first\_used)) / 86400
        if elapsed\_days > 30:
            return "expired"
    return info.get("plan", "free")

def add\_key(user: str, plan: str = "pro") -> str:
    """手动添加用户，返回 key。用户付款后执行。"""
    keys = \_load\_keys()
    key  = f"wlbs\_{plan\[:3]}\_{secrets.token\_hex(8)}"
    keys\[key] = {
        "user":         user,
        "plan":         plan,
        "created\_at":   datetime.now(timezone.utc).isoformat(),
        "first\_used\_at": None,   # 首次使用时记录，从这里开始计30天
    }
    \_save\_keys(keys)
    return key

def \_mark\_first\_use(api\_key: str):
    """首次使用时记录时间戳，开始计费。"""
    keys = \_load\_keys()
    if api\_key in keys and not keys\[api\_key].get("first\_used\_at"):
        keys\[api\_key]\["first\_used\_at"] = time.time()
        \_save\_keys(keys)

# ── 积分系统 ───────────────────────────────────────────
def \_load\_points() -> dict:
    if not POINTS\_PATH.exists(): return {}
    return json.loads(POINTS\_PATH.read\_text(encoding="utf-8"))

def \_save\_points(pts: dict):
    POINTS\_PATH.write\_text(json.dumps(pts, indent=2, ensure\_ascii=False), encoding="utf-8")

def \_add\_points(api\_key: str, amount: float):
    """给用户加积分（服务端计算，客户端无法调用）。"""
    pts = \_load\_points()
    pts\[api\_key] = round(pts.get(api\_key, 0.0) + amount, 3)
    \_save\_points(pts)

def \_get\_points(api\_key: str) -> float:
    return \_load\_points().get(api\_key, 0.0)

def \_calculate\_points(trace: dict, tier: str) -> float:
    """根据轨迹质量和用户 tier 计算积分。"""
    outcome    = trace.get("outcome", "failure")
    confidence = float(trace.get("confidence\_score", 0))
    points     = 0.0

    multiplier = 0.5 if tier == "pro" else 0.2  # Pro系数0.5，免费0.2

    if outcome == "success":
        points += 1.0 \* multiplier
        if confidence >= 0.8:
            points += (0.3 if tier == "pro" else 0.1)
    elif outcome in ("failure", "partial"):
        points += 0.1 \* multiplier  # 失败任务也有价值

    return round(points, 3)

# ── 轨迹验证 ───────────────────────────────────────────
def \_validate\_trace(trace: dict) -> tuple\[bool, str]:
    turns    = int(trace.get("turns\_used", 0))
    outcome  = trace.get("outcome", "")
    f\_passed = int(trace.get("final\_passed", 0))
    f\_failed = int(trace.get("final\_failed", 0))
    traj     = trace.get("trajectory", \[])

    if not (1 <= turns <= 15):
        return False, f"turns\_used={turns} invalid"
    if outcome not in ("success", "failure", "partial"):
        return False, "invalid outcome"
    if outcome == "success" and f\_failed > 0:
        return False, "success but final\_failed>0"
    if len(traj) == 0:
        return False, "empty trajectory"

    pytest\_steps = \[s for s in traj if s.get("expert") in ("pytest", "vitest")]
    if outcome == "success" and len(pytest\_steps) >= 2:
        first = int(pytest\_steps\[0].get("passed", 0))
        last  = int(pytest\_steps\[-1].get("passed", 0))
        if last <= first:
            return False, "success but no test improvement"

    return True, "ok"

# ── 服务端蒸馏 ─────────────────────────────────────────
def \_distill\_on\_server(trace: dict) -> dict | None:
    outcome  = trace.get("outcome", "failure")
    fp       = trace.get("fingerprint", {})
    traj     = trace.get("trajectory", \[])
    turns    = int(trace.get("turns\_used", 0))
    f\_passed = int(trace.get("final\_passed", 0))
    failure\_type = trace.get("failure\_type", "")

    write\_steps  = \[s for s in traj if s.get("expert") in ("implement","write","edit")]
    read\_steps   = \[s for s in traj if s.get("expert") == "read"]
    pytest\_steps = \[s for s in traj if s.get("expert") in ("pytest","vitest")]

    root\_cause\_turn = 0
    prev\_failed = None
    for s in pytest\_steps:
        failed = int(s.get("failed", 0))
        if prev\_failed is not None and prev\_failed > 0 and failed == 0:
            root\_cause\_turn = s.get("turn", 0)
            break
        prev\_failed = failed

    rule = ""
    if outcome == "success":
        read\_types  = \[s.get("file\_type","") for s in read\_steps]
        write\_types = \[s.get("file\_type","") for s in write\_steps]
        if read\_types and write\_types and read\_types\[0] != write\_types\[0]:
            rule = (f"{fp.get('task\_type','bug\_fix')} ({fp.get('language','python')}): "
                   f"fix landed in different file type than initial read — "
                   f"check upstream dependencies first. Resolved in {turns} turns.")
        elif turns <= 3:
            rule = (f"{fp.get('task\_type','bug\_fix')} ({fp.get('language','python')}): "
                   f"fast fix in {turns} turns — targeted single-file approach effective.")
        else:
            rule = (f"{fp.get('task\_type','bug\_fix')} ({fp.get('language','python')}): "
                   f"resolved in {turns} turns with {f\_passed} tests passing.")
    elif failure\_type:
        rule = (f"{fp.get('task\_type','bug\_fix')} ({fp.get('language','python')}): "
               f"'{failure\_type}' not resolved in {turns} turns — "
               f"consider different approach if same pattern recurs.")

    if not rule:
        return None

    confidence = round(
        0.5 + (0.3 if outcome=="success" else 0.0) + (0.2 if turns<=5 else 0.0), 2
    )

    return {
        "rule":              rule,
        "rule\_type":         "positive" if outcome=="success" else "negative",
        "outcome":           outcome,
        "task\_type":         fp.get("task\_type",""),
        "language":          fp.get("language",""),
        "complexity\_signals": fp.get("complexity\_signals",\[]),
        "turns\_used":        turns,
        "root\_cause\_turn":   root\_cause\_turn,
        "confidence":        confidence,
        "confidence\_score":  confidence,
        "contributed\_at":    datetime.now(timezone.utc).isoformat(),
    }

# ── HTTP 端点 ──────────────────────────────────────────
@app.get("/health")
def health():
    total = 0
    if CRYSTALS\_PATH.exists():
        total = sum(1 for l in CRYSTALS\_PATH.read\_text(encoding="utf-8").splitlines() if l.strip())
    return {"status": "ok", "total\_crystals": total}

@app.post("/traces/upload")
@limiter.limit("60/hour")   # 限频：每小时最多60次上传
async def upload\_trace(request: Request, x\_api\_key: Optional\[str] = Header(None)):
    info = \_verify\_key(x\_api\_key or "")
    if not info:
        raise HTTPException(401, "Invalid API key")

    \_mark\_first\_use(x\_api\_key)
    tier  = \_get\_tier(x\_api\_key)
    trace = await request.json()

    valid, reason = \_validate\_trace(trace)
    if not valid:
        return {"accepted": False, "reason": reason}

    rule = \_distill\_on\_server(trace)
    if rule:
        # 把 confidence\_score 写回 trace 供积分计算用
        trace\["confidence\_score"] = rule.get("confidence", 0)
        with CRYSTALS\_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rule, ensure\_ascii=False) + "\\n")

    # 计算并加积分
    pts = \_calculate\_points(trace, tier)
    \_add\_points(x\_api\_key, pts)

    return {"accepted": True, "rule\_generated": rule is not None, "points\_earned": pts}

@app.get("/crystals/download")
@limiter.limit("30/hour")   # 限频：每小时最多30次下载
async def download\_crystals(request: Request, x\_api\_key: Optional\[str] = Header(None)):
    tier = \_get\_tier(x\_api\_key or "")
    if tier == "none":
        raise HTTPException(401, "Pro subscription required for shared experience library")
    if tier == "expired":
        raise HTTPException(403, "Key expired. Please renew at kaiwucl.com/pro")

    \_mark\_first\_use(x\_api\_key)

    if not CRYSTALS\_PATH.exists():
        return {"crystals": \[], "total": 0}

    lines = \[l.strip() for l in CRYSTALS\_PATH.read\_text(encoding="utf-8").splitlines() if l.strip()]
    crystals = \[]
    for line in lines\[-200:]:   # Pro无数量限制，但限频
        try:
            crystals.append(json.loads(line))
        except Exception:
            continue

    return {"crystals": crystals, "total": len(lines)}

@app.get("/account/status")
async def account\_status(x\_api\_key: Optional\[str] = Header(None)):
    info = \_verify\_key(x\_api\_key or "")
    if not info:
        raise HTTPException(401, "Invalid API key")

    \_mark\_first\_use(x\_api\_key)
    tier       = \_get\_tier(x\_api\_key)
    points     = \_get\_points(x\_api\_key)
    first\_used = info.get("first\_used\_at")
    expires\_at = None
    if first\_used:
        expires\_ts = float(first\_used) + 30 \* 86400
        expires\_at = datetime.fromtimestamp(expires\_ts, tz=timezone.utc).isoformat()

    return {
        "tier":           tier,
        "points":         round(points, 1),
        "points\_needed":  100,
        "key\_expires\_at": expires\_at,
        "resets\_at":      "December 31",
    }

@app.post("/account/redeem")
async def redeem\_key(request: Request, x\_api\_key: Optional\[str] = Header(None)):
    """用100积分换1个新key（30天）。"""
    info = \_verify\_key(x\_api\_key or "")
    if not info:
        raise HTTPException(401, "Invalid API key")

    body  = await request.json()
    email = str(body.get("email", "")).strip()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email required")

    points = \_get\_points(x\_api\_key)
    if points < 100:
        return {"success": False, "message": f"Need 100 points, you have {points:.1f}"}

    # 扣分并生成新key
    pts = \_load\_points()
    pts\[x\_api\_key] = round(pts.get(x\_api\_key, 0) - 100, 3)
    \_save\_points(pts)

    new\_key = add\_key(email, plan="pro")
    # 实际发key给用户（早期手动，后期接邮件服务）
    # TODO: 接入邮件发送服务
    return {
        "success": True,
        "message": f"Key generated! Check {email} within 24h (manual delivery in early access).",
        "new\_key": new\_key  # 早期直接返回，后期改为邮件发送
    }
```

\---

## 文件清单

|操作|文件|说明|
|-|-|-|
|修改|`wlbs\_scan.py`|加 `--status` / `--advise` / `--dashboard` 参数和逻辑|
|新建|`wlbs\_dashboard.py`|Dashboard HTML 构建和本地服务器|
|新建|`wlbs\_pytest\_plugin.py`|pytest 自动记录插件|
|修改|`opencraft/main.py`|加 `\_auto\_upload\_trace()`|
|新建|`wlbs\_server.py`|VPS 服务端（含积分）|
|修改|`pyproject.toml`|注册 pytest 插件 + server 可选依赖|

**`pyproject.toml` 追加：**

```toml
\[project.entry-points."pytest11"]
wlbs = "wlbs\_pytest\_plugin"

\[project.optional-dependencies]
server = \["fastapi>=0.100", "uvicorn>=0.20", "pydantic>=2.0", "slowapi>=0.1.9"]
```

\---

## 执行顺序

```
Day 1    wlbs\_scan.py：--status / --advise
         wlbs\_pytest\_plugin.py：自动记录钩子
         验收：跑 pytest 后自动有 world-line 记录

Day 2    wlbs\_server.py：含积分系统
         VPS 部署，测试 /health / /account/status
         添加第一个测试用 key

Day 3    opencraft/main.py：\_auto\_upload\_trace 接入
         wlbs\_scan.py：--dashboard 命令
         wlbs\_dashboard.py：热力图界面

Day 4    端到端测试全流程
         积分累积验证（上传→加分→查询→兑换）
         限频测试（超过60次/小时应返回429）
```

\---

## 验收标准

```bash
# 1. 自动记录（无需手动）
pytest tests/
wlbs-scan . --history
# 有新事件，不需要用户执行任何 wlbs 命令

# 2. 状态查询
wlbs-scan . --status --api-key wlbs\_pro\_xxx
# 显示风险文件 + 积分 + 过期时间

# 3. Dashboard
wlbs-scan . --dashboard --api-key wlbs\_pro\_xxx
# 浏览器自动打开，热力图显示，积分可见，兑换入口可用

# 4. 积分验证
# 上传10个成功任务后
curl -H "x-api-key: wlbs\_pro\_xxx" http://VPS:8765/account/status
# points 字段 ≈ 5.0（10 × 0.5）

# 5. 限频
# 连续发61次上传请求
# 第61次返回 429 Too Many Requests

# 6. Key过期
# 修改 first\_used\_at 为31天前
# /crystals/download 返回 403 expired
```

\---

> 版本：v3.0 · 2026-03-26
> 核心变化：积分系统 · 自动记录 · 热力图Dashboard · 限频保护 · Key首次使用计费

