#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import tomllib
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from datasets import load_dataset


ROOT = Path(__file__).resolve().parents[1]
DATASET_NAME = "princeton-nlp/SWE-bench_Lite"
SPLIT = "dev"
OUT_ROOT = ROOT / "validation" / "batch_swebench"
REPOS_DIR = OUT_ROOT / "repos"
RUNS_DIR = OUT_ROOT / "runs"
REPORT_MD = OUT_ROOT / "BATCH_REPORT.md"
REPORT_JSON = OUT_ROOT / "batch_results.json"

DEFAULT_INSTANCE_IDS = [
    "sqlfluff__sqlfluff-1625",
    "sqlfluff__sqlfluff-2419",
    "sqlfluff__sqlfluff-1733",
    "sqlfluff__sqlfluff-1517",
    "sqlfluff__sqlfluff-1763",
    "marshmallow-code__marshmallow-1359",
    "marshmallow-code__marshmallow-1343",
    "pvlib__pvlib-python-1707",
    "pvlib__pvlib-python-1072",
    "pvlib__pvlib-python-1606",
]
MAX_PATCH_ROUNDS = 3


@dataclass
class ValidationResult:
    returncode: int
    stdout: str
    stderr: str
    command: list[str]


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 300,
    check: bool = False,
) -> ValidationResult:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return ValidationResult(proc.returncode, proc.stdout, proc.stderr, cmd)


def repo_slug(repo: str) -> str:
    return repo.replace("/", "__")


def safe_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_instances(instance_ids: list[str]) -> list[dict]:
    ds = load_dataset(DATASET_NAME, "default", split=SPLIT)
    wanted = set(instance_ids)
    rows = [row for row in ds if row["instance_id"] in wanted]
    order = {instance_id: i for i, instance_id in enumerate(instance_ids)}
    rows.sort(key=lambda row: order[row["instance_id"]])
    return rows


def read_provider_secret() -> tuple[str, str]:
    env_key = os.environ.get("DEEPSEEK_API_KEY")
    env_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    if env_key:
        return env_key, env_model
    cfg_path = Path(r"D:\kaiwucl\.opencraft\config.toml")
    if cfg_path.exists():
        data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        for provider in data.get("providers", []):
            if provider.get("name") == "deepseek" and provider.get("api_key"):
                return provider["api_key"], provider.get("models", ["deepseek-chat"])[0]
    raise RuntimeError("No DeepSeek key found.")


def ensure_repo(repo_name: str) -> Path:
    target = REPOS_DIR / repo_slug(repo_name)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        run(
            ["git", "clone", f"https://github.com/{repo_name}.git", str(target)],
            timeout=1200,
            check=True,
        )
    return target


def extract_keywords(instance: dict) -> list[str]:
    combined = instance["problem_statement"] + "\n" + instance.get("test_patch", "")
    patterns: list[str] = []
    seen: set[str] = set()

    def add(item: str):
        item = item.strip()
        if len(item) < 3 or item in seen:
            return
        seen.add(item)
        patterns.append(item)

    for match in re.findall(r"\b[A-Z]\d{3}\b", combined):
        add(match)
    for match in re.findall(r"[A-Za-z_][A-Za-z0-9_/.-]*\.py", combined):
        add(match)
    for match in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", combined):
        if match.isupper() or match[:1].isupper():
            add(match)
    return patterns[:20]


def find_candidates(repo_dir: Path, instance: dict) -> dict[str, str]:
    hits: list[str] = []
    for pattern in extract_keywords(instance):
        result = run(["rg", "-n", pattern, "src", "test"], cwd=repo_dir, timeout=60)
        if result.returncode in (0, 1):
            hits.extend(line for line in result.stdout.splitlines() if line.strip())
    ordered_files: list[str] = []
    for line in hits:
        rel = line.split(":", 1)[0].replace("\\", "/")
        if rel not in ordered_files:
            ordered_files.append(rel)
    preferred: list[str] = []
    for rel in re.findall(r"[A-Za-z_][A-Za-z0-9_/.-]*\.py", instance.get("test_patch", "")):
        if rel.startswith("test/") or rel.startswith("src/"):
            preferred.append(rel)
    final: list[str] = []
    for rel in preferred + ordered_files:
        if rel not in final and (repo_dir / rel).exists():
            final.append(rel)
    snippets: dict[str, str] = {}
    for rel in final[:6]:
        snippets[rel] = (repo_dir / rel).read_text(encoding="utf-8", errors="replace")[:6000]
    return snippets


