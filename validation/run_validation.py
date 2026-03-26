#!/usr/bin/env python3
"""
WLBS reproducible validation and experiment suite.

This script serves two purposes:
1. Verify that core README / PAPER claims still match the implementation.
2. Produce quantified, reproducible measurements that can be cited in the paper.

Artifacts generated:
  - validation/VALIDATION_RESULTS.md
  - validation/validation_results.json

Run:
  python validation/run_validation.py
"""
from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
DEMO = ROOT / "demo"
VAL_DIR = ROOT / "validation"
RESULTS_MD = VAL_DIR / "VALIDATION_RESULTS.md"
RESULTS_JSON = VAL_DIR / "validation_results.json"

sys.path.insert(0, str(ROOT))
import wlbs_scan as ws  # noqa: E402

results: list[dict] = []


def section(title: str):
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


def claim(claim_id: str, desc: str, passed: bool, measured: str, detail: str = "", extra: dict | None = None):
    icon = "PASS" if passed else "FAIL"
    print(f"  [{icon}] Claim {claim_id}: {desc}")
    if measured:
        print(f"         Measured: {measured}")
    if detail:
        print(f"         {detail}")
    entry = {
        "claim": claim_id,
        "desc": desc,
        "passed": passed,
        "measured": measured,
        "detail": detail,
    }
    if extra:
        entry["extra"] = extra
    results.append(entry)


def reset_wlbs(root: Path):
    wlbs_dir = root / ".wlbs"
    if wlbs_dir.exists():
        shutil.rmtree(wlbs_dir)


def stats_from_runs(runs: list[float]) -> dict:
    return {
        "runs_ms": [round(v, 3) for v in runs],
        "avg_ms": round(statistics.mean(runs), 3),
        "stdev_ms": round(statistics.pstdev(runs), 3),
        "min_ms": round(min(runs), 3),
        "max_ms": round(max(runs), 3),
    }


def measure_core_scan(root: Path, repeats: int = 10, lang: str = "python") -> dict:
    timings = []
    for _ in range(repeats):
        store = ws.WorldLineStore(root)
        t0 = time.perf_counter()
        graph = ws.build_graph(root, lang=lang)
        ws.compute_curvature(graph, store=store)
        timings.append((time.perf_counter() - t0) * 1000)
    return stats_from_runs(timings)


def node_map(graph: ws.BehaviorGraph) -> dict[str, ws.BehaviorNode]:
    return {n.id: n for n in graph.nodes.values()}


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def make_scale_project(root: Path, module_count: int):
    for i in range(module_count):
        imports = f"import mod_{i - 1}\n" if i > 0 else ""
        body = "\n".join(
            f"    if x % {j + 2} == 0:\n        total += {j + 1}"
            for j in range(6)
        )
        write(
            root / f"mod_{i}.py",
            f"""
            {imports}

            def work_{i}(x: int) -> int:
                total = x
            {body}
                return total
            """,
        )


