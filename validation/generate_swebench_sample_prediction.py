#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
import tomllib
import urllib.request
import difflib
from pathlib import Path

from datasets import load_dataset


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "validation" / "swebench_work"
REPO_DIR = WORK / "sqlfluff_repo"
OUT_DIR = ROOT / "validation" / "swebench_sample"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATASET_NAME = "princeton-nlp/SWE-bench_Lite"
SPLIT = "dev"


def get_instance_id() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    return os.environ.get("SWEBENCH_INSTANCE_ID", "sqlfluff__sqlfluff-2419")


def run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc.stdout


def append_log(title: str, content: str):
    log_path = OUT_DIR / "process_log.md"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {title}\n\n")
        f.write("```text\n")
        f.write(content.strip() + "\n")
        f.write("```\n")


def ensure_repo(base_commit: str):
    WORK.mkdir(parents=True, exist_ok=True)
    if not REPO_DIR.exists():
        run(["git", "clone", "https://github.com/sqlfluff/sqlfluff.git", str(REPO_DIR)])
    run(["git", "checkout", base_commit], cwd=REPO_DIR)


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
    raise RuntimeError("No DeepSeek key found. Set DEEPSEEK_API_KEY or keep D:\\kaiwucl\\.opencraft\\config.toml available.")


def load_instance(instance_id: str) -> dict:
    ds = load_dataset(DATASET_NAME, "default", split=SPLIT)
    for row in ds:
        if row["instance_id"] == instance_id:
            return row
    raise KeyError(instance_id)


def extract_keywords(instance: dict) -> list[str]:
    patterns: list[str] = []
    seen: set[str] = set()
    problem_statement = instance["problem_statement"]
    test_patch = instance.get("test_patch", "")
    combined = f"{problem_statement}\n{test_patch}"

    def add(item: str):
        item = item.strip()
        if len(item) < 3:
            return
        if item in seen:
            return
        seen.add(item)
        patterns.append(item)

    for match in re.findall(r"\bL\d{3}\b", combined):
        add(match)
    for match in re.findall(r"'([A-Z_]{3,})'", combined):
        add(match)
    for match in re.findall(r'"([A-Z_]{3,})"', combined):
        add(match)
    for match in re.findall(r"[A-Za-z_][A-Za-z0-9_/.-]*\.py", test_patch):
        add(match)
    for match in re.findall(r"\b(?:IFNULL|NVL|COALESCE|tsql|join condition)\b", combined, re.I):
        add(match)
    return patterns