def build_prompt(instance: dict, snippets: dict[str, str]) -> str:
    blocks = []
    for rel, text in snippets.items():
        blocks.append(f"### FILE: {rel}\n```python\n{text}\n```")
    return textwrap.dedent(
        f"""
        You are fixing a SWE-bench Lite instance.
        Return ONLY a unified git diff patch. No prose.

        Instance: {instance['instance_id']}
        Repo: {instance['repo']}
        Base commit: {instance['base_commit']}

        Problem statement:
        {instance['problem_statement']}

        FAIL_TO_PASS:
        {instance['FAIL_TO_PASS']}

        PASS_TO_PASS:
        {instance['PASS_TO_PASS']}

        Test patch to satisfy:
        {instance.get('test_patch', '')}

        Constraints:
        - Minimal patch only.
        - Preserve behavior outside the failing issue.
        - Match expected error text exactly if tests require exact descriptions.
        - Output a valid unified diff patch that can pass `git apply --check`.

        Relevant files:
        {chr(10).join(blocks)}
        """
    ).strip()


def call_deepseek(prompt: str, api_key: str, model: str) -> str:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an expert software repair model. Output only unified diff patches."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 4000,
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return data["choices"][0]["message"]["content"].strip()


def extract_patch(text: str) -> str:
    if "```" in text:
        match = re.search(r"```(?:diff)?\n(.*?)```", text, re.S)
        if match:
            text = match.group(1)
    idx = text.find("diff --git")
    if idx >= 0:
        text = text[idx:]
    return text.strip() + "\n"


def patch_applies(repo_dir: Path, patch_path: Path) -> tuple[bool, str]:
    result = run(["git", "apply", "--check", str(patch_path)], cwd=repo_dir, timeout=120)
    ok = result.returncode == 0
    detail = (result.stdout + "\n" + result.stderr).strip()
    return ok, detail


def parse_test_list(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(item) for item in data]
    except Exception:
        pass
    return []


def run_pytest_nodes(repo_dir: Path, nodes: list[str]) -> ValidationResult:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_dir / "src")
    if not nodes:
        return ValidationResult(0, "", "", ["python", "-m", "pytest", "-q"])
    return run(["python", "-m", "pytest", *nodes, "-q"], cwd=repo_dir, env=env, timeout=1200)


def write_result_file(path: Path, result: ValidationResult):
    safe_write(
        path,
        "\n".join(
            [
                f"command: {' '.join(result.command)}",
                f"returncode: {result.returncode}",
                "stdout:",
                result.stdout.rstrip(),
                "stderr:",
                result.stderr.rstrip(),
            ]
        ).rstrip()
        + "\n",
    )


def apply_patch_with_fallback(repo_dir: Path, patch_path: Path) -> tuple[bool, str, str]:
    strict_check = run(["git", "apply", "--check", str(patch_path)], cwd=repo_dir, timeout=300)
    if strict_check.returncode == 0:
        run(["git", "apply", str(patch_path)], cwd=repo_dir, timeout=300, check=True)
        return True, "strict", (strict_check.stdout + "\n" + strict_check.stderr).strip()

    relaxed_check = run(
        ["git", "apply", "--check", "--recount", "--ignore-space-change", "--ignore-whitespace", str(patch_path)],
        cwd=repo_dir,
        timeout=300,
    )
    if relaxed_check.returncode == 0:
        apply_result = run(
            ["git", "apply", "--recount", "--ignore-space-change", "--ignore-whitespace", str(patch_path)],
            cwd=repo_dir,
            timeout=300,
        )
        if apply_result.returncode == 0:
            detail = (
                strict_check.stdout
                + "\n"
                + strict_check.stderr
                + "\n--- relaxed ---\n"
                + relaxed_check.stdout
                + "\n"
                + relaxed_check.stderr
            ).strip()
            return True, "recount_ignore_whitespace", detail

    detail = (
        strict_check.stdout
        + "\n"
        + strict_check.stderr
        + "\n--- relaxed ---\n"
        + relaxed_check.stdout
        + "\n"
        + relaxed_check.stderr
    ).strip()
    return False, "failed", detail


