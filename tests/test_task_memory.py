from __future__ import annotations

import json
import shutil
from pathlib import Path

import wlbs_scan as ws


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


def reset_wlbs(root: Path):
    wlbs_dir = root / ".wlbs"
    if wlbs_dir.exists():
        shutil.rmtree(wlbs_dir)


def prepare_graph(root: Path):
    graph = ws.build_graph(root)
    store = ws.WorldLineStore(root)
    ws.compute_curvature(graph, store=store)
    return graph, store


def test_record_outcome_writes_task_memory():
    reset_wlbs(DEMO)
    graph, store = prepare_graph(DEMO)
    record = ws.build_task_record(graph, store, "rbac", "roles", "pass", tests_before="4/6", tests_after="6/6")
    store.record_outcome(record)
    data = json.loads((DEMO / ".wlbs" / "world_lines.json").read_text(encoding="utf-8"))
    assert "task_memory" in data
    assert record["task_id"] in data["task_memory"]


def test_task_memory_schema_complete():
    reset_wlbs(DEMO)
    graph, store = prepare_graph(DEMO)
    record = ws.build_task_record(graph, store, "rbac", "roles", "pass", tests_before="4/6", tests_after="6/6")
    required = {
        "task_id", "ts", "symptom", "wlbs_suggested_target", "final_target",
        "suggestion_was_followed", "result", "tests_before", "tests_after",
        "test_delta", "detail", "symptom_feature_vector",
    }
    assert required.issubset(record.keys())


def test_suggestion_was_followed_detection():
    reset_wlbs(DEMO)
    store = ws.WorldLineStore(DEMO)
    for i in range(3):
        store.record_failure("rbac", f"memory failure {i + 1}")
    graph = ws.build_graph(DEMO)
    ws.compute_curvature(graph, store=store)
    record = ws.build_task_record(graph, store, "rbac", "roles", "pass")
    assert record["suggestion_was_followed"] is True


def test_routing_stats_update():
    reset_wlbs(DEMO)
    store = ws.WorldLineStore(DEMO)
    for i in range(3):
        store.record_failure("rbac", f"memory failure {i + 1}")
    graph = ws.build_graph(DEMO)
    ws.compute_curvature(graph, store=store)
    store.record_outcome(ws.build_task_record(graph, store, "rbac", "roles", "pass", tests_before="4/6", tests_after="6/6"))
    store.record_outcome(ws.build_task_record(graph, store, "rbac", "rbac", "fail", tests_before="4/6", tests_after="4/6"))
    assert store.routing_stats["total_tasks"] == 2
    assert store.routing_stats["suggestion_follow_rate"] == 0.5
    assert store.routing_stats["suggestion_accuracy"] == 0.5


def test_task_id_auto_generated():
    reset_wlbs(DEMO)
    graph, store = prepare_graph(DEMO)
    record = ws.build_task_record(graph, store, "rbac", "roles", "pass")
    assert record["task_id"].startswith("T")


def test_backward_compatible_no_task_memory(tmp_path: Path):
    wlbs_dir = tmp_path / ".wlbs"
    wlbs_dir.mkdir(parents=True, exist_ok=True)
    (wlbs_dir / "world_lines.json").write_text(
        json.dumps({
            "version": "0.5.0",
            "world_lines": {
                "rbac": {"events": [{"ts": "2026-03-26T00:00:00+00:00", "kind": "failure", "node": "rbac", "detail": "old"}]}
            },
        }),
        encoding="utf-8",
    )
    store = ws.WorldLineStore(tmp_path)
    assert store.get("rbac").failure_count == 1
    assert store.task_memory == {}
    assert store.routing_stats["total_tasks"] == 0
