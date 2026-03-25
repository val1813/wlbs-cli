# Changelog

All notable changes to wlbs-scan are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