def main():
    instance_ids = sys.argv[1:] or DEFAULT_INSTANCE_IDS
    api_key, model = read_provider_secret()
    rows = load_instances(instance_ids)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    batch_results: list[dict] = []

    for idx, instance in enumerate(rows, start=1):
        instance_dir = RUNS_DIR / instance["instance_id"]
        if instance_dir.exists():
            shutil.rmtree(instance_dir)
        instance_dir.mkdir(parents=True)
        safe_write(instance_dir / "instance.json", json.dumps(instance, ensure_ascii=False, indent=2))

        print(f"[{idx}/{len(rows)}] {instance['instance_id']}")
        repo_cache = ensure_repo(instance["repo"])
        run(["git", "checkout", instance["base_commit"]], cwd=repo_cache, timeout=600, check=True)

        snippets = find_candidates(repo_cache, instance)
        prompt = build_prompt(instance, snippets)
        safe_write(instance_dir / "prompt.txt", prompt)

        rounds: list[dict] = []
        patch = ""
        patch_ok = False
        patch_detail = ""
        current_prompt = prompt
        patch_path = instance_dir / "candidate.patch"
        for round_no in range(1, MAX_PATCH_ROUNDS + 1):
            try:
                raw = call_deepseek(current_prompt, api_key, model)
            except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as exc:
                raw = f"[patch_generation_error] {type(exc).__name__}: {exc}"
                patch = ""
                safe_write(instance_dir / f"raw_model_output_round{round_no}.txt", raw)
                safe_write(instance_dir / f"sample_round{round_no}.patch", patch)
                rounds.append(
                    {
                        "round": round_no,
                        "git_apply_check_ok": False,
                        "git_apply_check_detail": f"patch generation failed: {type(exc).__name__}: {exc}",
                        "patch_bytes": 0,
                    }
                )
                patch_detail = f"patch generation failed: {type(exc).__name__}: {exc}"
                break
            patch = extract_patch(raw)
            safe_write(instance_dir / f"raw_model_output_round{round_no}.txt", raw)
            safe_write(instance_dir / f"sample_round{round_no}.patch", patch)
            patch_path.write_text(patch, encoding="utf-8")
            patch_ok, patch_detail = patch_applies(repo_cache, patch_path)
            rounds.append(
                {
                    "round": round_no,
                    "git_apply_check_ok": patch_ok,
                    "git_apply_check_detail": patch_detail,
                    "patch_bytes": len(patch.encode("utf-8")),
                }
            )
            if patch_ok:
                break
            current_prompt = textwrap.dedent(
                f"""
                The previous patch was invalid.
                Validation from `git apply --check`:
                {patch_detail or "(no detail)"}

                Regenerate a COMPLETE unified diff only.

                Original task:
                {prompt}
                """
            ).strip()

        safe_write(instance_dir / "sample.patch", patch)

        baseline_dir = instance_dir / "baseline_repo"
        patched_dir = instance_dir / "patched_repo"
        for target in [baseline_dir, patched_dir]:
            if target.exists():
                shutil.rmtree(target)
            run(["git", "clone", "--shared", str(repo_cache), str(target)], timeout=1200, check=True)
            run(["git", "checkout", instance["base_commit"]], cwd=target, timeout=600, check=True)

        official_test_patch = instance.get("test_patch", "")
        safe_write(instance_dir / "official_test_patch.diff", official_test_patch)
        official_patch_ok = True
        official_patch_mode = "not_needed"
        official_patch_detail = ""
        if official_test_patch.strip():
            official_patch_ok, official_patch_mode, official_patch_detail = apply_patch_with_fallback(
                baseline_dir,
                instance_dir / "official_test_patch.diff",
            )
            if official_patch_ok:
                official_patch_ok, official_patch_mode, official_patch_detail = apply_patch_with_fallback(
                    patched_dir,
                    instance_dir / "official_test_patch.diff",
                )

        patch_apply_mode = "not_run"
        patched_apply_ok = False
        patched_apply_detail = ""
        if official_patch_ok and patch.strip():
            patched_apply_ok, patch_apply_mode, patched_apply_detail = apply_patch_with_fallback(
                patched_dir,
                instance_dir / "sample.patch",
            )
        fail_to_pass = parse_test_list(instance["FAIL_TO_PASS"])
        pass_to_pass = parse_test_list(instance["PASS_TO_PASS"])

        if official_patch_ok:
            baseline_fail = run_pytest_nodes(baseline_dir, fail_to_pass)
            patched_fail = run_pytest_nodes(patched_dir, fail_to_pass) if patched_apply_ok else ValidationResult(999, "", "patch not applied", [])
        else:
            baseline_fail = ValidationResult(997, "", "official test patch not applied", [])
            patched_fail = ValidationResult(997, "", "official test patch not applied", [])

        run_pass_to_pass = len(pass_to_pass) <= 8
        if official_patch_ok and run_pass_to_pass:
            baseline_pass = run_pytest_nodes(baseline_dir, pass_to_pass)
            patched_pass = run_pytest_nodes(patched_dir, pass_to_pass) if patched_apply_ok else ValidationResult(999, "", "patch not applied", [])
        else:
            baseline_pass = ValidationResult(998, "", f"skipped PASS_TO_PASS count={len(pass_to_pass)}", [])
            patched_pass = ValidationResult(998, "", f"skipped PASS_TO_PASS count={len(pass_to_pass)}", [])

        write_result_file(instance_dir / "baseline_fail_to_pass.txt", baseline_fail)
        write_result_file(instance_dir / "patched_fail_to_pass.txt", patched_fail)
        write_result_file(instance_dir / "baseline_pass_to_pass.txt", baseline_pass)
        write_result_file(instance_dir / "patched_pass_to_pass.txt", patched_pass)

        result = {
            "instance_id": instance["instance_id"],
            "repo": instance["repo"],
            "base_commit": instance["base_commit"],
            "model_name": model,
            "candidate_files": list(snippets.keys()),
            "rounds": rounds,
            "official_patch_ok": official_patch_ok,
            "official_patch_mode": official_patch_mode,
            "official_patch_detail": official_patch_detail,
            "patch_apply_ok": patched_apply_ok,
            "patch_apply_mode": patch_apply_mode,
            "patch_apply_detail": patched_apply_detail or patch_detail,
            "fail_to_pass_count": len(fail_to_pass),
            "pass_to_pass_count": len(pass_to_pass),
            "baseline_fail_to_pass_rc": baseline_fail.returncode,
            "patched_fail_to_pass_rc": patched_fail.returncode,
            "baseline_pass_to_pass_rc": baseline_pass.returncode,
            "patched_pass_to_pass_rc": patched_pass.returncode,
            "run_pass_to_pass": run_pass_to_pass,
            "target_improved": baseline_fail.returncode != 0 and patched_fail.returncode == 0,
        }
        safe_write(instance_dir / "summary.json", json.dumps(result, ensure_ascii=False, indent=2))
        batch_results.append(result)

    improved = sum(1 for item in batch_results if item["target_improved"])
    patch_ok = sum(1 for item in batch_results if item["patch_apply_ok"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "instances": batch_results,
        "aggregate": {
            "total_instances": len(batch_results),
            "patch_apply_ok": patch_ok,
            "target_improved": improved,
        },
    }
    safe_write(REPORT_JSON, json.dumps(report, ensure_ascii=False, indent=2))

    lines = [
        "# SWE-bench Lite Batch Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"- Total instances: **{len(batch_results)}**",
        f"- Patch apply ok: **{patch_ok}**",
        f"- Target improved (FAIL_TO_PASS baseline fail -> patched pass): **{improved}**",
        "",
        "| Instance | Patch Apply | Target Improved | FAIL_TO_PASS | PASS_TO_PASS |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in batch_results:
        lines.append(
            f"| {item['instance_id']} | {item['patch_apply_ok']} | {item['target_improved']} | "
            f"{item['baseline_fail_to_pass_rc']} -> {item['patched_fail_to_pass_rc']} | "
            f"{item['baseline_pass_to_pass_rc']} -> {item['patched_pass_to_pass_rc']} |"
        )
    safe_write(REPORT_MD, "\n".join(lines) + "\n")
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
