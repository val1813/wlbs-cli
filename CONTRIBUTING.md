# Contributing to wlbs-scan

Thank you for your interest in contributing.
This document covers the essentials for getting a patch merged.

---

## Getting started

```bash
git clone https://github.com/wlbs-scan/wlbs-scan
cd wlbs-scan
pip install -e .
```

The runtime logic lives in `wlbs_scan/_impl.py`, with package wrappers in `wlbs_scan/`.
No compiled extensions, no mandatory third-party dependencies.

---

## Running the test suite

The project ships with a small self-test you can run against itself:

```bash
wlbs-scan . --json                  # sanity: should produce valid JSON
wlbs-scan . --suggest               # sanity: should print suggestions without error
wlbs-scan . --badges                # sanity: badge markdown
python -m pytest tests -q           # unit test suite
python -m wlbs_scan.validate        # full validation suite
```

If you add new features, please include at least one CLI invocation in the
examples section of `main()` (the `epilog` string inside `wlbs_scan/_impl.py`).

---

## Code style

- Python 3.8 compatible (`from __future__ import annotations` is already in place)
- Zero mandatory runtime dependencies — keep it that way
- Optional imports (e.g. `pytest`, `hashlib`) go inside the function that needs them
- Keep package wrappers thin; core behavior should continue to live in `wlbs_scan/_impl.py`

---

## Adding language support

New language parsers live inside `build_graph()`. Follow the pattern used for
JavaScript/TypeScript (`_parse_js_file`) — regex-based, no external parser
required, outputs into the shared `BehaviorGraph`.

---

## Submitting a pull request

1. Fork the repository and create a feature branch.
2. Keep commits focused — one logical change per commit.
3. Update `CHANGELOG.md` under an `[Unreleased]` heading.
4. Open the PR with a short description of *why* the change is needed.

---

## Release Checklist

Every release should pass all of the following:

- `python -m pytest tests -q`
- `python -m wlbs_scan.validate`
- `python -m wlbs_scan.validate --json`
- `python -m wlbs_scan . --advise rbac --json`
- `python -m wlbs_scan . --record-outcome --symptom rbac --final-target roles --result pass`
- `python -m build`
- Install the built wheel in a clean environment and confirm `python -m wlbs_scan.validate` still works
- When reviewing validation results, check `validation_mode`:
  - `repo-validation` means the full repository validation suite ran
  - `installed-fallback` means the embedded wheel self-check ran
- Sync `validation/VALIDATION_RESULTS.md` to the latest measured data
- Update `CHANGELOG.md`

---

## Reporting bugs

Please open a GitHub Issue with:
- Your Python version and OS
- The exact command you ran
- The full error output or unexpected behaviour

---

## License

By contributing you agree that your changes will be released under the
[Apache 2.0 License](LICENSE).
