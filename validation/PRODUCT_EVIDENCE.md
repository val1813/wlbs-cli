# WLBS Product Evidence

Generated: 2026-03-26T06:03:11.082999+00:00

## Goal

This report packages the most presentation-ready evidence for `wlbs-scan`:

1. A controlled counterfactual in which a symptom-fixated debugging policy keeps editing the wrong file.
2. A continual-memory benchmark in which WLBS improves behavior on held-out renamed tasks.
3. Screenshot-ready artifacts for demos, papers, and product pages.

## Experimental Boundary

This is a **routing-layer** benchmark, not a full model-synthesis benchmark.
It proves that WLBS improves *where to look first* and *how quickly to reach the true root cause*.
It does **not** by itself prove a full official SWE-bench pass-rate uplift.

## Anti-Overfitting Guardrails

- Train file stems: `api_auth, defaults, payment_handler, rbac, registry, roles, test_api_auth, test_payment_handler, test_rbac`.
- Held-out file stems: `catalog, dashboard_view, math_panel, policy_book, screen_gate, test_dashboard_view, test_math, test_screen_gate`.
- Exact overlap between train and held-out file stems: `(none)`.
- Overlap count: **0**.
- Held-out tasks use renamed modules and renamed missing keys; no exact train file name is reused.
- Continual uplift comes from structural similar-task memory and routing confidence, not from replaying a stored gold patch.

## Core Result

### Held-out summary

| Mode | Held-out success rate | Mean attempts |
|---|---:|---:|
| Symptom-first simulation | 0.333 | 2.333 |
| WLBS fresh memoryless | 0.333 | 2.333 |
| WLBS continual memory | 1.000 | 1.000 |

### Counterfactual example: `heldout_catalog_dashboard`

- Baseline first target: `dashboard_view`
- WLBS continual first target: `catalog`
- Baseline success: `False`
- WLBS continual success: `True`
- WLBS confidence trace: `[0.98]`

## Figures and Screenshots

- Counterfactual timeline: [`validation/evidence/figures/counterfactual_debugging_timeline.png`](evidence/figures/counterfactual_debugging_timeline.png)
- Held-out summary chart: [`validation/evidence/figures/heldout_summary.png`](evidence/figures/heldout_summary.png)
- Growth curve: [`validation/evidence/figures/growth_curve.png`](evidence/figures/growth_curve.png)
- Terminal screenshot: [`validation/evidence/figures/counterfactual_terminal.png`](evidence/figures/counterfactual_terminal.png)
- Real CLI `--status` screenshot: [`validation/evidence/figures/screenshot_status.png`](evidence/figures/screenshot_status.png)
- Real CLI `--advise` screenshot: [`validation/evidence/figures/screenshot_advise.png`](evidence/figures/screenshot_advise.png)

## Reproduce

```bash
python validation/run_product_evidence.py
```

## Interpretation

- The symptom-first policy models a low-capability debugger that keeps trusting the failing file name.
- WLBS fresh memory already helps on cross-file tasks by surfacing upstream candidates.
- WLBS continual memory further helps on held-out tasks by increasing trust in structurally similar successful routes.

## Claim Boundary

### Supported now

- WLBS materially improves root-cause routing in controlled cross-file tasks.
- WLBS continual memory transfers to renamed held-out tasks without exact file-name overlap.
- The project can now emit figures, logs, and screenshot-style artifacts suitable for papers and demos.

### Not claimed here

- Official end-to-end SWE-bench pass rate.
- A live hosted DeepSeek-vs-WLBS API A/B run.
