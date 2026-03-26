#!/usr/bin/env python3
"""
SWE-bench growth preflight for WLBS.

This script does not claim an official SWE-bench score. It verifies whether the
local machine is ready for an official run and emits a protocol document that
keeps the eventual benchmark honest.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_MD = ROOT / "validation" / "SWEBENCH_GROWTH_PROTOCOL.md"
OUT_JSON = ROOT / "validation" / "swebench_preflight.json"


def run(cmd: list[str]) -> dict:
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=20)
        stdout = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except Exception as exc:  # pragma: no cover - defensive preflight
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
        }


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main():
    checks = {
        "python": {
            "ok": True,
            "version": sys.version.split()[0],
            "executable": sys.executable,
        },
        "docker": run(["docker", "--version"]),
        "git": run(["git", "--version"]),
        "pytest": {"ok": has_module("pytest")},
        "swebench": {"ok": has_module("swebench")},
        "datasets": {"ok": has_module("datasets")},
    }
    checks["docker_binary_on_path"] = {"ok": shutil.which("docker") is not None}
    checks["git_binary_on_path"] = {"ok": shutil.which("git") is not None}

    readiness = {
        "docker_ready": bool(checks["docker"]["ok"]),
        "git_ready": bool(checks["git"]["ok"]),
        "python_ready": True,
        "benchmark_pkg_ready": bool(checks["swebench"]["ok"]),
        "dataset_pkg_ready": bool(checks["datasets"]["ok"]),
        "needs_model_executor": True,
        "needs_predictions_pipeline": True,
    }
    readiness["overall_ready_for_official_run"] = (
        readiness["docker_ready"]
        and readiness["git_ready"]
        and readiness["benchmark_pkg_ready"]
        and not readiness["needs_model_executor"]
        and not readiness["needs_predictions_pipeline"]
    )

    commands = {
        "install_swebench": "python -m pip install swebench datasets",
        "prepare_predictions": (
            "Use the same DeepSeek model, same max turns, same temperature, "
            "and same repo checkout policy for both baseline and WLBS-augmented runs."
        ),
        "official_eval_template": (
            "python -m swebench.harness.run_evaluation "
            "--dataset_name princeton-nlp/SWE-bench_Lite "
            "--predictions_path <predictions.jsonl> "
            "--max_workers 1"
        ),
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "readiness": readiness,
        "commands": commands,
        "claim_boundary": {
            "supported_now": [
                "This machine has Docker and Git available.",
                "A reproducible local WLBS evidence harness already exists in validation/run_product_evidence.py.",
                "The benchmark protocol below prevents template leakage and overfitting claims.",
            ],
            "not_supported_now": [
                "No official SWE-bench score was run in this preflight step.",
                "A live DeepSeek executor and prediction JSONL pipeline still need to be connected.",
            ],
        },
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    md = f"""\
# SWE-bench Growth Protocol for WLBS

Generated: {payload["generated_at"]}

## Purpose

This file defines how to measure whether WLBS gives a real DeepSeek uplift on the
internationally recognized **SWE-bench** benchmark, while explicitly guarding
against rote memorization and benchmark-specific overfitting.

## Current Preflight Status

- Python ready: **{readiness["python_ready"]}**
- Docker ready: **{readiness["docker_ready"]}**
- Git ready: **{readiness["git_ready"]}**
- `swebench` package installed: **{readiness["benchmark_pkg_ready"]}**
- `datasets` package installed: **{readiness["dataset_pkg_ready"]}**
- Overall ready for an official run right now: **{readiness["overall_ready_for_official_run"]}**

## Why no official score is reported here

The current repository contains a strong **routing-layer evidence harness**
(`validation/run_product_evidence.py`) but does not yet include a live DeepSeek
prediction generator wired into the official SWE-bench prediction format.

Reporting an official pass rate before that executor exists would overstate the evidence.

## Required Fairness Rules

1. Use the **same DeepSeek model** for baseline and WLBS-augmented runs.
2. Keep temperature, max turns, time budget, and tool access identical.
3. Run with serial workers when credibility matters: `--max_workers 1`.
4. Do not handcraft issue-specific templates or gold-file hints.
5. Freeze the benchmark split before tuning WLBS thresholds.
6. Evaluate on **held-out instances** only when claiming uplift.
7. Preserve raw predictions JSONL, Docker logs, and official evaluation output.

## Growth Measurement

The growth question should be phrased as:

> With the same DeepSeek base model, does WLBS increase official SWE-bench Lite
> resolution rate, or at minimum reduce wasted attempts before the successful patch?

Primary metrics:

- Official resolved count / resolution rate from the SWE-bench harness
- Mean attempts to first correct file touch
- Mean turns to first passing patch
- Invalid run rate

Secondary diagnostics:

- Top-1 root-file routing accuracy
- Share of runs that keep editing symptom files only
- Similar-task memory usage count

## Anti-Overfitting Design

- Tune WLBS only on a separate development subset or on synthetic tasks.
- Lock thresholds before the held-out official run.
- Keep a raw baseline without WLBS memory.
- Keep a fresh-memory WLBS run and a continual-memory WLBS run.
- Report all three:
  - DeepSeek baseline
  - DeepSeek + WLBS fresh
  - DeepSeek + WLBS continual

If only the continual version improves, claim **continual-learning uplift**.
If both fresh and continual improve, claim **routing uplift**, with continual
memory as an extra gain.

## Suggested Command Skeleton

Install benchmark tooling:

```bash
{commands["install_swebench"]}
```

Official evaluation shape:

```bash
{commands["official_eval_template"]}
```

## What is already proven locally

- `validation/run_product_evidence.py` already proves a non-overfit local pattern:
  held-out renamed tasks with zero exact file-name overlap improve from
  symptom-first failure to WLBS continual success.
- This is strong evidence for the *mechanism*.
- The missing step is the official end-to-end DeepSeek executor.

## Next Concrete Action

Build a DeepSeek prediction adapter that emits official SWE-bench predictions JSONL,
then run:

1. DeepSeek baseline
2. DeepSeek + WLBS fresh
3. DeepSeek + WLBS continual

Only after those three runs complete should an official SWE-bench uplift be claimed.
"""
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
