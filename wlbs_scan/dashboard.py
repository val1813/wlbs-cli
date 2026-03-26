from __future__ import annotations

import json
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


PORT = 7890


def build_dashboard_html(graph_data: dict, account_data: dict | None) -> str:
    nodes = graph_data.get("nodes", [])
    sings = set(graph_data.get("singularities", []))
    task_mem = graph_data.get("task_memory", {})
    heatmap_rows = ""
    for node in nodes[:50]:
        kappa = float(node.get("curvature", 0))
        nid = node.get("id", "")
        failures = int(node.get("failures", 0))
        is_sing = nid in sings
        pct = int(kappa * 100)
        if kappa >= 0.7:
            color = f"rgba(248,81,73,{0.4 + kappa * 0.6:.2f})"
            text_color = "#f85149"
            badge = '<span class="badge-sing">ROOT CAUSE</span>' if is_sing else '<span class="badge-high">HIGH</span>'
        elif kappa >= 0.4:
            color = f"rgba(227,179,65,{0.3 + kappa * 0.5:.2f})"
            text_color = "#e3b341"
            badge = '<span class="badge-med">MED</span>'
        else:
            color = "rgba(63,185,80,0.15)"
            text_color = "#3fb950"
            badge = '<span class="badge-low">LOW</span>'
        warn = ""
        if is_sing:
            warn = '<div class="warn-box">Likely root cause - investigate before touching downstream files</div>'
        heatmap_rows += f"""
        <div class="node-card" style="border-left:4px solid {text_color}; background:{color}">
          <div class="node-header"><span class="node-id">{nid}</span>{badge}</div>
          <div class="node-bar-wrap"><div class="node-bar" style="width:{pct}%; background:{text_color}"></div></div>
          <div class="node-meta">kappa = {kappa:.3f} / failures = {failures}</div>
          {warn}
        </div>"""

    account_html = ""
    if account_data:
        points = float(account_data.get("points", 0))
        tier = account_data.get("tier", "free")
        expires = (account_data.get("key_expires_at", "") or "")[:10]
        pct_points = min(100, int(points))
        account_html = f"""
        <div class="account-panel">
          <h2>Account</h2>
          <div class="account-row"><span class="acc-label">Plan</span><span class="acc-value tier-{tier}">{tier.upper()}</span></div>
          <div class="account-row"><span class="acc-label">Points</span><span class="acc-value">{points:.1f} / 100</span></div>
          <div class="points-bar-wrap"><div class="points-bar" style="width:{pct_points}%"></div></div>
          <div class="points-hint">100 points = 1 key (30 days). Resets every December.</div>
          {"<div class='account-row'><span class='acc-label'>Key expires</span><span class='acc-value'>" + expires + "</span></div>" if expires else ""}
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
        account_html = """
        <div class="account-panel">
          <h2>Account</h2>
          <p class="no-key">No API key configured.</p>
        </div>"""

    recent_tasks = ""
    for tid, task in sorted(task_mem.items(), reverse=True)[:5]:
        icon = "PASS" if task.get("result") == "pass" else "FAIL"
        color = "#3fb950" if task.get("result") == "pass" else "#f85149"
        target = task.get("final_target", "")
        ts = (task.get("ts", "") or "")[:16]
        recent_tasks += f"""
        <div class="task-row">
          <span style="color:{color}">{icon}</span>
          <span class="task-id">{tid}</span>
          <span class="task-target">-> {target}</span>
          <span class="task-ts">{ts}</span>
        </div>"""
    if not recent_tasks:
        recent_tasks = '<div class="no-tasks">No task history yet.</div>'
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>wlbs-scan Dashboard</title>
<style>
body{{font-family:Segoe UI,sans-serif;background:#0d1117;color:#c9d1d9;font-size:13px;margin:0}}
.topbar{{background:#161b22;border-bottom:1px solid #30363d;padding:16px 24px;display:flex;gap:16px;align-items:center}}
.topbar h1{{font-size:20px;color:#58a6ff;margin:0}} .sub{{color:#8b949e;font-size:12px}} .refresh{{margin-left:auto}}
.layout{{display:grid;grid-template-columns:1fr 320px;height:calc(100vh - 57px)}}
.main,.sidebar{{overflow:auto;padding:24px}} .sidebar{{background:#161b22;border-left:1px solid #30363d}}
.node-card{{border-radius:8px;padding:12px 16px;margin-bottom:10px}}
.node-bar-wrap{{background:rgba(0,0,0,.3);border-radius:3px;height:5px;margin:8px 0}} .node-bar{{height:5px;border-radius:3px}}
.node-header{{display:flex;gap:8px;align-items:center}} .node-id{{font-family:Consolas,monospace;font-weight:600}}
.warn-box{{margin-top:8px;padding:6px 10px;background:rgba(248,81,73,.1);border:1px solid rgba(248,81,73,.3);border-radius:4px;font-size:11px;color:#f85149}}
.badge-sing,.badge-high,.badge-med,.badge-low{{font-size:10px;padding:2px 6px;border-radius:3px}}
.badge-sing{{background:#3a1a5c;color:#d4b0f0;border:1px solid #7f77dd}} .badge-high{{background:rgba(248,81,73,.2);color:#f85149}} .badge-med{{background:rgba(227,179,65,.2);color:#e3b341}} .badge-low{{background:rgba(63,185,80,.1);color:#3fb950}}
.account-row,.task-row{{display:flex;gap:8px;justify-content:space-between;margin:6px 0}} .task-id{{font-family:Consolas,monospace;font-size:10px;flex:1;color:#8b949e}}
.points-bar-wrap{{background:#21262d;border-radius:4px;height:8px;margin:8px 0}} .points-bar{{height:8px;border-radius:4px;background:linear-gradient(90deg,#58a6ff,#3fb950)}}
.redeem-row{{display:flex;gap:8px}} .redeem-row input{{flex:1;background:#21262d;border:1px solid #30363d;color:#c9d1d9;padding:6px 10px;border-radius:6px}}
</style></head>
<body><div class="topbar"><h1>wlbs-scan</h1><span class="sub">Risk dashboard</span><button class="refresh" onclick="location.reload()">Refresh</button></div>
<div class="layout"><div class="main"><h2>File Risk Heatmap</h2>{heatmap_rows}</div><div class="sidebar">{account_html}<h2>Recent Tasks</h2>{recent_tasks}</div></div>
<script>
function redeemKey(){{
  const email=document.getElementById('redeemInput').value.trim();
  const msg=document.getElementById('redeemMsg');
  if(!email){{msg.textContent='Please enter an email.';return;}}
  fetch('/redeem',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email}})}})
    .then(r=>r.json()).then(d=>msg.textContent=d.message||'Done').catch(()=>msg.textContent='Request failed');
}}
setTimeout(()=>location.reload(),10000);
</script></body></html>"""


def launch_dashboard(root: Path, graph_getter, account_getter, hub_url: str, api_key: str):
    def get_data():
        return graph_getter()

    def get_account():
        return account_getter() if api_key else None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):
            html = build_dashboard_html(get_data(), get_account())
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        def do_POST(self):
            if self.path != "/redeem":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            from .cloud import cmd_redeem
            try:
                result = cmd_redeem(body.get("email", ""), api_key=api_key, hub_url=hub_url)
            except Exception as exc:
                result = {"message": f"Error: {exc}"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))

    server = HTTPServer(("127.0.0.1", PORT), Handler)

    def open_browser():
        time.sleep(0.5)
        webbrowser.open(f"http://127.0.0.1:{PORT}")

    threading.Thread(target=open_browser, daemon=True).start()
    print(f"  Dashboard running at http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")
