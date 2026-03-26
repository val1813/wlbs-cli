from __future__ import annotations

import json
import shutil
from pathlib import Path

import wlbs_scan as ws
from wlbs_scan.dashboard import build_dashboard_html


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


def reset_wlbs(root: Path):
    shutil.rmtree(root / ".wlbs", ignore_errors=True)


def prepare_demo():
    reset_wlbs(DEMO)
    store = ws.WorldLineStore(DEMO)
    for i in range(3):
        store.record_failure("rbac", f"product failure {i + 1}")
    graph = ws.build_graph(DEMO)
    ws.compute_curvature(graph, store=store)
    return graph, store


def test_write_auto_advice_creates_markdown():
    graph, store = prepare_demo()
    ws.write_auto_advice(graph, store, DEMO, api_key="", hub_url="http://127.0.0.1:8765")
    advice = DEMO / ".wlbs" / "current_advice.md"
    assert advice.exists()
    text = advice.read_text(encoding="utf-8")
    assert "Likely Root Causes" in text
    assert "roles" in text


def test_status_json_source_still_contains_task_memory():
    graph, store = prepare_demo()
    record = ws.build_task_record(graph, store, "rbac", "roles", "pass", tests_before="4/6", tests_after="6/6")
    store.record_outcome(record)
    payload = ws.report_json(graph, store)
    assert payload["task_memory_count"] == 1


def test_dashboard_html_contains_heatmap_and_account_panel():
    graph, store = prepare_demo()
    payload = ws.report_json(graph, store)
    payload["task_memory"] = store.task_memory
    html = build_dashboard_html(payload, {"points": 12.5, "tier": "pro", "key_expires_at": "2026-04-25T00:00:00Z"})
    assert "File Risk Heatmap" in html
    assert "Account" in html
    assert "Redeem Key" in html


def test_write_auto_advice_can_include_shared_experience(monkeypatch):
    graph, store = prepare_demo()

    def fake_download(api_key=None, hub_url=None):
        return {"crystals": [{"rule": "missing key in registry - inspect upstream registry first"}]}

    monkeypatch.setattr("wlbs_scan.cloud.cmd_download_crystals", fake_download)
    ws.write_auto_advice(graph, store, DEMO, api_key="wlbs_pro_x", hub_url="http://111.231.112.127:8765")
    text = (DEMO / ".wlbs" / "current_advice.md").read_text(encoding="utf-8")
    assert "Shared Experience" in text
    assert "registry" in text
