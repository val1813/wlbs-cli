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

The entire tool is a single file: `wlbs_scan.py`.
No build step, no compiled extensions, no mandatory third-party dependencies.

---

## Running the test suite

The project ships with a small self-test you can run against itself:

```bash
wlbs-scan . --json          # sanity: should produce valid JSON
wlbs-scan . --suggest       # sanity: should print suggestions without error
wlbs-scan . --badges        # sanity: badge markdown
```

If you add new features, please include at least one CLI invocation in the
examples section of `main()` (the `epilog` string).

---

## Code style

- Python 3.8 compatible (`from __future__ import annotations` is already in place)
- Zero mandatory runtime dependencies — keep it that way
- Optional imports (e.g. `pytest`, `hashlib`) go inside the function that needs them
- Preserve the single-file layout; resist splitting into packages unless the file
  genuinely exceeds ~2000 lines

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

## Reporting bugs

Please open a GitHub Issue with:
- Your Python version and OS
- The exact command you ran
- The full error output or unexpected behaviour

---

## License

By contributing you agree that your changes will be released under the
[Apache 2.0 License](LICENSE).
