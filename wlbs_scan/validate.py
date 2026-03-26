from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

from . import (
    __version__,
    WorldLineStore,
    _run_simple_tests_and_record,
    behavioral_distance,
    build_advisory,
    build_graph,
    build_repair_suggestion,
    build_task_record,
    compute_curvature,
    cosine_sim,
    export_html,
    find_similar_past_tasks,
    report_json,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _repo_validation_script() -> Path:
    return _project_root() / "validation" / "run_validation.py"


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def _make_demo(root: Path):
    _write(
        root / "roles.py",
        """
        PERMISSIONS = {
            "editor": ["read", "write"],
            "viewer": ["read"],
        }

        def get_permissions(role: str) -> list:
            if not isinstance(role, str):
                raise TypeError("role must be a string")
            if not role:
                raise KeyError(role)
            return PERMISSIONS[role]
        """,
    )
    _write(
        root / "rbac.py",
        """
        from roles import get_permissions

        class RBACManager:
            def __init__(self):
                self._cache = {}

            def check_access(self, user_role: str, required_perm: str) -> bool:
                if user_role not in self._cache:
                    self._cache[user_role] = get_permissions(user_role)
                return required_perm in self._cache[user_role]

            def grant_permissions(self, role: str, perm: str) -> None:
                perms = get_permissions(role)
                if perm not in perms:
                    perms.append(perm)
        """,
    )
    _write(
        root / "tests" / "test_rbac.py",
        """
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        from rbac import RBACManager

        def test_editor_read_access():
            assert RBACManager().check_access("editor", "read") is True

        def test_editor_write_access():
            assert RBACManager().check_access("editor", "write") is True

        def test_viewer_read_access():
            assert RBACManager().check_access("viewer", "read") is True

        def test_viewer_no_write():
            assert RBACManager().check_access("viewer", "write") is False

        def test_admin_access():
            assert RBACManager().check_access("admin", "read") is True

        def test_grant_permissions():
            RBACManager().grant_permissions("admin", "delete")
        """,
    )


def _make_monotone_project(root: Path):
    _write(
        root / "heavy.py",
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
    _write(
        root / "bridge.py",
        """
        import heavy

        def proxy(values):
            return heavy.normalize(values)
        """,
    )
    _write(
        root / "symptom.py",
        """
        import bridge

        def do_work():
            return bridge.proxy([1, 2, 3])
        """,
    )


def _make_js_project(root: Path):
    _write(root / "core.js", 'export function decodeRole(role) { return role.toUpperCase(); }\n')
    _write(root / "api.js", 'import { decodeRole } from "./core.js";\nexport function getRole(role) { return decodeRole(role); }\n')


def _measure(root: Path, repeats: int = 6, lang: str = "python") -> dict:
    runs = []
    for _ in range(repeats):
        store = WorldLineStore(root)
        t0 = time.perf_counter()
        graph = build_graph(root, lang=lang)
        compute_curvature(graph, store=store)
        runs.append((time.perf_counter() - t0) * 1000)
    return {
        "avg": sum(runs) / len(runs),
        "min": min(runs),
        "max": max(runs),
    }


def _reset(root: Path):
    shutil.rmtree(root / ".wlbs", ignore_errors=True)


def _run_internal_validation() -> dict:
    results = []
    with tempfile.TemporaryDirectory(prefix="wlbs_validate_") as tmp:
        demo = Path(tmp) / "demo"
        demo.mkdir(parents=True, exist_ok=True)
        _make_demo(demo)

        stats = _measure(demo, repeats=8)
        results.append(("1", stats["avg"] < 60, f"avg={stats['avg']:.2f}ms max={stats['max']:.2f}ms"))

        scale_root = Path(tmp) / "scale"
        scale_root.mkdir(parents=True, exist_ok=True)
        for i in range(60):
            _write(scale_root / f"mod_{i}.py", f"def work_{i}(x):\n    return x + {i}\n")
        scale = _measure(scale_root, repeats=4)
        results.append(("1b", scale["avg"] < 400, f"avg={scale['avg']:.2f}ms max={scale['max']:.2f}ms"))

        _reset(demo)
        store = WorldLineStore(demo)
        graph = build_graph(demo)
        compute_curvature(graph, store=store)
        results.append(("2", behavioral_distance(graph, "roles", "rbac") == 1, "d=1"))

        for i in range(3):
            store.record_failure("rbac", f"failure {i + 1}")
        graph = build_graph(demo)
        compute_curvature(graph, store=store)
        report = report_json(graph, store)
        nodes = {n["id"]: n for n in report["nodes"]}
        results.append(("3", nodes["roles"]["is_singularity"], "roles singularity"))

        mono = Path(tmp) / "mono"
        mono.mkdir(parents=True, exist_ok=True)
        _make_monotone_project(mono)
        _reset(mono)
        store2 = WorldLineStore(mono)
        series = []
        for i in range(5):
            graph2 = build_graph(mono)
            compute_curvature(graph2, store=store2)
            node = {n["id"]: n for n in report_json(graph2, store2)["nodes"]}["symptom.do_work"]
            series.append(node["curvature"])
            if i < 4:
                store2.record_failure("symptom.do_work", f"failure {i + 1}")
        results.append(("4", all(series[i] < series[i + 1] for i in range(len(series) - 1)), f"series={series}"))

        _reset(demo)
        store = WorldLineStore(demo)
        graph = build_graph(demo)
        simple = _run_simple_tests_and_record(demo / "tests", demo, store, graph.file_to_module)
        results.append(("5", simple["passed"] == 4 and simple["failed"] == 2, f"passed={simple['passed']} failed={simple['failed']}"))

        js = Path(tmp) / "js"
        js.mkdir(parents=True, exist_ok=True)
        _make_js_project(js)
        js_graph = build_graph(js, lang="js")
        results.append(("6", behavioral_distance(js_graph, "core", "api") == 1, "d(core, api)=1"))

        html = export_html(graph, store, Path(tmp) / "report.html")
        results.append(("7", html > 0, f"nodes={html}"))

        results.append(("8", simple["failed"] == 2 and simple["passed"] == 4, "2 failed, 4 passed"))

        ctx = build_repair_suggestion(graph, store, "rbac")["resolution_context"]
        near_ids = {item["id"] for item in ctx["tiers"]["near"]}
        results.append(("9", {"roles", "rbac"}.issubset(near_ids), f"near={sorted(near_ids)}"))

        suggestion = build_repair_suggestion(graph, store, "rbac")
        results.append(("10", suggestion["recommended_target"] == "roles", f"target={suggestion['recommended_target']}"))

        advisory = build_advisory(graph, store, "rbac")
        primary = advisory["advisory"]["primary_suggestion"]
        results.append(("11", advisory["schema"] == "wlbs-advisory-v1" and primary["tone"] == "suggestion", f"confidence={primary['confidence']:.3f}"))

        record = build_task_record(graph, store, "rbac", "roles", "pass", tests_before="4/6", tests_after="6/6")
        store.record_outcome(record)
        results.append(("12", store.routing_stats["total_tasks"] == 1, f"tasks={store.routing_stats['total_tasks']}"))

        pass_conf = store.routing_policy["rbac->roles"]["confidence"]
        fail_record = build_task_record(graph, store, "rbac", "roles", "fail", tests_before="4/6", tests_after="4/6")
        store.record_outcome(fail_record)
        fail_conf = store.routing_policy["rbac->roles"]["confidence"]
        results.append(("13", pass_conf > 0.75 and fail_conf < pass_conf, f"pass={pass_conf:.3f} fail={fail_conf:.3f}"))

        results.append(("14", len(build_advisory(graph, store, "rbac")["advisory"]["similar_past_tasks"]) >= 1, "similar>=1"))

    passed = sum(1 for _, ok, _ in results if ok)
    return {
        "generated_at_utc": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "validation_mode": "installed-fallback",
        "scanner_version": __version__,
        "passed": passed,
        "total": len(results),
        "results": [
            {"claim": claim, "passed": ok, "measured": measured}
            for claim, ok, measured in results
        ],
    }


def _run_validation(json_only: bool = False) -> dict:
    script = _repo_validation_script()
    if not script.exists():
        return _run_internal_validation()
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=_project_root(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if not json_only:
        sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    json_path = _project_root() / "validation" / "validation_results.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["validation_mode"] = "repo-validation"
    return payload


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="python -m wlbs_scan.validate")
    parser.add_argument("--quick", action="store_true", help="Accepted for compatibility; currently runs the full validation suite.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON after validation completes.")
    args = parser.parse_args(argv)

    payload = _run_validation(json_only=args.json)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
