# SWE-bench 2419 Real Test Evidence

Instance: `sqlfluff__sqlfluff-2419`
Base commit: `f1dba0e1dd764ae72d67c3d5e1471cf14d3db030`

## Method

- `baseline_repo`: base commit + official `test_patch` only.
- `patched_repo`: same base commit + validated minimal patch.
- Both sides use the same interpreter and `PYTHONPATH=<repo>/src`.

## Real Results

- Baseline target test: `1 failed`
- Baseline existing L060 fixture regression: `3 passed, 725 deselected`
- Patched target test: `1 passed`
- Patched existing L060 fixture regression: `3 passed, 725 deselected`

## Lint Output Delta

Baseline lint output descriptions:
- `Use 'COALESCE' instead of 'IFNULL' or 'NVL'.`
- `Use 'COALESCE' instead of 'IFNULL' or 'NVL'.`

Patched lint output descriptions:
- `Use 'COALESCE' instead of 'IFNULL'.`
- `Use 'COALESCE' instead of 'NVL'.`

## Interpretation

This can be used as real local evidence for `sqlfluff__sqlfluff-2419` because it is not only a patch artifact. The official failing test was executed on the untouched baseline and failed, then executed on the patched tree and passed, while the pre-existing L060 fixture tests stayed green.
