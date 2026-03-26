# SWE-bench Growth Protocol for WLBS

Generated: 2026-03-26T06:04:52.512570+00:00

## Purpose

This file defines how to measure whether WLBS gives a real DeepSeek uplift on the
internationally recognized **SWE-bench** benchmark, while explicitly guarding
against rote memorization and benchmark-specific overfitting.

## Current Preflight Status

- Python ready: **True**
- Docker ready: **True**
- Git ready: **True**
- `swebench` package installed: **False**
- `datasets` package installed: **False**
- Overall ready for an official run right now: **False**

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
python -m pip install swebench datasets
```

Official evaluation shape:

```bash
python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Lite --predictions_path <predictions.jsonl> --max_workers 1
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
