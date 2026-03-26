# WLBS Validation Results

**Generated:** 2026-03-26 06:04 UTC  
**Project:** `D:/wlbs_scan`  
**Demo:** `D:/wlbs_scan/demo` (`roles.py -> rbac.py`, mirroring Figure 1)  
**Scanner:** `wlbs_scan.py v0.6.0`  
**Python:** `3.12.9`  
**Result:** 15/15 claims validated

---

## Summary

| Claim | Description | Result | Measured |
|-------|-------------|--------|----------|
| 1 | Core graph build + curvature on the paper demo stays in the low tens of milliseconds | PASS | avg=35.48ms  stdev=4.99ms  min=29.38ms  max=47.24ms |
| 1b | Scan cost grows predictably and the average scan stays below 150 ms up to 60 synthetic Python modules | PASS | 3 files avg=33.85ms; 10 files avg=29.46ms; 30 files avg=58.32ms; 60 files avg=62.79ms |
| 2 | Behavioral distance d(roles, rbac) = 1 hop | PASS | measured d = 1 |
| 3 | roles becomes the singularity after downstream rbac failures while keeping zero direct failures | PASS | roles κ=1.000 static=0.590 downstream_failures=3 ; rbac κ=1.000 failures=3 |
| 4 | Curvature on a low-static node increases strictly across repeated failure recordings | PASS | κ series = [0.087, 0.411, 0.415, 0.419, 0.423] |
| 5 | --pytest integration records the expected 4 pass / 2 fail split and persists two failure events | PASS | passed=4 failed=2 events=2 |
| 6 | JS import graph scanning resolves a one-hop dependency between core.js and api.js | PASS | total_nodes=6  d(core, api)=1 |
| 7 | HTML report export generates a non-empty artifact containing the key demo nodes | PASS | nodes=19  size=10621 bytes |
| 8 | The paper demo still reproduces the intended baseline defect with exactly 2 failing tests | PASS | pytest summary contains '2 failed, 4 passed' |
| 9 | Resolution-decay context keeps `roles` and `rbac` in the full-fidelity near tier | PASS | tier_counts={'near': 3, 'mid': 0, 'far': 0}  approx_units=42 |
| 10 | Repair suggestion routes downstream symptom node `rbac` to upstream target `roles` | PASS | target=roles  reasoning_steps=4  actions=3 |
| 11 | Advisory output is agent-friendly: schema-tagged, suggestion-toned, and confidence-scored | PASS | schema=wlbs-advisory-v1  tone=suggestion  confidence=0.911 |
| 12 | Task-level outcome recording persists task memory and updates routing stats | PASS | task_id=Ta9ac3d44a68a4111  routing_total=1  follow_rate=1.000 |
| 13 | Routing policy confidence rises after a followed success and drops after a followed failure | PASS | pass_conf=0.825  fail_conf=0.277 |
| 14 | Advisory output includes structurally similar past tasks when task memory exists | PASS | similar_tasks=1 |

---

## Experimental Protocol

All measurements are produced by `python validation/run_validation.py`.
The suite mixes two experiment classes:

1. Real demo validation on `demo/`, which preserves the paper's intentional `roles.py -> rbac.py` defect.
2. Deterministically generated synthetic projects, used to measure scaling, monotonicity, and JS import-graph parsing.
3. Context-assembly, advisory routing, task-memory checks, and policy-learning checks after controlled outcome injection.

The latency claims are measured in-process through `build_graph()` + `compute_curvature()` so the timings reflect scanner work rather than Python interpreter startup overhead.

---

## Detailed Results

### Claim 1: Core graph build + curvature on the paper demo stays in the low tens of milliseconds

- **Result:** PASS
- **Measured:** avg=35.48ms  stdev=4.99ms  min=29.38ms  max=47.24ms
- **Notes:** Measured in-process to exclude Python process startup noise.

### Claim 1b: Scan cost grows predictably and the average scan stays below 150 ms up to 60 synthetic Python modules

- **Result:** PASS
- **Measured:** 3 files avg=33.85ms; 10 files avg=29.46ms; 30 files avg=58.32ms; 60 files avg=62.79ms
- **Notes:** Synthetic benchmark is generated deterministically inside the validation script.

### Claim 2: Behavioral distance d(roles, rbac) = 1 hop

- **Result:** PASS
- **Measured:** measured d = 1
- **Notes:** Matches the concrete cross-file dependency described in README and PAPER.

### Claim 3: roles becomes the singularity after downstream rbac failures while keeping zero direct failures

- **Result:** PASS
- **Measured:** roles κ=1.000 static=0.590 downstream_failures=3 ; rbac κ=1.000 failures=3
- **Notes:** This aligns implementation with the paper's Definition 4: upstream, high-curvature, no direct failure.

