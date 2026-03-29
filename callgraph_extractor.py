"""
Java Call Graph Extractor
用 javap 从编译好的 .class 文件提取方法调用图。

JDK 自带 javap，不需要额外工具。
输出: {caller_node: [callee_node, ...]} 字典
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple


WSL_DISTRO = 'Ubuntu-22.04'
WSL_PATH = ('/usr/lib/jvm/java-11-openjdk-amd64/bin'
            ':/usr/local/bin:/usr/bin:/bin')


def _wsl_run(cmd: str, timeout: int = 60) -> str:
    result = subprocess.run(
        ['wsl', '-d', WSL_DISTRO, '-u', 'root', '--', 'sh', '-c',
         f'PATH={WSL_PATH} {cmd}'],
        capture_output=True, timeout=timeout
    )
    return result.stdout.decode('utf-8', errors='replace')


def find_class_files(bug_dir_wsl: str) -> List[str]:
    """Find all .class files in the compiled project."""
    out = _wsl_run(
        f'find {bug_dir_wsl}/target/classes {bug_dir_wsl}/build/classes '
        f'{bug_dir_wsl}/target/test-classes {bug_dir_wsl}/build/test-classes '
        f'-name "*.class" 2>/dev/null | head -500'
    )
    return [f.strip() for f in out.splitlines() if f.strip().endswith('.class')]


def parse_javap_output(javap_out: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Parse javap -p -c output to extract:
    - current class name
    - list of (caller_method, callee_class#callee_method) calls
    """
    current_class = ''
    current_method = ''
    calls: List[Tuple[str, str]] = []

    for line in javap_out.splitlines():
        # Class declaration: "public class org.apache.commons.lang3.math.NumberUtils {"
        m = re.match(r'^(?:(?:public|private|protected|abstract|final|static)\s+)*'
                     r'(?:class|interface|enum)\s+([\w.$]+)', line.strip())
        if m:
            current_class = m.group(1).replace('$', '.')
            continue

        # Method declaration: "  public static int toInt(java.lang.String);"
        # Must have '(' and not be inside Code block
        if '(' in line and ');' in line and not line.strip().startswith('//'):
            sig_m = re.search(r'([\w<>]+)\s*\(', line)
            if sig_m:
                mname = sig_m.group(1)
                # Skip keywords
                if mname not in ('if', 'for', 'while', 'switch', 'catch', 'Code'):
                    current_method = mname
            continue

        # Bytecode invoke instructions
        # Format: invokestatic  #N  // Method classname.method:(sig)ret
        # OR:     invokevirtual #N  // Method java/lang/Class.method:(sig)ret
        # OR (same class): invokestatic #N  // Method methodname:(sig)ret
        if 'invoke' in line and '// Method' in line:
            # Extract the method reference from comment
            m = re.search(r'//\s*Method\s+([^:]+):', line)
            if m and current_class and current_method:
                ref = m.group(1).strip()
                if '.' in ref:
                    # External class: e.g. java/lang/Integer.parseInt
                    parts = ref.rsplit('.', 1)
                    callee_class = parts[0].replace('/', '.').replace('$', '.')
                    callee_method = parts[1]
                else:
                    # Same class method
                    callee_class = current_class
                    callee_method = ref.strip('"')
                caller_node = f'{current_class}#{current_method}'
                callee_node = f'{callee_class}#{callee_method}'
                calls.append((caller_node, callee_node))

    return current_class, calls


def build_call_graph(
    bug_dir_wsl: str,
    max_classes: int = 300,
) -> Dict[str, List[str]]:
    """
    Build method-level call graph for a Defects4J bug.
    Returns {caller_node: [callee_node, ...]}.
    Only includes edges within the same project (filters out JDK/external calls).
    """
    class_files = find_class_files(bug_dir_wsl)
    if not class_files:
        print(f'[CG] No class files found in {bug_dir_wsl}')
        return {}

    class_files = class_files[:max_classes]
    print(f'[CG] Analyzing {len(class_files)} class files...')

    # Get project package prefix from class names
    all_calls: Dict[str, List[str]] = {}
    project_classes: Set[str] = set()

    # First pass: get all class names
    for cf in class_files:
        out = _wsl_run(f'javap -p "{cf}" 2>/dev/null | head -3')
        for line in out.splitlines():
            m = re.search(r'class\s+([\w.$]+)', line)
            if m:
                project_classes.add(m.group(1).replace('$', '.'))

    # Second pass: extract calls
    for cf in class_files:
        out = _wsl_run(f'javap -p -c "{cf}" 2>/dev/null')
        cls_name, calls = parse_javap_output(out)
        if not cls_name:
            continue
        for caller, callee in calls:
            callee_class = callee.split('#')[0]
            # Only keep edges to project classes (filter JDK/external)
            if callee_class in project_classes:
                if caller not in all_calls:
                    all_calls[caller] = []
                if callee not in all_calls[caller]:
                    all_calls[caller].append(callee)

    n_edges = sum(len(v) for v in all_calls.values())
    print(f'[CG] Built call graph: {len(all_calls)} callers, {n_edges} edges')
    return all_calls


if __name__ == '__main__':
    import json, sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    bug_dir = '/mnt/d/papers/WLBS/bugs/Lang_1_b'
    cg = build_call_graph(bug_dir, max_classes=100)
    print(f'Sample edges:')
    for caller, callees in list(cg.items())[:5]:
        print(f'  {caller} -> {callees[:2]}')
