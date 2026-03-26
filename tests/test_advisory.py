from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import wlbs_scan as ws


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


def reset_wlbs(root: Path):
    wlbs_dir = root / ".wlbs"
    if wlbs_dir.exists():
        last_error = None
        for _ in range(5):
            try:
                shutil.rmtree(wlbs_dir)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.05)
        if last_error:
            raise last_error


def prepare_demo_graph():
    reset_wlbs(DEMO)
    store = ws.WorldLineStore(DEMO)
    for i in range(3):
        store.record_failure("rbac", f"advisory failure {i + 1}")
    graph = ws.build_graph(DEMO)
    ws.compute_curvature(graph, store=store)
    return graph, store


def test_advise_output_schema():
    graph, store = prepare_demo_graph()
    advisory = ws.build_advisory(graph, store, "rbac")
    assert advisory["schema"] == "wlbs-advisory-v1"
    primary = advisory["advisory"]["primary_suggestion"]
    assert "tone" in primary
    assert "confidence" in primary


def test_advise_tone_is_suggestion():
    graph, store = prepare_demo_graph()
    advisory = ws.build_advisory(graph, store, "rbac")
    tone = advisory["advisory"]["primary_suggestion"]["tone"]
    assert tone in {"suggestion", "note"}
    assert tone != "directive"


def test_advise_confidence_range():
    graph, store = prepare_demo_graph()
    advisory = ws.build_advisory(graph, store, "rbac")
    confidence = advisory["advisory"]["primary_suggestion"]["confidence"]
    assert 0.0 <= confidence <= 1.0


def test_advise_routes_rbac_to_roles():
    graph, store = prepare_demo_graph()
    advisory = ws.build_advisory(graph, store, "rbac")
    assert "roles" in advisory["advisory"]["primary_suggestion"]["text"]


def test_advise_includes_open_questions():
    graph, store = prepare_demo_graph()
    advisory = ws.build_advisory(graph, store, "rbac")
    assert advisory["advisory"]["open_questions"] is not None
    assert len(advisory["advisory"]["open_questions"]) >= 1


def test_advise_json_parseable():
    reset_wlbs(DEMO)
    cmd = [
        sys.executable,
        str(ROOT / "wlbs_scan.py"),
        str(DEMO),
        "--record-failure",
        "rbac",
        "--detail",
        "cli setup failure",
    ]
    subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "wlbs_scan.py"), str(DEMO), "--advise", "rbac", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "wlbs-advisory-v1"
