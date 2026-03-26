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
        shutil.rmtree(wlbs_dir)


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_behavioral_distance_demo():
    reset_wlbs(DEMO)
    graph = ws.build_graph(DEMO)
    store = ws.WorldLineStore(DEMO)
    ws.compute_curvature(graph, store=store)
    assert ws.behavioral_distance(graph, "roles", "rbac") == 1


def test_upstream_singularity_matches_paper_definition():
    reset_wlbs(DEMO)
    store = ws.WorldLineStore(DEMO)
    for i in range(3):
        store.record_failure("rbac", f"demo failure {i + 1}")
    graph = ws.build_graph(DEMO)
    ws.compute_curvature(graph, store=store)
    report = ws.report_json(graph, store)
    nodes = {item["id"]: item for item in report["nodes"]}
    assert nodes["roles"]["is_singularity"] is True
    assert nodes["roles"]["failures"] == 0
    assert nodes["roles"]["downstream_failures"] >= 3
    assert nodes["rbac"]["is_singularity"] is False


def test_pytest_integration_records_demo_failures():
    reset_wlbs(DEMO)
    store = ws.WorldLineStore(DEMO)
    graph = ws.build_graph(DEMO)
    result = ws._run_pytest_and_record(DEMO / "tests", DEMO, store, graph.file_to_module)
    assert result["passed"] == 4
    assert result["failed"] == 2
    lines = store.get("demo")
    assert lines.failure_count == 2

def test_resolution_decay_context_places_roles_in_near_tier():
    reset_wlbs(DEMO)
    store = ws.WorldLineStore(DEMO)
    for i in range(3):
        store.record_failure("rbac", f"context failure {i + 1}")
    graph = ws.build_graph(DEMO)
    ws.compute_curvature(graph, store=store)
    ctx = ws.assemble_resolution_context(graph, store, "rbac")
    near_ids = {item["id"] for item in ctx["tiers"]["near"]}
    assert "rbac" in near_ids
    assert "roles" in near_ids
    assert ctx["tier_counts"]["near"] >= 2


def test_repair_suggestion_routes_rbac_to_roles():
    reset_wlbs(DEMO)
    store = ws.WorldLineStore(DEMO)
    for i in range(3):
        store.record_failure("rbac", f"suggest failure {i + 1}")
    graph = ws.build_graph(DEMO)
    ws.compute_curvature(graph, store=store)
    suggestion = ws.build_repair_suggestion(graph, store, "rbac")
    assert suggestion["recommended_target"] == "roles"
    assert any("singularity" in step for step in suggestion["reasoning_chain"])


def test_js_graph_support(tmp_path: Path):
    write(
        tmp_path / "core.js",
        """
        export function decodeRole(role) {
          return role.toUpperCase();
        }
        """,
    )
    write(
        tmp_path / "api.js",
        """
        import { decodeRole } from "./core.js";

        export function getRole(role) {
          return decodeRole(role);
        }
        """,
    )
    graph = ws.build_graph(tmp_path, lang="js")
    store = ws.WorldLineStore(tmp_path)
    ws.compute_curvature(graph, store=store)
    assert "core" in graph.nodes
    assert "api" in graph.nodes
    assert ws.behavioral_distance(graph, "core", "api") == 1


def test_worldline_accumulation_is_monotone_on_synthetic_target(tmp_path: Path):
    write(
        tmp_path / "heavy.py",
        """
        def normalize(values):
            total = 0
            for idx, value in enumerate(values):
                if idx % 2 == 0:
                    total += value
                else:
                    total -= value
                if total > 50:
                    total -= 3
                if total < -50:
                    total += 5
            return total
        """,
    )
    write(
        tmp_path / "bridge.py",
        """
        import heavy

        def proxy(values):
            return heavy.normalize(values)
        """,
    )
    write(
        tmp_path / "symptom.py",
        """
        import bridge

        def do_work():
            return bridge.proxy([1, 2, 3])
        """,
    )
    reset_wlbs(tmp_path)
    store = ws.WorldLineStore(tmp_path)
    values = []
    for i in range(5):
        graph = ws.build_graph(tmp_path)
        ws.compute_curvature(graph, store=store)
        report = ws.report_json(graph, store)
        nodes = {item["id"]: item for item in report["nodes"]}
        values.append(nodes["symptom.do_work"]["curvature"])
        if i < 4:
            store.record_failure("symptom.do_work", f"synthetic failure {i + 1}")
    assert all(values[i] < values[i + 1] for i in range(len(values) - 1))
