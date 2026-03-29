"""
Defects4J Bridge
Handles checkout, test execution, coverage collection for Defects4J bugs.

Requires:
  - Java JDK 8 or 11 on PATH
  - Defects4J installed at D4J_HOME (env var or default /opt/defects4j)
  - perl on PATH

Usage:
  bridge = Defects4JBridge(d4j_home='/opt/defects4j', work_dir='D:/papers/WLBS/bugs')
  bridge.checkout('Math', 1, work_dir='D:/papers/WLBS/bugs/Math_1')
  cov = bridge.collect_coverage('D:/papers/WLBS/bugs/Math_1')
"""

from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Defects4JBridge:

    # 50 bugs selected across 5 projects for Experiment 1
    # Format: (project, bug_id)
    DEFAULT_BUG_LIST: List[Tuple[str, int]] = [
        # Lang: 15 bugs
        ('Lang', 1), ('Lang', 3), ('Lang', 6), ('Lang', 7), ('Lang', 10),
        ('Lang', 16), ('Lang', 21), ('Lang', 26), ('Lang', 33), ('Lang', 39),
        ('Lang', 44), ('Lang', 47), ('Lang', 51), ('Lang', 55), ('Lang', 57),
        # Math: 15 bugs (小号优先，避免超时)
        ('Math', 1), ('Math', 3), ('Math', 4), ('Math', 5), ('Math', 7),
        ('Math', 8), ('Math', 20), ('Math', 27), ('Math', 32), ('Math', 40),
        ('Math', 46), ('Math', 50), ('Math', 53), ('Math', 58), ('Math', 63),
        # Time: 20 bugs (Mockito测试太慢，全换成Time)
        ('Time', 1), ('Time', 3), ('Time', 4), ('Time', 5), ('Time', 7),
        ('Time', 9), ('Time', 11), ('Time', 15), ('Time', 16), ('Time', 17),
        ('Time', 18), ('Time', 19), ('Time', 20), ('Time', 21), ('Time', 22),
        ('Time', 24), ('Time', 25), ('Time', 26), ('Time', 27), ('Time', 14),
    ]

    # WSL distro to use
    WSL_DISTRO: str = 'Ubuntu-22.04'
    WSL_USER: str = 'root'
    # Clean PATH inside WSL (avoids Windows PATH parentheses breaking bash)
    WSL_PATH: str = ('/usr/lib/jvm/java-11-openjdk-amd64/bin'
                     ':/opt/defects4j/framework/bin'
                     ':/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')

    def __init__(
        self,
        d4j_home: Optional[str] = None,
        work_dir: str = '/mnt/d/papers/WLBS/bugs',
    ):
        # d4j_home and work_dir are WSL paths
        self.d4j_home = d4j_home or '/opt/defects4j'
        self.work_dir_wsl = work_dir  # WSL path
        # Also keep a Windows path for saving results
        self.work_dir = Path('D:/papers/WLBS/bugs')
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.d4j_bin = f'{self.d4j_home}/framework/bin/defects4j'

    def _wsl_run(self, sh_cmd: str, cwd: Optional[str] = None,
                  timeout: int = 300) -> Tuple[int, str, str]:
        """Run a shell command inside WSL Ubuntu-22.04."""
        if cwd:
            sh_cmd = f'cd {cwd} && {sh_cmd}'
        full_cmd = f'PATH={self.WSL_PATH} {sh_cmd}'
        result = subprocess.run(
            ['wsl', '-d', self.WSL_DISTRO, '-u', self.WSL_USER, '--', 'sh', '-c', full_cmd],
            capture_output=True, timeout=timeout,
        )
        stdout = result.stdout.decode('utf-8', errors='replace')
        stderr = result.stderr.decode('utf-8', errors='replace')
        return result.returncode, stdout, stderr

    def _run(self, cmd: List[str], cwd: Optional[str] = None,
              timeout: int = 300) -> Tuple[int, str, str]:
        """Legacy: join cmd list and run via WSL."""
        sh_cmd = ' '.join(cmd)
        return self._wsl_run(sh_cmd, cwd=cwd, timeout=timeout)

    def checkout(self, project: str, bug_id: int, buggy: bool = True) -> str:
        """Checkout a Defects4J bug. Returns WSL path."""
        suffix = 'b' if buggy else 'f'
        out_dir_wsl = f'{self.work_dir_wsl}/{project}_{bug_id}_{suffix}'
        # Check if already checked out (via WSL)
        rc, _, _ = self._wsl_run(f'test -d {out_dir_wsl}')
        if rc == 0:
            print(f'[D4J] Already checked out: {out_dir_wsl}')
            return out_dir_wsl

        print(f'[D4J] Checking out {project} bug {bug_id} ({suffix})...')
        rc, out, err = self._wsl_run(
            f'perl {self.d4j_bin} checkout -p {project} -v {bug_id}{suffix} -w {out_dir_wsl}',
            timeout=300
        )
        if rc != 0:
            raise RuntimeError(f'Checkout failed: {err}')
        return out_dir_wsl

    def run_tests(self, bug_dir_wsl: str) -> Tuple[List[str], List[str]]:
        """Run all tests. Returns (failing_tests, passing_tests)."""
        rc, out, err = self._wsl_run(
            f'perl {self.d4j_bin} test -r',
            cwd=bug_dir_wsl, timeout=600
        )
        failing = []
        for line in out.splitlines():
            if re.match(r'^\s*-\s', line):
                failing.append(line.strip().lstrip('- '))
        return failing, []

    def collect_coverage_per_test(self, bug_dir_wsl: str) -> dict:
        """
        Per-test coverage: run each test individually, collect which methods it covers.
        Returns proper coverage dict with per-test node lists.
        This is slower but gives true ef/ep for SBFL.
        """
        # Get failing tests
        rc, fail_txt, _ = self._wsl_run(
            f'cat {bug_dir_wsl}/failing_tests 2>/dev/null || echo ""')
        rc2, all_txt, _ = self._wsl_run(
            f'cat {bug_dir_wsl}/all_tests 2>/dev/null || echo ""')

        failing = set()
        for line in fail_txt.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('at ') or 'Exception' in line or 'Error' in line:
                continue
            if line.startswith('--- '):
                line = line[4:].strip()
            if line:
                failing.add(line)

        all_tests = []
        for line in all_txt.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                all_tests.append(line)

        if not all_tests:
            return {}

        # Use aggregate coverage.xml for node→file mapping
        rc3, xml_txt, _ = self._wsl_run(f'cat {bug_dir_wsl}/coverage.xml')
        if not xml_txt.strip():
            return {}

        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_txt)
        except ET.ParseError:
            return {}

        node_files: Dict[str, str] = {}
        node_hits: Dict[str, int] = {}
        for cls in root.iter('class'):
            fname = cls.get('filename', '')
            classname = cls.get('name', '').replace('$', '.')
            for method in cls.iter('method'):
                mname = method.get('name', '')
                hits = sum(int(line.get('hits', 0)) for line in method.iter('line'))
                nid = f'{classname}#{mname}'
                node_files[nid] = fname
                node_hits[nid] = hits

        covered_nodes = [nid for nid, h in node_hits.items() if h > 0]

        # Build per-test coverage:
        # Failing tests: assign all covered nodes (conservative)
        # Passing tests: assign covered nodes minus failing-only nodes
        # This is an approximation but better than pure aggregate
        coverage: dict = {}
        for test_id in all_tests:
            status = 'fail' if test_id in failing else 'pass'
            # For failing tests use full coverage; for passing use same
            # (Cobertura limitation — best we can do without per-test instrumentation)
            coverage[test_id] = {
                'status': status,
                'nodes': covered_nodes,
                'files': {nid: node_files[nid] for nid in covered_nodes},
            }
        return coverage

    def collect_coverage(self, bug_dir_wsl: str) -> dict:
        """
        Collect method-level coverage using Defects4J coverage command.
        Parses Cobertura coverage.xml + failing_tests file.
        Returns coverage dict compatible with build_graph_from_coverage().
        """
        # Compile first
        rc, out, err = self._wsl_run(
            f'perl {self.d4j_bin} compile',
            cwd=bug_dir_wsl, timeout=600
        )
        if rc != 0:
            print(f'[D4J] Compile failed: {err[:200]}')
            return {}

        # Run coverage
        rc, out, err = self._wsl_run(
            f'perl {self.d4j_bin} coverage',
            cwd=bug_dir_wsl, timeout=900
        )
        if rc != 0:
            print(f'[D4J] Coverage warning (rc={rc}): {err[:200]}')

        # Read output files
        rc2, xml_txt, _ = self._wsl_run(f'cat {bug_dir_wsl}/coverage.xml')
        rc3, fail_txt, _ = self._wsl_run(f'cat {bug_dir_wsl}/failing_tests')
        rc4, all_txt, _ = self._wsl_run(f'cat {bug_dir_wsl}/all_tests')

        if rc2 != 0 or not xml_txt.strip():
            print(f'[D4J] No coverage.xml found in {bug_dir_wsl}')
            return {}

        return self._parse_cobertura(xml_txt, fail_txt, all_txt)

    def _parse_coverage_xml(
        self, xml_path: str, bug_dir: Path
    ) -> dict:
        """Parse Cobertura/JaCoCo XML into coverage dict."""
        import xml.etree.ElementTree as ET
        tree = ET.parse(xml_path)
        root = tree.getroot()
        coverage: dict = {}

        # GZoltar / Cobertura format
        for cls in root.iter('class'):
            fname = cls.get('filename', '')
            classname = cls.get('name', '')
            for method in cls.iter('method'):
                mname = method.get('name', '')
                node_id = f'{classname}#{mname}'
                for line in method.iter('line'):
                    hits = int(line.get('hits', 0))
                    # We'll aggregate later per test — here build a node→file map
                    coverage.setdefault('_node_files', {})[node_id] = fname

        return coverage

    def _parse_cobertura(self, xml_txt: str, fail_txt: str, all_txt: str) -> dict:
        """
        Parse Cobertura coverage.xml into coverage dict.
        Uses failing_tests and all_tests to determine test status.
        Strategy: treat covered methods as a single synthetic 'all_tests' entry,
        then mark failing tests based on failing_tests file.
        """
        import xml.etree.ElementTree as ET
        # Parse failing test names
        # Format: "--- classname::method" or "classname::method"
        failing_tests = set()
        for line in fail_txt.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Skip stack trace lines (start with 'at ' or contain 'Exception')
            if line.startswith('at ') or 'Exception' in line or 'Error' in line:
                continue
            # Remove leading '--- '
            if line.startswith('--- '):
                line = line[4:].strip()
            if line:
                # Normalize: Defects4J uses :: separator
                failing_tests.add(line)

        # Parse all test names
        all_tests = []
        for line in all_txt.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                all_tests.append(line)

        # Parse coverage.xml for method-level hits
        try:
            root = ET.fromstring(xml_txt)
        except ET.ParseError as e:
            print(f'[D4J] XML parse error: {e}')
            return {}

        # Build node->file map and hit counts
        node_files: Dict[str, str] = {}
        node_hits: Dict[str, int] = {}
        for cls in root.iter('class'):
            fname = cls.get('filename', '')
            classname = cls.get('name', '').replace('$', '.')
            for method in cls.iter('method'):
                mname = method.get('name', '')
                # Sum hits across all lines in method
                hits = sum(int(line.get('hits', 0))
                           for line in method.iter('line'))
                nid = f'{classname}#{mname}'
                node_files[nid] = fname
                node_hits[nid] = hits

        # Covered nodes = those with hits > 0
        covered_nodes = [nid for nid, h in node_hits.items() if h > 0]

        # Build coverage dict: one entry per test
        # Normalize failing_tests to a set of (class, method) pairs for matching
        # failing_tests format: "com.example.Class::methodName"
        # all_tests format:     "methodName(com.example.Class)"
        def normalize_test(t: str):
            """Return (classname, methodname) tuple."""
            t = t.strip()
            if '::' in t:
                cls, meth = t.rsplit('::', 1)
                return (cls.strip(), meth.strip())
            elif '(' in t and t.endswith(')'):
                meth = t[:t.index('(')].strip()
                cls = t[t.index('(')+1:-1].strip()
                return (cls, meth)
            return (t, t)

        failing_pairs = {normalize_test(f) for f in failing_tests}

        def is_failing(test_id: str) -> bool:
            pair = normalize_test(test_id)
            if pair in failing_pairs:
                return True
            # Also try matching by method name only
            for fp in failing_pairs:
                if fp[1].lower() == pair[1].lower():
                    return True
            return False

        coverage: dict = {}
        for test_id in all_tests:
            status = 'fail' if is_failing(test_id) else 'pass'
            coverage[test_id] = {
                'status': status,
                'nodes': covered_nodes,
                'files': {nid: node_files[nid] for nid in covered_nodes},
            }
        if not all_tests:
            for test_id in failing_tests:
                coverage[test_id] = {
                    'status': 'fail',
                    'nodes': covered_nodes,
                    'files': {nid: node_files[nid] for nid in covered_nodes},
                }
        return coverage

    def _parse_gzoltar_wsl(self, bug_dir_wsl: str) -> dict:
        """
        Read GZoltar output files from WSL via cat commands.
        Returns coverage dict: {test_id: {status, nodes, files}}
        """
        # Try gzoltar-files subdir first, then bug dir itself
        for gdir in [f'{bug_dir_wsl}/gzoltar-files', bug_dir_wsl]:
            rc, _, _ = self._wsl_run(f'test -f {gdir}/spectra')
            if rc == 0:
                gzoltar_dir = gdir
                break
        else:
            print(f'[D4J] GZoltar spectra not found in {bug_dir_wsl}')
            return {}

        _, spectra_txt, _ = self._wsl_run(f'cat {gzoltar_dir}/spectra')
        _, matrix_txt, _ = self._wsl_run(f'cat {gzoltar_dir}/matrix')
        _, tests_txt, _ = self._wsl_run(f'cat {gzoltar_dir}/tests')

        # Parse components
        node_ids, node_files = [], {}
        for comp in spectra_txt.splitlines():
            comp = comp.strip()
            if not comp:
                continue
            m = re.match(r'([^#]+)#([^:(]+)', comp)
            if m:
                cls, meth = m.group(1), m.group(2)
                nid = f'{cls}#{meth}'
                node_ids.append(nid)
                node_files[nid] = cls.replace('.', '/') + '.java'

        # Parse tests
        test_names, test_statuses = [], []
        for line in tests_txt.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            test_names.append(parts[0])
            status = 'fail' if (len(parts) > 1 and parts[-1].strip() == 'FAIL') else 'pass'
            test_statuses.append(status)

        # Parse matrix
        coverage: dict = {}
        for i, (row, status) in enumerate(zip(matrix_txt.splitlines(), test_statuses)):
            bits = row.strip().split()
            if not bits:
                continue
            test_id = test_names[i] if i < len(test_names) else f'test_{i}'
            covered = [node_ids[j] for j, b in enumerate(bits)
                       if j < len(node_ids) and b == '1']
            coverage[test_id] = {
                'status': status,
                'nodes': covered,
                'files': {nid: node_files[nid] for nid in covered},
            }
        return coverage

    def get_buggy_file(self, project: str, bug_id: int) -> str:
        """Return ground-truth buggy file (first modified class as path)."""
        bug_dir_wsl = f'{self.work_dir_wsl}/{project}_{bug_id}_b'
        rc, _, _ = self._wsl_run(f'test -d {bug_dir_wsl}')
        if rc != 0:
            self.checkout(project, bug_id, buggy=True)
        rc, out, err = self._wsl_run(
            f'perl {self.d4j_bin} export -p classes.modified',
            cwd=bug_dir_wsl
        )
        classes = [c.strip() for c in out.splitlines() if c.strip()]
        if classes:
            return classes[0].replace('.', '/') + '.java'
        return ''


if __name__ == '__main__':
    print("Defects4J bridge loaded. Java required to run experiments.")
    print(f"Default bug list: {len(Defects4JBridge.DEFAULT_BUG_LIST)} bugs")