### Claim 4: Curvature on a low-static node increases strictly across repeated failure recordings

- **Result:** PASS
- **Measured:** κ series = [0.087, 0.411, 0.415, 0.419, 0.423]
- **Notes:** Synthetic project avoids early saturation, making world-line accumulation directly observable.

### Claim 5: --pytest integration records the expected 4 pass / 2 fail split and persists two failure events

- **Result:** PASS
- **Measured:** passed=4 failed=2 events=2
- **Notes:** World-lines persisted to D:\wlbs_scan\demo\.wlbs\world_lines.json.

### Claim 6: JS import graph scanning resolves a one-hop dependency between core.js and api.js

- **Result:** PASS
- **Measured:** total_nodes=6  d(core, api)=1
- **Notes:** Confirms the README's cross-language support claim on a deterministic fixture.

### Claim 7: HTML report export generates a non-empty artifact containing the key demo nodes

- **Result:** PASS
- **Measured:** nodes=19  size=10621 bytes
- **Notes:** Artifact: D:\wlbs_scan\validation\demo_report.html

### Claim 8: The paper demo still reproduces the intended baseline defect with exactly 2 failing tests

- **Result:** PASS
- **Measured:** pytest summary contains '2 failed, 4 passed'
- **Notes:** This preserved failure fixture is important because the validation suite depends on it.

### Claim 9: Resolution-decay context keeps `roles` and `rbac` in the full-fidelity near tier

- **Result:** PASS
- **Measured:** tier_counts={'near': 3, 'mid': 0, 'far': 0}  approx_units=42
- **Notes:** Confirms the paper's L1/L2/L3 context assembly behavior on the cross-file demo.

### Claim 10: Repair suggestion routes downstream symptom node `rbac` to upstream target `roles`

- **Result:** PASS
- **Measured:** target=roles  reasoning_steps=4  actions=3
- **Notes:** This is the first executable version of the paper's Gate-side reasoning chain in the standalone scanner.

### Claim 11: Advisory output is agent-friendly: schema-tagged, suggestion-toned, and confidence-scored

- **Result:** PASS
- **Measured:** schema=wlbs-advisory-v1  tone=suggestion  confidence=0.911
- **Notes:** This is the Phase 1 harness interface described in HARNESS_ROADMAP.md.

### Claim 12: Task-level outcome recording persists task memory and updates routing stats

- **Result:** PASS
- **Measured:** task_id=Ta9ac3d44a68a4111  routing_total=1  follow_rate=1.000
- **Notes:** This is the Phase 2 harness memory loop: advise -> act -> record outcome.

### Claim 13: Routing policy confidence rises after a followed success and drops after a followed failure

- **Result:** PASS
- **Measured:** pass_conf=0.825  fail_conf=0.277
- **Notes:** Implements the EMA-style policy update from HARNESS_ROADMAP Phase 3.

### Claim 14: Advisory output includes structurally similar past tasks when task memory exists

- **Result:** PASS
- **Measured:** similar_tasks=1
- **Notes:** This is the minimal cross-task transfer path for the harness.

---

## Reproducibility

Run the full suite:

```bash
cd D:/wlbs_scan
python validation/run_validation.py
```

Generated artifacts:

- `validation/VALIDATION_RESULTS.md`
- `validation/validation_results.json`
- `validation/demo_report.html`

For the paper demo baseline alone:

```bash
cd D:/wlbs_scan
python -m pytest demo/tests -q
python wlbs_scan.py demo --json
python wlbs_scan.py demo --dist roles rbac --json
python wlbs_scan.py demo --context rbac --json
python wlbs_scan.py demo --suggest --suggest-node rbac --json
python wlbs_scan.py demo --advise rbac --json
python wlbs_scan.py demo --record-outcome --symptom rbac --final-target roles --result pass --tests-before 4/6 --tests-after 6/6 --json
```

---

## Paper Claims Cross-Reference

| Paper / README Topic | Supported By |
|----------------------|--------------|
| Demo scan latency | Claim 1 |
| Scaling beyond the 3-file demo | Claim 1b |
| Behavioral distance definition | Claim 2 |
| Upstream root-cause propagation | Claim 3 |
| World-line accumulation over repeated failures | Claim 4 |
| Pytest auto-record integration | Claim 5 |
| JavaScript / TypeScript support | Claim 6 |
| HTML visualization export | Claim 7 |
| Intentional cross-file defect baseline remains reproducible | Claim 8 |
| Resolution-decay context assembly | Claim 9 |
| Reasoning-chain repair routing | Claim 10 |
| Advisory CLI harness output | Claim 11 |
| Task-level memory and routing stats | Claim 12 |
| EMA-style routing policy update | Claim 13 |
| Similar-task structural transfer | Claim 14 |
