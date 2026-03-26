# SWE-bench Sample Run Log

Generated in D:\wlbs_scan\validation\swebench_sample

## Instance

```text
{
  "instance_id": "sqlfluff__sqlfluff-2419",
  "repo": "sqlfluff/sqlfluff",
  "base_commit": "f1dba0e1dd764ae72d67c3d5e1471cf14d3db030"
}
```

## Repo Ready

```text
f1dba0e1dd764ae72d67c3d5e1471cf14d3db030
```

## Candidate Files

```text
src/sqlfluff/rules/L060.py
test/fixtures/rules/std_rule_cases/L060.yml
src/sqlfluff/core/rules/__init__.py
src/sqlfluff/testing/rules.py
test/rules/std_test.py
```

## Model Round 1

```text
{
  "git_apply_check_ok": false,
  "git_apply_check_detail": "error: patch failed: src/sqlfluff/rules/L060.py:1
error: src/sqlfluff/rules/L060.py: patch does not apply",
  "patch_bytes": 1539
}
```

## Model Round 2

```text
{
  "git_apply_check_ok": false,
  "git_apply_check_detail": "error: corrupt patch at line 32",
  "patch_bytes": 1099
}
```

## Model Round 3

```text
{
  "git_apply_check_ok": false,
  "git_apply_check_detail": "error: patch failed: src/sqlfluff/rules/L060.py:59
error: src/sqlfluff/rules/L060.py: patch does not apply",
  "patch_bytes": 524
}
```

## Manual Round 4

```text
{
  "strategy": "minimal manual repair after three invalid model patches",
  "git_apply_check_ok": true,
  "validation": {
    "target_test": "python -m pytest test/rules/std_L060_test.py -q -> 1 passed",
    "fixture_regression": "python -m pytest test/rules/yaml_test_cases_test.py -q -k L060 -> 3 passed"
  }
}
```

## Final Patch

```diff
diff --git a/src/sqlfluff/rules/L060.py b/src/sqlfluff/rules/L060.py
index 836941edc..853ceeb6f 100644
--- a/src/sqlfluff/rules/L060.py
+++ b/src/sqlfluff/rules/L060.py
@@ -59,4 +59,8 @@ class Rule_L060(BaseRule):
             ],
         )
 
-        return LintResult(context.segment, [fix])
+        return LintResult(
+            context.segment,
+            [fix],
+            description=f"Use 'COALESCE' instead of '{context.segment.raw_upper}'.",
+        )
diff --git a/test/rules/std_L060_test.py b/test/rules/std_L060_test.py
new file mode 100644
index 000000000..afd01c98a
--- /dev/null
+++ b/test/rules/std_L060_test.py
@@ -0,0 +1,12 @@
+"""Tests the python routines within L060."""
+import sqlfluff
+
+
+def test__rules__std_L060_raised() -> None:
+    """L060 is raised for use of ``IFNULL`` or ``NVL``."""
+    sql = "SELECT\n\tIFNULL(NULL, 100),\n\tNVL(NULL,100);"
+    result = sqlfluff.lint(sql, rules=["L060"])
+
+    assert len(result) == 2
+    assert result[0]["description"] == "Use 'COALESCE' instead of 'IFNULL'."
+    assert result[1]["description"] == "Use 'COALESCE' instead of 'NVL'."
```

## Summary

```text
{
  "instance_id": "sqlfluff__sqlfluff-2419",
  "repo": "sqlfluff/sqlfluff",
  "base_commit": "f1dba0e1dd764ae72d67c3d5e1471cf14d3db030",
  "candidate_files": [
    "src/sqlfluff/rules/L060.py",
    "test/fixtures/rules/std_rule_cases/L060.yml",
    "src/sqlfluff/core/rules/__init__.py",
    "src/sqlfluff/testing/rules.py",
    "test/rules/std_test.py"
  ],
  "model_name": "deepseek-chat",
  "patch_bytes": 1118,
  "rounds": [
    {
      "round": 1,
      "git_apply_check_ok": false,
      "git_apply_check_detail": "error: patch failed: src/sqlfluff/rules/L060.py:1\nerror: src/sqlfluff/rules/L060.py: patch does not apply"
    },
    {
      "round": 2,
      "git_apply_check_ok": false,
      "git_apply_check_detail": "error: corrupt patch at line 32"
    },
    {
      "round": 3,
      "git_apply_check_ok": false,
      "git_apply_check_detail": "error: patch failed: src/sqlfluff/rules/L060.py:59\nerror: src/sqlfluff/rules/L060.py: patch does not apply"
    },
    {
      "round": 4,
      "git_apply_check_ok": true,
      "git_apply_check_detail": "manual minimal patch validated locally",
      "validation": {
        "target_test": "passed",
        "fixture_regression": "passed"
      }
    }
  ]
}
```
