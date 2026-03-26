from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import wlbs_scan as ws


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


def reset_wlbs(root: Path):
    wlbs_dir = root / ".wlbs"
    if wlbs_dir.exists():
        shutil.rmtree(wlbs_dir, ignore_errors=True)


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def prepare_demo_store():
    reset_wlbs(DEMO)
    store = ws.WorldLineStore(DEMO)
    for i in range(3):
        store.record_failure("rbac", f"policy failure {i + 1}")
    graph = ws.build_graph(DEMO)
    ws.compute_curvature(graph, store=store)
    return graph, store


def test_routing_confidence_increases_on_pass_followed():
    graph, store = prepare_demo_store()
    record = ws.build_task_record(graph, store, "rbac", "roles", "pass", tests_before="4/6", tests_after="6/6")
    store.record_outcome(record)
    assert store.routing_policy["rbac->roles"]["confidence"] > 0.75


def test_routing_confidence_decreases_on_fail_followed():
    graph, store = prepare_demo_store()
    record = ws.build_task_record(graph, store, "rbac", "roles", "fail", tests_before="4/6", tests_after="4/6")
    store.record_outcome(record)
    assert store.routing_policy["rbac->roles"]["confidence"] < 0.75


def test_cosine_sim_identical_vectors():
    assert round(ws.cosine_sim([1.0, 0.5], [1.0, 0.5]), 6) == 1.0


def test_similar_task_matching_by_structure_not_name(tmp_path: Path):
    write(
        tmp_path / "registry.py",
        """
        TABLE = {"editor": ["read"]}

        def get_entry(role):
            if not isinstance(role, str):
                raise TypeError("role must be string")
            return TABLE[role]
        """,
    )
    write(
        tmp_path / "payment_handler.py",
        """
        import registry

        def handle():
            return registry.get_entry("admin")
        """,
    )
    store = ws.WorldLineStore(tmp_path)
    graph = ws.build_graph(tmp_path)
    ws.compute_curvature(graph, store=store)
    # Seed historical task from demo with different names but similar structure.
    demo_graph, demo_store = prepare_demo_store()
    hist = ws.build_task_record(demo_graph, demo_store, "rbac", "roles", "pass", detail="missing key in registry")
    store.task_memory[hist["task_id"]] = hist
    similar = ws.find_similar_past_tasks("payment_handler", graph, store.task_memory, min_similarity=0.6)
    assert similar
    assert similar[0]["final_target"] == "roles"


def test_dissimilar_task_not_matched(tmp_path: Path):
    write(
        tmp_path / "math_utils.py",
        """
        def add(a, b):
            return a + b
        """,
    )
    write(
        tmp_path / "api.py",
        """
        import math_utils

        def run():
            return math_utils.add(1, 2)
        """,
    )
    store = ws.WorldLineStore(tmp_path)
    graph = ws.build_graph(tmp_path)
    ws.compute_curvature(graph, store=store)
    demo_graph, demo_store = prepare_demo_store()
    hist = ws.build_task_record(demo_graph, demo_store, "rbac", "roles", "pass", detail="missing key in registry")
    store.task_memory[hist["task_id"]] = hist
    similar = ws.find_similar_past_tasks("api", graph, store.task_memory, min_similarity=0.98)
    assert similar == []


def test_similar_tasks_appear_in_advise_json():
    graph, store = prepare_demo_store()
    hist = ws.build_task_record(graph, store, "rbac", "roles", "pass", detail="missing key in registry")
    store.record_outcome(hist)
    advisory = ws.build_advisory(graph, store, "rbac")
    assert advisory["advisory"]["similar_past_tasks"]


def test_successful_similar_tasks_raise_advisory_confidence(tmp_path: Path):
    write(
        tmp_path / "registry.py",
        """
        TABLE = {"editor": ["read"]}

        def get_entry(role):
            return TABLE[role]
        """,
    )
    write(
        tmp_path / "payment_handler.py",
        """
        import registry

        def handle():
            return registry.get_entry("admin")
        """,
    )
    store = ws.WorldLineStore(tmp_path)
    store.record_failure("payment_handler", "missing key")
    graph = ws.build_graph(tmp_path)
    ws.compute_curvature(graph, store=store)
    base_conf = ws.build_advisory(graph, store, "payment_handler")["advisory"]["primary_suggestion"]["confidence"]

    demo_graph, demo_store = prepare_demo_store()
    hist = ws.build_task_record(demo_graph, demo_store, "rbac", "roles", "pass", detail="missing key in registry")
    store.record_outcome(hist)
    ws.compute_curvature(graph, store=store)
    learned_conf = ws.build_advisory(graph, store, "payment_handler")["advisory"]["primary_suggestion"]["confidence"]

    assert learned_conf > base_conf