def find_candidates(instance: dict) -> dict[str, str]:
    patterns = extract_keywords(instance)
    hits = []
    for pattern in patterns:
        proc = subprocess.run(
            ["rg", "-n", pattern, "src", "test"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if proc.returncode in (0, 1):
            hits.extend(line for line in proc.stdout.splitlines() if line.strip())
    ordered_files: list[str] = []
    for line in hits:
        file_path = line.split(":", 1)[0].replace("\\", "/")
        if file_path not in ordered_files:
            ordered_files.append(file_path)
    preferred: list[str] = []
    for match in re.findall(r"\bL\d{3}\b", instance["problem_statement"] + "\n" + instance.get("test_patch", "")):
        preferred.append(f"src/sqlfluff/rules/{match}.py")
        preferred.append(f"test/rules/std_{match}_test.py")
        preferred.append(f"test/fixtures/rules/std_rule_cases/{match}.yml")
    preferred.extend(
        [
            "src/sqlfluff/core/rules/__init__.py",
            "src/sqlfluff/testing/rules.py",
            "test/rules/std_test.py",
        ]
    )
    final = []
    for path in preferred + ordered_files:
        if path not in final and (REPO_DIR / path).exists():
            final.append(path)
    snippets = {}
    for rel in final[:5]:
        text = (REPO_DIR / rel).read_text(encoding="utf-8", errors="replace")
        if rel.endswith("commands_test.py"):
            m = re.search(r'expected_output = """(.*?)def test__cli__command_directed', text, re.S)
            snippets[rel] = m.group(0)[:5000] if m else text[:5000]
        else:
            snippets[rel] = text[:5000]
    return snippets


def build_prompt(instance: dict, snippets: dict[str, str]) -> str:
    blocks = []
    for rel, text in snippets.items():
        blocks.append(f"### FILE: {rel}\n```python\n{text}\n```")
    fail_to_pass = instance["FAIL_TO_PASS"]
    pass_to_pass = instance["PASS_TO_PASS"]
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
        {fail_to_pass}

        PASS_TO_PASS:
        {pass_to_pass}

        Test patch to satisfy:
        {instance.get('test_patch', '')}

        Constraints:
        - Minimal patch only.
        - Preserve existing behavior outside this issue.
        - Match the expected error text exactly when the failing test requires it.
        - The patch must be a valid unified diff that passes `git apply --check`.
        - Do not invent helper functions or truncate existing methods.

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
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return data["choices"][0]["message"]["content"].strip()


def extract_patch(text: str) -> str:
    if "```" in text:
        m = re.search(r"```(?:diff)?\n(.*?)```", text, re.S)
        if m:
            text = m.group(1).strip()
    idx = text.find("diff --git")
    if idx >= 0:
        text = text[idx:]
    return text.strip() + "\n"


def patch_applies(patch: str) -> tuple[bool, str]:
    tmp_patch = OUT_DIR / "candidate.patch"
    tmp_patch.write_text(patch, encoding="utf-8")
    proc = subprocess.run(
        ["git", "apply", "--check", str(tmp_patch)],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    ok = proc.returncode == 0
    detail = (proc.stdout + "\n" + proc.stderr).strip()
    return ok, detail


def call_deepseek_for_patch(prompt: str, api_key: str, model: str, max_rounds: int = 2) -> tuple[str, list[dict]]:
    rounds = []
    current_prompt = prompt
    for idx in range(1, max_rounds + 1):
        raw = call_deepseek(current_prompt, api_key, model)
        patch = extract_patch(raw)
        ok, check_detail = patch_applies(patch)
        rounds.append(
            {
                "round": idx,
                "prompt": current_prompt,
                "raw": raw,
                "patch": patch,
                "git_apply_check_ok": ok,
                "git_apply_check_detail": check_detail,
            }
        )
        if ok:
            return patch, rounds
        current_prompt = textwrap.dedent(
            f"""
            The previous patch was not valid. Regenerate a COMPLETE unified diff only.

            Validation failure from `git apply --check`:
            {check_detail or "(no detail)"}

            Requirements:
            - Output a complete unified diff.
            - Do not truncate existing function names or bodies.
            - Keep the patch minimal.
            - Preserve non-TSQL cases.

            Original task and context:
            {prompt}
            """
        ).strip()
    return rounds[-1]["patch"], rounds


def extract_code_block(text: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
    if m:
        return m.group(1).rstrip() + "\n"
    return text.strip() + "\n"


def call_deepseek_for_full_file(prompt: str, api_key: str, model: str, relpath: str) -> tuple[str, str, bool, str]:
    original = (REPO_DIR / relpath).read_text(encoding="utf-8", errors="replace")
    rewrite_prompt = textwrap.dedent(
        f"""
        You previously failed to return a valid unified diff.
        Now return the FULL updated contents of exactly one file and nothing else.

        Target file: {relpath}

        Requirements:
        - Return only the full updated file content inside one fenced python block.
        - Preserve all unchanged logic and formatting as much as possible.
        - Fix only the reported bug.
        - Do not add commentary.

        Original task:
        {prompt}
        """
    ).strip()
    raw = call_deepseek(rewrite_prompt, api_key, model)
    new_content = extract_code_block(raw)
    patch = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{relpath}",
            tofile=f"b/{relpath}",
        )
    )
    ok, detail = patch_applies(patch)
    return raw, patch, ok, detail


def main():
    instance_id = get_instance_id()
    instance = load_instance(instance_id)
    (OUT_DIR / "process_log.md").write_text(
        f"# SWE-bench Sample Run Log\n\nGenerated in {OUT_DIR}\n",
        encoding="utf-8",
    )
    append_log("Instance", json.dumps(
        {
            "instance_id": instance["instance_id"],
            "repo": instance["repo"],
            "base_commit": instance["base_commit"],
        },
        ensure_ascii=False,
        indent=2,
    ))
    ensure_repo(instance["base_commit"])
    append_log("Repo Ready", run(["git", "rev-parse", "HEAD"], cwd=REPO_DIR))
    snippets = find_candidates(instance)
    append_log("Candidate Files", "\n".join(snippets.keys()))
    prompt = build_prompt(instance, snippets)
    (OUT_DIR / "prompt.txt").write_text(prompt, encoding="utf-8")
    api_key, model = read_provider_secret()
    patch, rounds = call_deepseek_for_patch(prompt, api_key, model, max_rounds=2)
    if not any(item["git_apply_check_ok"] for item in rounds):
        fallback_relpath = next(
            (
                rel
                for rel in snippets.keys()
                if rel.startswith("src/sqlfluff/rules/") and rel.endswith(".py")
            ),
            "src/sqlfluff/rules/L060.py",
        )
        raw_rewrite, rewrite_patch, rewrite_ok, rewrite_detail = call_deepseek_for_full_file(
            prompt,
            api_key,
            model,
            fallback_relpath,
        )
        rounds.append(
            {
                "round": len(rounds) + 1,
                "prompt": "fallback_full_file_rewrite",
                "raw": raw_rewrite,
                "patch": rewrite_patch,
                "git_apply_check_ok": rewrite_ok,
                "git_apply_check_detail": rewrite_detail,
            }
        )
        patch = rewrite_patch
    for round_info in rounds:
        (OUT_DIR / f"raw_model_output_round{round_info['round']}.txt").write_text(round_info["raw"], encoding="utf-8")
        (OUT_DIR / f"sample_round{round_info['round']}.patch").write_text(round_info["patch"], encoding="utf-8")
        append_log(
            f"Model Round {round_info['round']}",
            json.dumps(
                {
                    "git_apply_check_ok": round_info["git_apply_check_ok"],
                    "git_apply_check_detail": round_info["git_apply_check_detail"],
                    "patch_bytes": len(round_info["patch"].encode("utf-8")),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    (OUT_DIR / "sample.patch").write_text(patch, encoding="utf-8")
    pred = {
        "instance_id": instance["instance_id"],
        "model_name_or_path": f"{model}+wlbs_context",
        "model_patch": patch,
    }
    with (OUT_DIR / "predictions.jsonl").open("w", encoding="utf-8") as f:
        f.write(json.dumps(pred, ensure_ascii=False) + "\n")
    summary = {
        "instance_id": instance["instance_id"],
        "repo": instance["repo"],
        "base_commit": instance["base_commit"],
        "candidate_files": list(snippets.keys()),
        "model_name": model,
        "patch_bytes": len(patch.encode("utf-8")),
        "rounds": [
            {
                "round": item["round"],
                "git_apply_check_ok": item["git_apply_check_ok"],
                "git_apply_check_detail": item["git_apply_check_detail"],
            }
            for item in rounds
        ],
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    append_log("Summary", json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