def make_monotone_project(root: Path):
    write(
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
    write(
        root / "bridge.py",
        """
        import heavy

        def proxy(values):
            return heavy.normalize(values)
        """,
    )
    write(
        root / "symptom.py",
        """
        import bridge

        def do_work():
            return bridge.proxy([1, 2, 3])
        """,
    )


def make_js_project(root: Path):
    write(
        root / "core.js",
        """
        export function decodeRole(role) {
          return role.toUpperCase();
        }
        """,
    )
    write(
        root / "api.js",
        """
        import { decodeRole } from "./core.js";

        export function getRole(role) {
          return decodeRole(role);
        }
        """,
    )
    write(
        root / "ui.js",
        """
        import { getRole } from "./api.js";

        export function render(role) {
          return getRole(role);
        }
        """,
    )


def locate_node(report: dict, node_id: str) -> dict:
    for item in report["nodes"]:
        if item["id"] == node_id:
            return item
    raise KeyError(node_id)


def build_report(root: Path, lang: str = "python") -> dict:
    store = ws.WorldLineStore(root)
    graph = ws.build_graph(root, lang=lang)
    ws.compute_curvature(graph, store=store)
    return ws.report_json(graph, store)


def run_demo_pytest_autorecord() -> dict:
    reset_wlbs(DEMO)
    store = ws.WorldLineStore(DEMO)
    graph = ws.build_graph(DEMO)
    result = ws._run_pytest_and_record(DEMO / "tests", DEMO, store, graph.file_to_module)
    wl_file = DEMO / ".wlbs" / "world_lines.json"
    world_lines = json.loads(wl_file.read_text(encoding="utf-8")) if wl_file.exists() else {}
    total_events = sum(len(v["events"]) for v in world_lines.get("world_lines", {}).values())
    result["total_events"] = total_events
    result["world_lines_path"] = str(wl_file)
    return result


section("Claim 1: Demo scan latency")
reset_wlbs(DEMO)
demo_stats = measure_core_scan(DEMO, repeats=12)
claim(
    "1",
    "Core graph build + curvature on the paper demo stays in the low tens of milliseconds",
    demo_stats["avg_ms"] < 50 and demo_stats["max_ms"] < 60,
    (
        f"avg={demo_stats['avg_ms']:.2f}ms  stdev={demo_stats['stdev_ms']:.2f}ms  "
        f"min={demo_stats['min_ms']:.2f}ms  max={demo_stats['max_ms']:.2f}ms"
    ),
    "Measured in-process to exclude Python process startup noise.",
    extra=demo_stats,
)


section("Claim 1b: Scaling benchmark")
with tempfile.TemporaryDirectory(prefix="wlbs_scale_") as tmp:
    base = Path(tmp)
    scale_stats = {}
    for size in (3, 10, 30, 60):
        proj = base / f"scale_{size}"
        proj.mkdir(parents=True, exist_ok=True)
        make_scale_project(proj, size)
        scale_stats[size] = measure_core_scan(proj, repeats=6)
        print(
            f"  size={size:>2}  avg={scale_stats[size]['avg_ms']:.2f}ms  "
            f"max={scale_stats[size]['max_ms']:.2f}ms"
        )
    general_growth = scale_stats[60]["avg_ms"] >= scale_stats[3]["avg_ms"] and scale_stats[30]["avg_ms"] >= scale_stats[10]["avg_ms"] * 0.8
    claim(
        "1b",
        "Scan cost grows predictably and the average scan stays below 150 ms up to 60 synthetic Python modules",
        general_growth and scale_stats[60]["avg_ms"] < 150,
        "; ".join(f"{size} files avg={vals['avg_ms']:.2f}ms" for size, vals in scale_stats.items()),
        "Synthetic benchmark is generated deterministically inside the validation script.",
        extra=scale_stats,
    )


section("Claim 2: Behavioral distance on the paper demo")
reset_wlbs(DEMO)
demo_graph = ws.build_graph(DEMO)
demo_store = ws.WorldLineStore(DEMO)
ws.compute_curvature(demo_graph, store=demo_store)
distance = ws.behavioral_distance(demo_graph, "roles", "rbac")
claim(
    "2",
    "Behavioral distance d(roles, rbac) = 1 hop",
    distance == 1,
    f"measured d = {distance}",
    "Matches the concrete cross-file dependency described in README and PAPER.",
)


section("Claim 3: Upstream localization and singularity semantics")
reset_wlbs(DEMO)
demo_store = ws.WorldLineStore(DEMO)
for i in range(3):
    demo_store.record_failure("rbac", f"KeyError admin iteration {i + 1}")
demo_graph = ws.build_graph(DEMO)
ws.compute_curvature(demo_graph, store=demo_store)
demo_report = ws.report_json(demo_graph, demo_store)
roles_node = locate_node(demo_report, "roles")
rbac_node = locate_node(demo_report, "rbac")
claim(
    "3",
    "roles becomes the singularity after downstream rbac failures while keeping zero direct failures",
    roles_node["is_singularity"] and roles_node["failures"] == 0 and not rbac_node["is_singularity"],
    (
        f"roles κ={roles_node['curvature']:.3f} static={roles_node['static']:.3f} "
        f"downstream_failures={roles_node['downstream_failures']} ; "
        f"rbac κ={rbac_node['curvature']:.3f} failures={rbac_node['failures']}"
    ),
    "This aligns implementation with the paper's Definition 4: upstream, high-curvature, no direct failure.",
    extra={"roles": roles_node, "rbac": rbac_node},
)


section("Claim 4: World-line accumulation on a low-static target")
with tempfile.TemporaryDirectory(prefix="wlbs_monotone_") as tmp:
    proj = Path(tmp)
    make_monotone_project(proj)
    reset_wlbs(proj)
    store = ws.WorldLineStore(proj)
    series = []
    baseline_report = build_report(proj)
    baseline_node = locate_node(baseline_report, "symptom.do_work")
    series.append(round(baseline_node["curvature"], 3))
    print(f"  baseline symptom.do_work κ = {series[-1]:.3f}")
    for i in range(4):
        store.record_failure("symptom.do_work", f"synthetic failure {i + 1}")
        report = build_report(proj)
        node = locate_node(report, "symptom.do_work")
        series.append(round(node["curvature"], 3))
        print(f"  after {i + 1} failure(s): symptom.do_work κ = {series[-1]:.3f}")
    monotone = all(series[i] < series[i + 1] for i in range(len(series) - 1))
    claim(
        "4",
        "Curvature on a low-static node increases strictly across repeated failure recordings",
        monotone,
        f"κ series = {series}",
        "Synthetic project avoids early saturation, making world-line accumulation directly observable.",
        extra={"series": series},
    )


section("Claim 5: pytest auto-record")
pytest_result = run_demo_pytest_autorecord()
claim(
    "5",
    "--pytest integration records the expected 4 pass / 2 fail split and persists two failure events",
    pytest_result.get("passed") == 4 and pytest_result.get("failed") == 2 and pytest_result.get("total_events") == 2,
    (
        f"passed={pytest_result.get('passed')} failed={pytest_result.get('failed')} "
        f"events={pytest_result.get('total_events')}"
    ),
    f"World-lines persisted to {pytest_result.get('world_lines_path')}.",
    extra=pytest_result,
)


section("Claim 6: JavaScript / TypeScript graph support")
with tempfile.TemporaryDirectory(prefix="wlbs_js_") as tmp:
    proj = Path(tmp)
    make_js_project(proj)
    js_report = build_report(proj, lang="js")
    js_graph = ws.build_graph(proj, lang="js")
    js_dist = ws.behavioral_distance(js_graph, "core", "api")
    claim(
        "6",
        "JS import graph scanning resolves a one-hop dependency between core.js and api.js",
        js_report["total_nodes"] >= 3 and js_dist == 1,
        f"total_nodes={js_report['total_nodes']}  d(core, api)={js_dist}",
        "Confirms the README's cross-language support claim on a deterministic fixture.",
        extra={"report": js_report, "distance": js_dist},
    )


section("Claim 7: HTML report export")
reset_wlbs(DEMO)
store = ws.WorldLineStore(DEMO)
store.record_failure("rbac", "html export probe")
graph = ws.build_graph(DEMO)
ws.compute_curvature(graph, store=store)
html_path = VAL_DIR / "demo_report.html"
node_count = ws.export_html(graph, store, html_path)
html_text = html_path.read_text(encoding="utf-8")
claim(
    "7",
    "HTML report export generates a non-empty artifact containing the key demo nodes",
    html_path.exists() and html_path.stat().st_size > 1000 and "roles" in html_text and "rbac" in html_text,
    f"nodes={node_count}  size={html_path.stat().st_size} bytes",
    f"Artifact: {html_path}",
    extra={"path": str(html_path), "size_bytes": html_path.stat().st_size, "nodes": node_count},
)


section("Claim 8: Demo pytest baseline remains intentionally failing")
cmd = [sys.executable, "-m", "pytest", str(DEMO / "tests"), "-q"]
run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
stdout = (run.stdout + run.stderr).strip()
if "No module named pytest" in stdout:
    reset_wlbs(DEMO)
    fallback_store = ws.WorldLineStore(DEMO)
    fallback_graph = ws.build_graph(DEMO)
    fallback = ws._run_simple_tests_and_record(DEMO / "tests", DEMO, fallback_store, fallback_graph.file_to_module)
    stdout = f"{fallback['failed']} failed, {fallback['passed']} passed"
    run = subprocess.CompletedProcess(cmd, 1 if fallback["failed"] else 0, stdout, "")
claim(
    "8",
    "The paper demo still reproduces the intended baseline defect with exactly 2 failing tests",
    run.returncode != 0 and "2 failed, 4 passed" in stdout,
    "pytest summary contains '2 failed, 4 passed'",
    "This preserved failure fixture is important because the validation suite depends on it.",
    extra={"returncode": run.returncode, "pytest_output": stdout},
)


section("Claim 9: Resolution-decay context assembly")
reset_wlbs(DEMO)
store = ws.WorldLineStore(DEMO)
for i in range(3):
    store.record_failure("rbac", f"context probe {i + 1}")
graph = ws.build_graph(DEMO)
ws.compute_curvature(graph, store=store)
ctx = ws.assemble_resolution_context(graph, store, "rbac")
near_ids = {item["id"] for item in ctx["tiers"]["near"]}
claim(
    "9",
    "Resolution-decay context keeps `roles` and `rbac` in the full-fidelity near tier",
    "roles" in near_ids and "rbac" in near_ids and ctx["tier_counts"]["near"] >= 2,
    f"tier_counts={ctx['tier_counts']}  approx_units={ctx['approx_context_units']}",
    "Confirms the paper's L1/L2/L3 context assembly behavior on the cross-file demo.",
    extra=ctx,
)


section("Claim 10: Reasoning-chain repair suggestion")
suggestion = ws.build_repair_suggestion(graph, store, "rbac")
claim(
    "10",
    "Repair suggestion routes downstream symptom node `rbac` to upstream target `roles`",
    suggestion["recommended_target"] == "roles" and len(suggestion["reasoning_chain"]) >= 2,
    (
        f"target={suggestion['recommended_target']}  "
        f"reasoning_steps={len(suggestion['reasoning_chain'])}  "
        f"actions={len(suggestion['action_chain'])}"
    ),
    "This is the first executable version of the paper's Gate-side reasoning chain in the standalone scanner.",
    extra=suggestion,
)


section("Claim 11: Advisory CLI schema")
advisory = ws.build_advisory(graph, store, "rbac")
primary = advisory["advisory"]["primary_suggestion"]
claim(
    "11",
    "Advisory output is agent-friendly: schema-tagged, suggestion-toned, and confidence-scored",
    advisory["schema"] == "wlbs-advisory-v1"
    and primary["tone"] in {"suggestion", "note"}
    and primary["tone"] != "directive"
    and 0.0 <= primary["confidence"] <= 1.0,
    f"schema={advisory['schema']}  tone={primary['tone']}  confidence={primary['confidence']:.3f}",
    "This is the Phase 1 harness interface described in HARNESS_ROADMAP.md.",
    extra=advisory,
)


section("Claim 12: Task memory outcome recording")
task_record = ws.build_task_record(
    graph, store,
    symptom="rbac",
    final_target="roles",
    result="pass",
    tests_before="4/6",
    tests_after="6/6",
)
store.record_outcome(task_record)
reloaded = ws.WorldLineStore(DEMO)
saved = reloaded.task_memory.get(task_record["task_id"])
claim(
    "12",
    "Task-level outcome recording persists task memory and updates routing stats",
    saved is not None
    and reloaded.routing_stats["total_tasks"] >= 1
    and saved["suggestion_was_followed"] is True,
    (
        f"task_id={task_record['task_id']}  "
        f"routing_total={reloaded.routing_stats['total_tasks']}  "
        f"follow_rate={reloaded.routing_stats['suggestion_follow_rate']:.3f}"
    ),
    "This is the Phase 2 harness memory loop: advise -> act -> record outcome.",
    extra={"task_record": task_record, "routing_stats": reloaded.routing_stats},
)


section("Claim 13: Policy learning confidence update")
reset_wlbs(DEMO)
store = ws.WorldLineStore(DEMO)
for i in range(3):
    store.record_failure("rbac", f"policy probe {i + 1}")
graph = ws.build_graph(DEMO)
ws.compute_curvature(graph, store=store)
pass_record = ws.build_task_record(graph, store, "rbac", "roles", "pass", tests_before="4/6", tests_after="6/6")
store.record_outcome(pass_record)
pass_conf = store.routing_policy["rbac->roles"]["confidence"]
fail_record = ws.build_task_record(graph, store, "rbac", "roles", "fail", tests_before="4/6", tests_after="4/6")
store.record_outcome(fail_record)
fail_conf = store.routing_policy["rbac->roles"]["confidence"]
claim(
    "13",
    "Routing policy confidence rises after a followed success and drops after a followed failure",
    pass_conf > 0.75 and fail_conf < pass_conf,
    f"pass_conf={pass_conf:.3f}  fail_conf={fail_conf:.3f}",
    "Implements the EMA-style policy update from HARNESS_ROADMAP Phase 3.",
    extra={"pass_conf": pass_conf, "fail_conf": fail_conf},
)


section("Claim 14: Similar task transfer")
with tempfile.TemporaryDirectory(prefix="wlbs_policy_") as tmp:
    proj = Path(tmp)
    make_scale_project(proj, 0)
    write(
        proj / "registry.py",
        """
        TABLE = {"editor": ["read"]}

        def get_entry(role):
            if not isinstance(role, str):
                raise TypeError("role must be string")
            return TABLE[role]
        """,
    )
    write(
        proj / "payment_handler.py",
        """
        import registry

        def handle():
            return registry.get_entry("admin")
        """,
    )
    store = ws.WorldLineStore(proj)
    graph = ws.build_graph(proj)
    ws.compute_curvature(graph, store=store)
    hist = ws.build_task_record(graph=graph, store=store, symptom="payment_handler", final_target="registry", result="pass", detail="missing key in registry")
    store.record_outcome(hist)
    advisory = ws.build_advisory(graph, store, "payment_handler")
    similar = advisory["advisory"]["similar_past_tasks"]
    claim(
        "14",
        "Advisory output includes structurally similar past tasks when task memory exists",
        len(similar) >= 1,
        f"similar_tasks={len(similar)}",
        "This is the minimal cross-task transfer path for the harness.",
        extra={"similar_tasks": similar},
    )


passed_n = sum(1 for r in results if r["passed"])
total_n = len(results)
timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

payload = {
    "generated_at_utc": timestamp,
    "project": str(ROOT),
    "python": sys.version.split()[0],
    "scanner_version": ws.__version__,
    "passed": passed_n,
    "total": total_n,
    "results": results,
}
RESULTS_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

lines = [
    "# WLBS Validation Results",
    "",
    f"**Generated:** {timestamp}  ",
    f"**Project:** `{ROOT.as_posix()}`  ",
    f"**Demo:** `{DEMO.as_posix()}` (`roles.py -> rbac.py`, mirroring Figure 1)  ",
    f"**Scanner:** `wlbs_scan.py v{ws.__version__}`  ",
    f"**Python:** `{sys.version.split()[0]}`  ",
    f"**Result:** {passed_n}/{total_n} claims validated",
    "",
    "---",
    "",
    "## Summary",
    "",
    "| Claim | Description | Result | Measured |",
    "|-------|-------------|--------|----------|",
]

for r in results:
    icon = "PASS" if r["passed"] else "FAIL"
    desc = r["desc"].replace("|", "/")
    meas = (r["measured"] or "").replace("|", "/")
    lines.append(f"| {r['claim']} | {desc} | {icon} | {meas} |")

lines += [
    "",
    "---",
    "",
    "## Experimental Protocol",
    "",
    "All measurements are produced by `python validation/run_validation.py`.",
    "The suite mixes two experiment classes:",
    "",
    "1. Real demo validation on `demo/`, which preserves the paper's intentional `roles.py -> rbac.py` defect.",
    "2. Deterministically generated synthetic projects, used to measure scaling, monotonicity, and JS import-graph parsing.",
    "3. Context-assembly, advisory routing, task-memory checks, and policy-learning checks after controlled outcome injection.",
    "",
    "The latency claims are measured in-process through `build_graph()` + `compute_curvature()` so the timings reflect scanner work rather than Python interpreter startup overhead.",
    "",
    "---",
    "",
    "## Detailed Results",
    "",
]

for r in results:
    icon = "PASS" if r["passed"] else "FAIL"
    lines += [
        f"### Claim {r['claim']}: {r['desc']}",
        "",
        f"- **Result:** {icon}",
        f"- **Measured:** {r['measured']}",
        f"- **Notes:** {r['detail']}",
        "",
    ]

lines += [
    "---",
    "",
    "## Reproducibility",
    "",
    "Run the full suite:",
    "",
    "```bash",
    "cd D:/wlbs_scan",
    "python validation/run_validation.py",
    "```",
    "",
    "Generated artifacts:",
    "",
    "- `validation/VALIDATION_RESULTS.md`",
    "- `validation/validation_results.json`",
    "- `validation/demo_report.html`",
    "",
    "For the paper demo baseline alone:",
    "",
    "```bash",
    "cd D:/wlbs_scan",
    "python -m pytest demo/tests -q",
    "python wlbs_scan.py demo --json",
    "python wlbs_scan.py demo --dist roles rbac --json",
    "python wlbs_scan.py demo --context rbac --json",
    "python wlbs_scan.py demo --suggest --suggest-node rbac --json",
    "python wlbs_scan.py demo --advise rbac --json",
    "python wlbs_scan.py demo --record-outcome --symptom rbac --final-target roles --result pass --tests-before 4/6 --tests-after 6/6 --json",
    "```",
    "",
    "---",
    "",
    "## Paper Claims Cross-Reference",
    "",
    "| Paper / README Topic | Supported By |",
    "|----------------------|--------------|",
    "| Demo scan latency | Claim 1 |",
    "| Scaling beyond the 3-file demo | Claim 1b |",
    "| Behavioral distance definition | Claim 2 |",
    "| Upstream root-cause propagation | Claim 3 |",
    "| World-line accumulation over repeated failures | Claim 4 |",
    "| Pytest auto-record integration | Claim 5 |",
    "| JavaScript / TypeScript support | Claim 6 |",
    "| HTML visualization export | Claim 7 |",
    "| Intentional cross-file defect baseline remains reproducible | Claim 8 |",
    "| Resolution-decay context assembly | Claim 9 |",
    "| Reasoning-chain repair routing | Claim 10 |",
    "| Advisory CLI harness output | Claim 11 |",
    "| Task-level memory and routing stats | Claim 12 |",
    "| EMA-style routing policy update | Claim 13 |",
    "| Similar-task structural transfer | Claim 14 |",
    "",
]

RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")

print(f"\n{'=' * 72}")
print(f"  VALIDATION COMPLETE: {passed_n}/{total_n} passed")
print(f"  Results written to: {RESULTS_MD}")
print(f"  JSON artifact: {RESULTS_JSON}")
print(f"{'=' * 72}\n")
