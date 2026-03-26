# Changelog

All notable changes to wlbs-scan are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.6.0] — 2026-03

### Added
- `--context <node>` — executable resolution-decay context assembly with L1/L2/L3 tiers
- `--suggest --suggest-node <node>` — reasoning-chain repair routing from symptom node to upstream target
- `--advise <node>` — agent-friendly advisory JSON with confidence, open questions, and suggestion tone
- `--record-outcome` — task-level memory persistence with routing statistics
- EMA-based routing policy updates tied to task outcomes
- Structural similar-task matching surfaced through advisory JSON
- `python -m wlbs_scan.validate` — package-level self-validation entrypoint
- First-party IDE workspace configs: `.vscode/`, `pyrightconfig.json`, `.editorconfig`
- `--status` — product-style risk and account summary
- `--dashboard` — local interactive dashboard entrypoint
- `wlbs_server.py` — V3-aligned hub server with points, redeem, trace upload, and legacy snapshot compatibility
- `deploy/DEPLOY_V3.md` and systemd/env examples for standalone server deployment
- Validation suite expanded with context-assembly and reasoning-chain experiments
- Machine-readable validation artifact: `validation/validation_results.json`

### Changed
- `--suggest` now uses graph topology, singularity status, and world-line evidence to build an action chain
- `--history` now shows task-memory summaries and routing metrics
- `--advise` now incorporates routing-policy confidence and similar past tasks
- Standalone validation now measures scaling, context assembly, and deterministic routing in addition to core demo claims

### Fixed
- Singularity detection now matches the paper definition: upstream candidate, no direct failure, downstream failure evidence
- Demo `roles.py` fixture now satisfies the paper's structural singularity criteria without changing the intended baseline defect
- Version metadata synced to 0.6.0 across code, packaging, and docs

---

## [0.5.0] — 2026-03

### Added
- `--runtime` — `sys.settrace` dynamic tracing; failing-test call stacks drive curvature
- `--moe` — Mixture-of-Experts expert routing map (`p(expert_n) = κ(n) / Σκ`)
- `--badges` — README shield badge markdown with live project health metrics
- `--watch --pytest` — file-change detection loop with automatic pytest re-run and world-line update

### Fixed
- `--watch` (standalone) now uses MD5 file-hash change detection instead of blind 30 s polling
- `behavioral_distance` BFS resolves short call names to full node IDs, eliminating false "unreachable" results
- Module docstring version synced to 0.5
- `setup.py` version bumped to 0.5.0; added `pyproject.toml` for modern packaging

---

## [0.4.0] — 2026-02

### Added
- `--diff` — curvature trend comparison between scans
- `--export-html` — searchable, filterable HTML report with per-node history
- `--init-hook` — one-command git pre-commit hook installation
- Automatic scan snapshot saved to `.wlbs/last_scan.json` after every run

---

## [0.3.0] — 2026-01

### Added
- `--pytest` — auto-run pytest, parse JUnit XML, record pass/fail into world-lines
- `--suggest` — per-node actionable fix recommendations
- `--ci --fail-above K` — CI/CD gate; exits non-zero when curvature threshold breached
- `--blame` — `git blame` on high-curvature nodes
- `--lang js` / `--lang ts` — JavaScript and TypeScript support

---

## [0.2.0] — 2025-12

### Added
- World-line persistence: `.wlbs/world_lines.json` accumulates across sessions
- `--record-failure` / `--record-fix` — manual event recording
- Git-history-driven curvature (commit frequency signal)
- Curvature backpropagation (3 passes upstream through call graph)
- `--history` — full learning history view

---

## [0.1.0] — 2025-11

### Added
- AST behavior graph construction for Python codebases
- Curvature κ(n) computation (complexity, fan-in, line count, exception handling)
- Singularity detection and call-graph BFS behavioral distance
- `--json` output for CI/CD pipeline integration
- `--watch` mode for continuous scanning
