#!/usr/bin/env python3
"""
wlbs-scan v0.5 — WLBS Behavior Graph Scanner
Learns from your failures. Gets smarter over time. Zero dependencies beyond Python 3.8+.

Usage:
    wlbs-scan .                              # 扫描 + 更新记忆
    wlbs-scan . --record-failure rbac        # 记录失败（测试失败后调用）
    wlbs-scan . --record-fix roles           # 记录修复成功
    wlbs-scan . --history                    # 查看学习历史
    wlbs-scan . --top 10 --json              # JSON输出接入CI/CD
    wlbs-scan . --reset                      # 清空记忆重新开始
    wlbs-scan . --pytest tests/                  # 自动解析pytest结果并记录
    wlbs-scan . --ci --fail-above 0.8            # CI模式，超阈值返回非零exit code
    wlbs-scan . --suggest                        # 给高风险节点提供修复建议
    wlbs-scan . --blame                          # 显示高曲率节点最后修改人(git blame)
    wlbs-scan . --lang js src/                   # 扫描 JavaScript/TypeScript 项目
    wlbs-scan . --diff                           # 对比上次扫描，显示曲率变化趋势
    wlbs-scan . --export-html report.html        # 导出 HTML 可视化报告
    wlbs-scan . --init-hook                      # 安装 pre-commit hook
"""
from __future__ import annotations
import ast, argparse, json, os, subprocess, sys, time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

__version__ = "0.5.0"

RESET="\033[0m"; BOLD="\033[1m"; RED="\033[91m"; YELLOW="\033[93m"
GREEN="\033[92m"; CYAN="\033[96m"; GRAY="\033[90m"; WHITE="\033[97m"; MAGENTA="\033[95m"
# Ensure UTF-8 output on Windows (GBK terminal would break Unicode symbols)
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

USE_COLOR = sys.stdout.isatty()
def colored(t, *c): return ("".join(c)+t+RESET) if USE_COLOR else t

# ── World-line storage ─────────────────────────────────────────────────────────
@dataclass
class Event:
    ts: str; kind: str; node: str; detail: str = ""

@dataclass
class WorldLine:
    node_id: str
    events: list = field(default_factory=list)
    def append(self, kind, detail=""):
        self.events.append({"ts": datetime.now(timezone.utc).isoformat(),
                             "kind": kind, "node": self.node_id, "detail": detail})
    @property
    def failure_count(self): return sum(1 for e in self.events if e["kind"]=="failure")
    @property
    def fix_count(self): return sum(1 for e in self.events if e["kind"]=="fix")
    @property
    def recent_failure_rate(self):
        recent = [e for e in self.events if e["kind"] in ("failure","fix")][-10:]
        if not recent: return 0.0
        return sum(1 for e in recent if e["kind"]=="failure") / len(recent)
    @property
    def last_event(self): return self.events[-1] if self.events else None

class WorldLineStore:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / ".wlbs" / "world_lines.json"
        self._lines: dict[str, WorldLine] = {}
        self._load()
    def _load(self):
        if not self.path.exists(): return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for nid, wl_data in data.get("world_lines", {}).items():
                wl = WorldLine(node_id=nid)
                wl.events = wl_data.get("events", [])
                self._lines[nid] = wl
        except Exception: pass
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": __version__,
                "updated": datetime.now(timezone.utc).isoformat(),
                "world_lines": {nid: {"events": wl.events}
                                for nid, wl in self._lines.items()}}
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    def get(self, nid: str) -> WorldLine:
        if nid not in self._lines: self._lines[nid] = WorldLine(node_id=nid)
        return self._lines[nid]
    def record_failure(self, nid, detail=""):
        self.get(nid).append("failure", detail); self.save()
    def record_fix(self, nid, detail=""):
        self.get(nid).append("fix", detail); self.save()
    def reset(self):
        if self.path.exists(): self.path.unlink()
        self._lines = {}
    def all_lines(self): return list(self._lines.values())
    @property
    def total_failures(self): return sum(wl.failure_count for wl in self._lines.values())
    @property
    def total_fixes(self): return sum(wl.fix_count for wl in self._lines.values())

# ── Data model ─────────────────────────────────────────────────────────────────
@dataclass
class BehaviorNode:
    id: str; file: str; kind: str
    calls: list = field(default_factory=list)
    called_by: list = field(default_factory=list)
    curvature: float = 0.0
    static_curvature: float = 0.0
    history_curvature: float = 0.0
    git_curvature: float = 0.0
    complexity: int = 0
    is_imported_by_count: int = 0
    has_exception_handling: bool = False
    line_count: int = 0
    git_change_count: int = 0
    failure_count: int = 0
    fix_count: int = 0
    recent_failure_rate: float = 0.0
    @property
    def risk_label(self):
        if self.curvature >= 0.7: return colored("HIGH  ", RED, BOLD)
        if self.curvature >= 0.4: return colored("MED   ", YELLOW)
        return colored("LOW   ", GREEN)
    @property
    def trend(self):
        if self.recent_failure_rate >= 0.6: return colored("↑", RED)
        if self.recent_failure_rate <= 0.2 and self.fix_count > 0: return colored("↓", GREEN)
        return colored("→", GRAY)

@dataclass
class BehaviorGraph:
    nodes: dict = field(default_factory=dict)
    file_to_module: dict = field(default_factory=dict)

# ── AST visitors ───────────────────────────────────────────────────────────────
class _CV(ast.NodeVisitor):
    def __init__(self): self.score = 1
    def visit_If(self,n): self.score+=1; self.generic_visit(n)
    def visit_For(self,n): self.score+=1; self.generic_visit(n)
    def visit_While(self,n): self.score+=1; self.generic_visit(n)
    def visit_ExceptHandler(self,n): self.score+=1; self.generic_visit(n)
    def visit_With(self,n): self.score+=1; self.generic_visit(n)

class _IV(ast.NodeVisitor):
    def __init__(self): self.imports = []
    def visit_Import(self,n):
        for a in n.names: self.imports.append(a.name.split(".")[0])
    def visit_ImportFrom(self,n):
        if n.module: self.imports.append(n.module.split(".")[0])

class _CallV(ast.NodeVisitor):
    def __init__(self): self.calls = []
    def visit_Call(self,n):
        f=n.func
        if isinstance(f,ast.Attribute): self.calls.append(f.attr)
        elif isinstance(f,ast.Name): self.calls.append(f.id)
        self.generic_visit(n)

def _parse_file(path: Path, mname: str, graph: BehaviorGraph):
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=str(path))
    except SyntaxError: return
    iv=_IV(); iv.visit(tree)
    cv=_CV(); cv.visit(tree)
    has_exc = any(isinstance(n,(ast.Try,ast.ExceptHandler)) for n in ast.walk(tree))
    graph.nodes[mname] = BehaviorNode(
        id=mname, file=str(path), kind="module",
        calls=list(set(iv.imports)), complexity=cv.score,
        has_exception_handling=has_exc, line_count=len(src.splitlines()))
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            kind="class" if isinstance(node,ast.ClassDef) else "function"
            nid=f"{mname}.{node.name}"
            c2=_CV(); c2.visit(node)
            c3=_CallV(); c3.visit(node)
            has_e=any(isinstance(n,(ast.Try,ast.ExceptHandler)) for n in ast.walk(node))
            end=getattr(node,"end_lineno",node.lineno)
            graph.nodes[nid]=BehaviorNode(
                id=nid, file=str(path), kind=kind,
                calls=list(set(c for c in c3.calls if c!=node.name)),
                complexity=c2.score, has_exception_handling=has_e,
                line_count=end-node.lineno+1)

# ── Git history ────────────────────────────────────────────────────────────────
def _git_counts(root: Path) -> dict:
    counts = {}
    try:
        r = subprocess.run(
            ["git","log","--name-only","--pretty=format:","--diff-filter=ACDMR"],
            cwd=root, capture_output=True, text=True, timeout=10)
        if r.returncode != 0: return counts
        for line in r.stdout.splitlines():
            line = line.strip()
            if line: counts[line] = counts.get(line, 0) + 1
    except (FileNotFoundError, subprocess.TimeoutExpired): pass
    return counts

# ── Build graph ────────────────────────────────────────────────────────────────
def build_graph(root: Path, since_days=None, lang: str = 'python') -> BehaviorGraph:
    graph = BehaviorGraph()
    skip = {"__pycache__",".git",".wlbs","node_modules","venv",".venv","dist","build",".tox"}
    py_files = []
    js_exts = {".js", ".ts", ".jsx", ".tsx"} if lang in ("js","ts","javascript","typescript") else set()
    for p in sorted(list(root.rglob("*.py")) +
                    [f for ext in js_exts for f in root.rglob(f"*{ext}")]):
        if any(x in p.parts for x in skip): continue
        if since_days and (time.time()-p.stat().st_mtime)/86400 > since_days: continue
        py_files.append(p)
    for p in py_files:
        try: rel = p.relative_to(root)
        except ValueError: rel = p
        parts = list(rel.parts)
        if parts[-1]=="__init__.py": parts=parts[:-1]
        else: parts[-1]=parts[-1][:-3]
        mname = ".".join(parts) if parts else p.stem
        graph.file_to_module[str(p)] = mname
        if p.suffix in ('.js','.ts','.jsx','.tsx'):
            _parse_js_file(p, mname, graph)
        else:
            _parse_file(p, mname, graph)
    # called_by edges
    idx = defaultdict(list)
    for nid in graph.nodes: idx[nid.split(".")[-1]].append(nid)
    for nid, node in graph.nodes.items():
        for s in node.calls:
            for cand in idx.get(s,[]):
                if cand!=nid and cand in graph.nodes:
                    graph.nodes[cand].called_by.append(nid)
    # import fan-in
    for nid, node in graph.nodes.items():
        if node.kind=="module":
            short=nid.split(".")[-1]
            node.is_imported_by_count=sum(
                1 for o in graph.nodes.values()
                if o.kind=="module" and short in o.calls and o.id!=nid)
    # git
    gc = _git_counts(root)
    for p, mname in graph.file_to_module.items():
        try: rel = str(Path(p).relative_to(root))
        except ValueError: rel = p
        count = gc.get(rel, gc.get(rel.replace("\\","/"),0))
        if mname in graph.nodes:
            graph.nodes[mname].git_change_count = count
            for nid,n in graph.nodes.items():
                if nid.startswith(mname+"."): n.git_change_count=count
    return graph

# ── Curvature ─────────────────────────────────────────────────────────────────
def compute_curvature(graph: BehaviorGraph, store: Optional[WorldLineStore]=None):
    if not graph.nodes: return
    mc = max(n.complexity for n in graph.nodes.values()) or 1
    mi = max(n.is_imported_by_count for n in graph.nodes.values()) or 1
    ml = max(n.line_count for n in graph.nodes.values()) or 1
    mg = max(n.git_change_count for n in graph.nodes.values()) or 1
    for node in graph.nodes.values():
        # static
        s = (0.35*(node.complexity/mc) + 0.25*(node.is_imported_by_count/mi) +
             0.10*min(node.line_count/ml,1.0) +
             (0.15 if not node.has_exception_handling and node.complexity>3 else 0))
        node.static_curvature = round(min(s,1.0),3)
        node.git_curvature = round(node.git_change_count/mg,3)
        # world-line
        h = 0.0
        if store:
            wl = store._lines.get(node.id)
            if wl:
                node.failure_count=wl.failure_count
                node.fix_count=wl.fix_count
                node.recent_failure_rate=wl.recent_failure_rate
                raw = wl.recent_failure_rate*0.8 + min(wl.failure_count/20,1.0)*0.2
                disc = 0.7 if wl.fix_count>0 and wl.last_event and wl.last_event["kind"]=="fix" else 1.0
                h = raw * disc
        node.history_curvature = round(min(h,1.0),3)
        # combined — additive: failures always increase above static baseline (paper: Δκ = α·λ^d)
        if node.failure_count>0 or node.fix_count>0:
            bonus = 0.40*node.history_curvature + 0.15*node.git_curvature
            k = node.static_curvature + bonus  # additive ensures failures never lower κ
        elif node.git_change_count>0:
            k = 0.45*node.static_curvature + 0.55*node.git_curvature
        else:
            k = node.static_curvature
        node.curvature = round(min(k,1.0),3)
    # backpropagation — BFS upstream along dependency edges (calls), exponential decay
    # Δκ(n) = seed_κ × decay^depth  (paper §3.2: Δκ = α·λ^d)
    # Direction: if rbac CALLS roles, failure in rbac propagates risk signal TO roles.
    # We follow node.calls (dependencies) not node.called_by (callers).
    DECAY = 0.5; MAX_DEPTH = 4
    # Build short-name → full node ID index for resolving calls list
    _bp_idx: dict = defaultdict(list)
    for nid in graph.nodes:
        _bp_idx[nid.split(".")[-1]].append(nid)
    # Only seed from nodes with actual failure history — pure static κ should not propagate
    seeds = [(nid, n.curvature) for nid, n in graph.nodes.items()
             if n.failure_count > 0 and n.curvature >= 0.5]
    for seed_id, seed_k in seeds:
        visited = {seed_id}; queue = [(seed_id, 1)]
        while queue:
            cur, depth = queue.pop(0)
            if depth > MAX_DEPTH: continue
            node = graph.nodes.get(cur)
            if not node: continue
            # resolve calls (short names) to full node IDs; use set to avoid double-counting
            dep_ids: set = set()
            for short in node.calls:
                for cand in _bp_idx.get(short, []):
                    dep_ids.add(cand)
                # only add short directly if it is NOT already in _bp_idx results
                if short in graph.nodes and short not in dep_ids:
                    dep_ids.add(short)
            for dep_id in dep_ids:
                if dep_id not in graph.nodes: continue
                contrib = round(seed_k * (DECAY ** depth), 4)
                graph.nodes[dep_id].curvature = round(
                    min(graph.nodes[dep_id].curvature + contrib, 1.0), 3)
                if dep_id not in visited:
                    visited.add(dep_id); queue.append((dep_id, depth + 1))

def find_singularities(graph: BehaviorGraph, threshold=0.55):
    out = []
    for node in graph.nodes.values():
        if node.curvature < threshold: continue
        if (len(node.called_by)>0 or node.is_imported_by_count>0) and node.complexity>2:
            out.append(node)
    return sorted(out, key=lambda n: n.curvature, reverse=True)

def behavioral_distance(graph: BehaviorGraph, src: str, dst: str) -> int:
    """Shortest undirected hop distance between two nodes in the behavior graph.
    Searches both call directions (src→calls and src←called_by) so that
    d(roles, rbac) == d(rbac, roles) == 1 regardless of argument order."""
    if src == dst: return 0
    # Build short-name → full node ID index
    idx: dict = defaultdict(list)
    for nid in graph.nodes:
        idx[nid.split(".")[-1]].append(nid)
    def _neighbors(nid):
        node = graph.nodes.get(nid)
        if not node: return []
        neighbors = []
        # forward edges (calls)
        for short in node.calls:
            for cand in idx.get(short, []):
                neighbors.append(cand)
            if short in graph.nodes:
                neighbors.append(short)
        # backward edges (called_by) — makes distance undirected
        for cand in node.called_by:
            neighbors.append(cand)
        return neighbors
    visited = {src}; queue = [(src, 0)]
    while queue:
        cur, d = queue.pop(0)
        for cand in _neighbors(cur):
            if cand == dst: return d + 1
            if cand not in visited:
                visited.add(cand); queue.append((cand, d + 1))
    return 999

# ── Reports ────────────────────────────────────────────────────────────────────
def print_report(graph: BehaviorGraph, store: WorldLineStore, top_n=15, show_sing=True):
    nodes = sorted(graph.nodes.values(), key=lambda n: n.curvature, reverse=True)
    total=len(nodes)
    high=sum(1 for n in nodes if n.curvature>=0.7)
    med =sum(1 for n in nodes if 0.4<=n.curvature<0.7)
    low =sum(1 for n in nodes if n.curvature<0.4)
    tf=store.total_failures; tfx=store.total_fixes
    learned=len([w for w in store.all_lines() if w.failure_count>0])
    print()
    print(colored("━"*55, CYAN, BOLD))
    print(colored(f"  wlbs-scan v{__version__}", WHITE, BOLD))
    print(colored("━"*55, CYAN, BOLD))
    print(f"  Nodes: {colored(str(total),WHITE,BOLD)}  │  "
          f"{colored(str(high),RED)} high  {colored(str(med),YELLOW)} med  {colored(str(low),GREEN)} low")
    if tf>0 or tfx>0:
        print(f"  Memory: {colored(str(learned),MAGENTA)} nodes learned  │  "
              f"{colored(str(tf),RED)} failures  {colored(str(tfx),GREEN)} fixes")
    else:
        print(f"  Memory: {colored('no history yet',GRAY)}"
              f"  — use --record-failure / --record-fix to teach it")
    print()
    print(colored(f"  Top {min(top_n,total)} by curvature:", BOLD))
    print(colored(f"  {'RISK':<8} {'κ':>6} T  {'FAIL':>5} {'FIX':>4}  {'GIT':>4}  ID", GRAY))
    print(colored("  "+"─"*62, GRAY))
    for node in nodes[:top_n]:
        fs = colored(f"{node.failure_count:>5}",RED) if node.failure_count>0 else f"{'0':>5}"
        xs = colored(f"{node.fix_count:>4}",GREEN) if node.fix_count>0 else f"{'0':>4}"
        gs = f"{node.git_change_count:>4}" if node.git_change_count>0 else colored("   -",GRAY)
        w  = colored(" ⚠",YELLOW) if not node.has_exception_handling and node.complexity>5 else ""
        print(f"  {node.risk_label} {node.curvature:>6.3f} {node.trend}  "
              f"{fs} {xs}  {gs}  {colored(node.id,CYAN)}{w}")
    if show_sing:
        sings = find_singularities(graph)
        if sings:
            print()
            print(colored("  ★ Singularities (likely cross-file root causes):", YELLOW, BOLD))
            for s in sings[:5]:
                hist = colored(f" ({s.failure_count} failures)",RED) if s.failure_count>0 else ""
                print(f"    {colored('★',YELLOW)} {colored(s.id,WHITE,BOLD)}{hist}")
                print(f"       κ={s.curvature:.3f}  complexity={s.complexity}"
                      f"  git={s.git_change_count}  deps={len(s.called_by)+s.is_imported_by_count}")
    print()
    print(colored("  Tip: wlbs-scan . --record-failure <node>  after test fails",GRAY))
    print(colored("       wlbs-scan . --record-fix <node>      after you fix it",GRAY))
    print(colored("━"*55, CYAN))
    print()

def print_history(store: WorldLineStore):
    lines=[w for w in store.all_lines() if w.failure_count>0 or w.fix_count>0]
    if not lines:
        print(colored("\n  No history yet.\n",GRAY)); return
    lines.sort(key=lambda w: w.failure_count, reverse=True)
    print()
    print(colored("━"*55,CYAN,BOLD))
    print(colored("  World-Line History — what the system has learned",WHITE,BOLD))
    print(colored("━"*55,CYAN,BOLD))
    print(colored(f"  {'NODE':<38} {'FAIL':>5} {'FIX':>5} {'RATE':>6}  TREND",GRAY))
    print(colored("  "+"─"*62,GRAY))
    for wl in lines:
        rate=wl.recent_failure_rate
        rc=RED if rate>=0.6 else (YELLOW if rate>=0.3 else GREEN)
        trend="↑ still failing" if rate>=0.6 else ("↓ improving" if wl.fix_count>0 else "→ stable")
        trend_c=RED if rate>=0.6 else (GREEN if wl.fix_count>0 else GRAY)
        print(f"  {colored(wl.node_id,CYAN):<48} "
              f"{colored(str(wl.failure_count),RED):>5} "
              f"{colored(str(wl.fix_count),GREEN):>5} "
              f"{colored(f'{rate*100:.0f}%',rc):>6}  "
              f"{colored(trend,trend_c)}")
        for ev in wl.events[-3:]:
            icon=colored("✗",RED) if ev["kind"]=="failure" else colored("✓",GREEN)
            detail=f" — {ev['detail'][:50]}" if ev.get("detail") else ""
            print(f"    {icon} {ev['ts'][:16]}  {ev['kind']}{detail}")
    print(colored("━"*55,CYAN))
    print()

def report_json(graph: BehaviorGraph, store: WorldLineStore):
    sings=find_singularities(graph)
    sing_ids={s.id for s in sings}
    return {
        "version": __version__,
        "total_nodes": len(graph.nodes),
        "high_risk": sum(1 for n in graph.nodes.values() if n.curvature>=0.7),
        "total_failures_recorded": store.total_failures,
        "total_fixes_recorded": store.total_fixes,
        "singularities": [s.id for s in sings],
        "nodes": [
            {"id":n.id,"file":n.file,"kind":n.kind,
             "curvature":n.curvature,"static":n.static_curvature,
             "history":n.history_curvature,"git":n.git_curvature,
             "complexity":n.complexity,"lines":n.line_count,
             "git_changes":n.git_change_count,
             "failures":n.failure_count,"fixes":n.fix_count,
             "recent_failure_rate":n.recent_failure_rate,
             "is_singularity":n.id in sing_ids}
            for n in sorted(graph.nodes.values(),key=lambda n:n.curvature,reverse=True)
        ]
    }

# ── Main ───────────────────────────────────────────────────────────────────────
# ── JavaScript / TypeScript support (regex-based, no external deps) ───────────
import re as _re

def _parse_js_file(path, mname, graph):
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    lines = src.splitlines()
    complexity = 1
    complexity += src.count(" if ") + src.count(" else ") + src.count("? ")
    complexity += src.count("for ") + src.count("while ") + src.count("forEach(")
    complexity += src.count("catch ") + src.count("?.") + src.count(" ?? ")
    has_exc = "try {" in src or "catch(" in src or ".catch(" in src
    imports = []
    for m in _re.findall(r"from\s+['\"]([^'\"]+)['\"]", src):
        base = m.split("/")[-1].replace(".js","").replace(".ts","")
        if base: imports.append(base)
    for m in _re.findall(r"require\(['\"]([^'\"]+)['\"]\)", src):
        base = m.split("/")[-1].replace(".js","").replace(".ts","")
        if base: imports.append(base)
    graph.nodes[mname] = BehaviorNode(
        id=mname, file=str(path), kind="module",
        calls=list(set(imports)), complexity=complexity,
        has_exception_handling=has_exc, line_count=len(lines))
    seen = set()
    for m in _re.finditer(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)|class\s+(\w+)', src):
        name = m.group(1) or m.group(2)
        if not name or name in seen: continue
        seen.add(name)
        kind = "class" if m.group(2) else "function"
        graph.nodes[f"{mname}.{name}"] = BehaviorNode(
            id=f"{mname}.{name}", file=str(path), kind=kind,
            calls=[], complexity=max(1, complexity//4),
            has_exception_handling=has_exc, line_count=30)


# ── pytest auto-integration ────────────────────────────────────────────────────
import xml.etree.ElementTree as _ET

def _run_pytest_and_record(test_path, project_root, store, file_to_module):
    import tempfile
    results = {"passed": 0, "failed": 0, "recorded": []}
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        xml_path = f.name
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_path),
             f"--junit-xml={xml_path}", "-q", "--tb=no"],
            cwd=project_root, capture_output=True, text=True, timeout=120)
    except Exception as e:
        return {"error": str(e), "passed": 0, "failed": 0, "recorded": []}
    try:
        tree = _ET.parse(xml_path)
        root_el = tree.getroot()
        suites = root_el.findall(".//testsuite") or [root_el]
        all_modules = list(file_to_module.values())
        for suite in suites:
            for tc in suite.findall("testcase"):
                classname = tc.get("classname","")
                name = tc.get("name","")
                failures = tc.findall("failure") + tc.findall("error")
                node_id = _find_best_node(classname, name, all_modules)
                if failures:
                    detail = f"{name}: {failures[0].get('message','')[:80]}"
                    store.record_failure(node_id, detail)
                    results["failed"] += 1
                    results["recorded"].append(("failure", node_id, detail))
                else:
                    results["passed"] += 1
                    wl = store._lines.get(node_id)
                    if wl and wl.failure_count > 0 and wl.recent_failure_rate > 0:
                        store.record_fix(node_id, f"test passed: {name}")
                        results["recorded"].append(("fix", node_id, name))
    except Exception as e:
        results["parse_error"] = str(e)
    finally:
        try: os.unlink(xml_path)
        except: pass
    return results

def _find_best_node(classname, test_name, all_modules):
    module_guess = classname.split(".")[0] if classname else ""
    guesses = [module_guess]
    for prefix in ("test_","tests_","spec_"):
        if module_guess.startswith(prefix):
            guesses.append(module_guess[len(prefix):])
    for g in guesses:
        if g in all_modules: return g
        for m in all_modules:
            if g and (m == g or m.endswith("."+g) or m.endswith("/"+g)): return m
    return module_guess or "unknown"


# ── Suggestions ────────────────────────────────────────────────────────────────
def print_suggestions(graph, store):
    sings = find_singularities(graph)
    sing_ids = {s.id for s in sings}
    nodes = sorted(graph.nodes.values(), key=lambda n: n.curvature, reverse=True)[:10]
    print()
    print(colored("━"*55, CYAN, BOLD))
    print(colored("  Actionable Suggestions", WHITE, BOLD))
    print(colored("━"*55, CYAN, BOLD))
    for node in nodes:
        if node.curvature < 0.3: break
        print()
        icon = colored("★", YELLOW) if node.id in sing_ids else colored("•", CYAN)
        print(f"  {icon} {colored(node.id, WHITE, BOLD)}  κ={node.curvature:.3f}")
        suggs = []
        if node.failure_count >= 2 and node.fix_count == 0:
            suggs.append(colored("  → Multiple failures, no fix yet. "
                "Confirm this is root cause not just symptom.", RED))
        if node.id in sing_ids:
            suggs.append(colored("  → Singularity: errors appear downstream but "
                "root cause is here. Review exports/interface.", YELLOW))
        if not node.has_exception_handling and node.complexity > 5:
            suggs.append(colored("  → High complexity + no error handling. "
                "Add try/except around critical paths.", YELLOW))
        if node.git_change_count > 10:
            suggs.append(colored(f"  → Changed {node.git_change_count}x in git. "
                "Frequently modified = reliability risk. Consider refactor.", YELLOW))
        if node.complexity > 15:
            suggs.append(colored(f"  → Complexity={node.complexity}. "
                "Split into smaller functions.", CYAN))
        if node.is_imported_by_count > 3:
            suggs.append(colored(f"  → Imported by {node.is_imported_by_count} modules. "
                "Wide blast radius. Add regression tests.", CYAN))
        if not suggs:
            suggs.append(colored("  → High static risk. Add tests + error handling.", GRAY))
        for s in suggs:
            print(s)
    print()
    print(colored("━"*55, CYAN))
    print()


def print_blame(graph, root, top_n=8):
    nodes = sorted(graph.nodes.values(), key=lambda n: n.curvature, reverse=True)[:top_n]
    print()
    print(colored("━"*55, CYAN, BOLD))
    print(colored("  Git Blame — high-curvature node owners", WHITE, BOLD))
    print(colored("━"*55, CYAN, BOLD))
    seen = set()
    for node in nodes:
        if node.curvature < 0.3: continue
        fp = Path(node.file)
        if str(fp) in seen: continue
        seen.add(str(fp))
        try: rel = fp.relative_to(root)
        except ValueError: rel = fp
        try:
            r = subprocess.run(
                ["git","log","-1","--format=%an|%ar|%s","--",str(rel)],
                cwd=root, capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                parts = r.stdout.strip().split("|")
                author = parts[0] if parts else "unknown"
                when   = parts[1] if len(parts)>1 else ""
                msg    = parts[2][:55] if len(parts)>2 else ""
                print(f"  {node.risk_label} {colored(node.id, CYAN)}")
                print(f"       {colored(author, WHITE)}  {colored(when, GRAY)}")
                print(f"       {colored(msg, GRAY)}")
            else:
                print(f"  {node.risk_label} {colored(node.id, CYAN)}"
                      f"  {colored('(no git history)', GRAY)}")
        except Exception:
            print(f"  {node.risk_label} {colored(node.id, CYAN)}")
    print()
    print(colored("━"*55, CYAN))
    print()


# ── Diff: compare against last scan ───────────────────────────────────────────
SNAPSHOT_FILE = ".wlbs/last_scan.json"

def save_snapshot(graph: BehaviorGraph, root: Path):
    snap = {n.id: n.curvature for n in graph.nodes.values()}
    snap_path = root / SNAPSHOT_FILE
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")

def load_snapshot(root: Path) -> dict:
    snap_path = root / SNAPSHOT_FILE
    if not snap_path.exists():
        return {}
    try:
        return json.loads(snap_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def print_diff(graph: BehaviorGraph, root: Path):
    prev = load_snapshot(root)
    if not prev:
        print(colored("\n  No previous scan found. Run without --diff first to create baseline.\n", GRAY))
        return

    changes = []
    for nid, node in graph.nodes.items():
        old_k = prev.get(nid)
        if old_k is None:
            changes.append((node.curvature - 0.0, nid, 0.0, node.curvature, "new"))
        elif abs(node.curvature - old_k) >= 0.03:
            changes.append((node.curvature - old_k, nid, old_k, node.curvature, "changed"))

    # Also find removed nodes
    removed = [(nid, k) for nid, k in prev.items() if nid not in graph.nodes]

    changes.sort(key=lambda x: abs(x[0]), reverse=True)

    print()
    print(colored("━"*58, CYAN, BOLD))
    print(colored("  Curvature Diff — changes since last scan", WHITE, BOLD))
    print(colored("━"*58, CYAN, BOLD))

    rising  = [(d,nid,ok,nk,t) for d,nid,ok,nk,t in changes if d > 0]
    falling = [(d,nid,ok,nk,t) for d,nid,ok,nk,t in changes if d < 0]
    new_nodes = [(d,nid,ok,nk,t) for d,nid,ok,nk,t in changes if t == "new"]

    if rising:
        print(colored(f"\n  ↑ Rising ({len(rising)} nodes) — increasing risk:", RED, BOLD))
        for d,nid,ok,nk,t in rising[:10]:
            bar = "█" * min(int(abs(d)*40), 20)
            print(f"    {colored(f'+{d:+.3f}', RED)}  {colored(nid, CYAN):<45} "
                  f"{ok:.3f} → {colored(f'{nk:.3f}', RED)}  {colored(bar, RED)}")

    if falling:
        print(colored(f"\n  ↓ Falling ({len(falling)} nodes) — decreasing risk:", GREEN, BOLD))
        for d,nid,ok,nk,t in falling[:10]:
            bar = "█" * min(int(abs(d)*40), 20)
            print(f"    {colored(f'{d:+.3f}', GREEN)}  {colored(nid, CYAN):<45} "
                  f"{ok:.3f} → {colored(f'{nk:.3f}', GREEN)}  {colored(bar, GREEN)}")

    if new_nodes:
        print(colored(f"\n  + New ({len(new_nodes)} nodes):", YELLOW))
        for d,nid,ok,nk,t in new_nodes[:5]:
            print(f"    {colored(nid, CYAN)}  κ={nk:.3f}")

    if removed:
        print(colored(f"\n  - Removed ({len(removed)} nodes):", GRAY))
        for nid, k in removed[:5]:
            print(f"    {colored(nid, GRAY)}  was κ={k:.3f}")

    if not changes and not removed:
        print(colored("\n  No significant changes since last scan.\n", GREEN))

    print()
    print(colored("━"*58, CYAN))
    print()


# ── HTML report ────────────────────────────────────────────────────────────────
def export_html(graph: BehaviorGraph, store: WorldLineStore, out_path: Path):
    nodes = sorted(graph.nodes.values(), key=lambda n: n.curvature, reverse=True)
    sings = {s.id for s in find_singularities(graph)}
    total = len(nodes)
    high  = sum(1 for n in nodes if n.curvature >= 0.7)
    med   = sum(1 for n in nodes if 0.4 <= n.curvature < 0.7)
    tf    = store.total_failures
    tfx   = store.total_fixes

    # Build node rows
    rows = []
    for n in nodes[:100]:  # cap at 100 for performance
        risk_cls = "high" if n.curvature >= 0.7 else ("med" if n.curvature >= 0.4 else "low")
        sing_badge = '<span class="badge sing">★ singularity</span>' if n.id in sings else ""
        exc_warn   = '<span class="badge warn">⚠ no exc</span>' if not n.has_exception_handling and n.complexity > 5 else ""
        fail_str   = f'<span class="red">{n.failure_count}</span>' if n.failure_count > 0 else "0"
        fix_str    = f'<span class="green">{n.fix_count}</span>' if n.fix_count > 0 else "0"
        git_str    = str(n.git_change_count) if n.git_change_count > 0 else "-"
        pct = int(n.curvature * 100)
        rows.append(f"""
        <tr class="{risk_cls}">
          <td><div class="bar-wrap"><div class="bar {risk_cls}" style="width:{pct}%"></div></div>{pct/100:.3f}</td>
          <td>{n.id}{sing_badge}{exc_warn}</td>
          <td>{n.kind}</td>
          <td>{n.complexity}</td>
          <td>{n.line_count}</td>
          <td>{git_str}</td>
          <td>{fail_str}</td>
          <td>{fix_str}</td>
        </tr>""")

    # World-line history
    hist_rows = []
    for wl in sorted(store.all_lines(), key=lambda w: w.failure_count, reverse=True)[:20]:
        if wl.failure_count == 0 and wl.fix_count == 0:
            continue
        rate_pct = int(wl.recent_failure_rate * 100)
        color = "red" if rate_pct >= 60 else ("amber" if rate_pct >= 30 else "green")
        last_evs = "".join(
            f'<div class="ev {e["kind"]}">{e["ts"][:16]} {e["kind"]}'
            + (f' — {e["detail"][:60]}' if e.get("detail") else "") + "</div>"
            for e in wl.events[-5:]
        )
        hist_rows.append(f"""
        <tr>
          <td class="mono">{wl.node_id}</td>
          <td class="red">{wl.failure_count}</td>
          <td class="green">{wl.fix_count}</td>
          <td><span class="{color}">{rate_pct}%</span></td>
          <td>{last_evs}</td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>wlbs-scan report</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#0d1117;color:#c9d1d9;font-size:13px;line-height:1.5}}
.header{{background:#161b22;border-bottom:1px solid #30363d;padding:20px 32px}}
.header h1{{font-size:22px;color:#58a6ff;font-weight:600}}
.header .sub{{color:#8b949e;margin-top:4px;font-size:13px}}
.stats{{display:flex;gap:24px;padding:20px 32px;border-bottom:1px solid #21262d}}
.stat{{background:#161b22;border:1px solid #30363d;border-radius:8px;
       padding:12px 20px;text-align:center;min-width:100px}}
.stat .num{{font-size:28px;font-weight:700;line-height:1}}
.stat .lbl{{color:#8b949e;font-size:11px;margin-top:4px;text-transform:uppercase}}
.red{{color:#f85149}}.green{{color:#3fb950}}.amber{{color:#e3b341}}
.yellow{{color:#e3b341}}.gray{{color:#8b949e}}
section{{padding:24px 32px}}
h2{{color:#58a6ff;font-size:15px;margin-bottom:14px;font-weight:600}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#161b22;color:#8b949e;padding:8px 10px;text-align:left;
    border-bottom:1px solid #30363d;font-weight:500;text-transform:uppercase;font-size:11px}}
td{{padding:7px 10px;border-bottom:1px solid #21262d;vertical-align:middle}}
tr:hover td{{background:#161b22}}
tr.high td:first-child{{border-left:3px solid #f85149}}
tr.med  td:first-child{{border-left:3px solid #e3b341}}
tr.low  td:first-child{{border-left:3px solid #3fb950}}
.bar-wrap{{background:#21262d;border-radius:3px;height:6px;width:80px;
           display:inline-block;margin-right:8px;vertical-align:middle}}
.bar{{height:6px;border-radius:3px}}
.bar.high{{background:#f85149}}.bar.med{{background:#e3b341}}.bar.low{{background:#3fb950}}
.badge{{font-size:10px;padding:1px 5px;border-radius:3px;margin-left:6px;vertical-align:middle}}
.badge.sing{{background:#3a1a5c;color:#d4b0f0;border:1px solid #7f77dd}}
.badge.warn{{background:#2d1b00;color:#e3b341;border:1px solid #b7791f}}
.mono{{font-family:'SF Mono',Consolas,monospace;font-size:11px}}
.ev{{font-size:11px;padding:2px 0;color:#8b949e}}
.ev.failure{{color:#f85149}}.ev.fix{{color:#3fb950}}
.filter{{margin-bottom:12px}}
.filter input{{background:#21262d;border:1px solid #30363d;color:#c9d1d9;
               padding:6px 12px;border-radius:6px;font-size:13px;width:300px}}
.filter input:focus{{outline:none;border-color:#58a6ff}}
</style>
</head>
<body>
<div class="header">
  <h1>wlbs-scan — Behavior Graph Report</h1>
  <div class="sub">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · v{__version__} · {total} nodes analyzed</div>
</div>

<div class="stats">
  <div class="stat"><div class="num">{total}</div><div class="lbl">Total Nodes</div></div>
  <div class="stat"><div class="num red">{high}</div><div class="lbl">High Risk</div></div>
  <div class="stat"><div class="num amber">{med}</div><div class="lbl">Medium Risk</div></div>
  <div class="stat"><div class="num red">{tf}</div><div class="lbl">Failures Recorded</div></div>
  <div class="stat"><div class="num green">{tfx}</div><div class="lbl">Fixes Recorded</div></div>
  <div class="stat"><div class="num yellow">{len(sings)}</div><div class="lbl">Singularities</div></div>
</div>

<section>
  <h2>Behavior Graph — Node Curvature</h2>
  <div class="filter"><input type="text" id="q" placeholder="Filter by node name..." oninput="filterTable()"></div>
  <table id="nodeTable">
    <thead><tr>
      <th>κ (curvature)</th><th>Node ID</th><th>Kind</th>
      <th>Complexity</th><th>Lines</th><th>Git Δ</th><th>Failures</th><th>Fixes</th>
    </tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</section>

{"<section><h2>World-Line History — Learned Failures</h2><table><thead><tr><th>Node</th><th>Failures</th><th>Fixes</th><th>Recent Rate</th><th>Last 5 Events</th></tr></thead><tbody>" + "".join(hist_rows) + "</tbody></table></section>" if hist_rows else ""}

<script>
function filterTable() {{
  const q = document.getElementById('q').value.toLowerCase();
  document.querySelectorAll('#nodeTable tbody tr').forEach(r => {{
    r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}
</script>
</body></html>"""

    out_path.write_text(html, encoding="utf-8")
    return len(nodes)


# ── pre-commit hook installer ──────────────────────────────────────────────────
HOOK_SCRIPT = """#!/bin/sh
# wlbs-scan pre-commit hook
# Runs behavior graph scan; exits 1 if any node exceeds curvature threshold

WLBS_THRESHOLD=${WLBS_THRESHOLD:-0.90}
WLBS_PATH=$(git rev-parse --show-toplevel)

if command -v wlbs-scan > /dev/null 2>&1; then
    wlbs-scan "$WLBS_PATH" --ci --fail-above "$WLBS_THRESHOLD" --no-singularities
else
    python3 -m wlbs_scan "$WLBS_PATH" --ci --fail-above "$WLBS_THRESHOLD" --no-singularities 2>/dev/null || true
fi
"""

def install_hook(root: Path) -> bool:
    hooks_dir = root / ".git" / "hooks"
    if not hooks_dir.exists():
        return False
    hook_path = hooks_dir / "pre-commit"
    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8")
        if "wlbs-scan" in existing:
            return True  # already installed
        # Append to existing hook
        hook_path.write_text(existing.rstrip() + "\n\n" + HOOK_SCRIPT, encoding="utf-8")
    else:
        hook_path.write_text(HOOK_SCRIPT, encoding="utf-8")
    hook_path.chmod(0o755)
    return True


# ── Runtime curvature (sys.settrace dynamic tracing) ─────────────────────────
def run_with_tracing(test_path, project_root, store, file_to_module):
    import tempfile, threading
    call_counts = {}
    fail_calls  = {}
    _local = threading.local()
    file_map = {str(Path(k).resolve()): v for k, v in file_to_module.items()}

    def tracer(frame, event, arg):
        if event != "call": return tracer
        resolved = str(Path(frame.f_code.co_filename).resolve())
        mname = file_map.get(resolved)
        if not mname: return tracer
        func = frame.f_code.co_name
        nid = f"{mname}.{func}" if func != "<module>" else mname
        call_counts[nid] = call_counts.get(nid, 0) + 1
        if getattr(_local, "in_fail", False):
            fail_calls[nid] = fail_calls.get(nid, 0) + 1
        return tracer

    import xml.etree.ElementTree as _ET
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        xml_path = f.name
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_path),
             f"--junit-xml={xml_path}", "-q", "--tb=no"],
            cwd=project_root, capture_output=True, text=True, timeout=120)
    except Exception as e:
        return {"error": str(e)}
    failed_tests = set()
    try:
        tree = _ET.parse(xml_path)
        for tc in tree.getroot().findall(".//testcase"):
            if tc.findall("failure") or tc.findall("error"):
                failed_tests.add(tc.get("name",""))
    except Exception: pass
    finally:
        try: os.unlink(xml_path)
        except: pass

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        xml_path2 = f.name
    old_trace = sys.gettrace()
    sys.settrace(tracer)
    try:
        import pytest as _pt
        class _FP:
            def pytest_runtest_setup(self, item):
                _local.in_fail = item.name in failed_tests
            def pytest_runtest_teardown(self, item, nextitem):
                _local.in_fail = False
        _pt.main([str(test_path), "-q", "--tb=no",
                  f"--junit-xml={xml_path2}"], plugins=[_FP()])
    except Exception: pass
    finally:
        sys.settrace(old_trace)
        try: os.unlink(xml_path2)
        except: pass

    total_fail = sum(fail_calls.values()) or 1
    recorded = []
    for nid, fc in fail_calls.items():
        ratio = fc / total_fail
        if ratio >= 0.05:
            store.record_failure(nid, f"runtime: {fc} calls during failing tests ({ratio*100:.1f}%)")
            recorded.append(nid)
    return {"total_nodes_traced": len(call_counts),
            "failing_test_nodes": len(fail_calls),
            "recorded": recorded, "failed_tests": list(failed_tests)}

# ── MoE expert routing suggestion ────────────────────────────────────────────
def print_moe_routing(graph, store):
    sings  = {s.id for s in find_singularities(graph)}
    nodes  = sorted(graph.nodes.values(), key=lambda n: n.curvature, reverse=True)
    active = [n for n in nodes if n.curvature >= 0.4][:12]
    total_k = sum(n.curvature for n in active) or 1.0

    print()
    print(colored("━"*60, CYAN, BOLD))
    print(colored("  MoE Expert Routing — WLBS-guided activation map", WHITE, BOLD))
    print(colored("━"*60, CYAN, BOLD))
    print(colored("  p(expert_n) = κ(n) / Σκ    [top-k gate routing]", GRAY))
    print()
    print(colored(f"  {'WEIGHT':>7}  {'EXPERT (node)':44}  ROLE", GRAY))
    print(colored("  " + "─"*68, GRAY))

    for node in active:
        weight = node.curvature / total_k
        pct    = int(weight * 100)
        bar    = colored("█" * min(pct // 3, 18),
                         RED if node.curvature >= 0.7 else
                         YELLOW if node.curvature >= 0.4 else GREEN)
        if node.id in sings:
            role = colored("root-cause expert  ★", YELLOW)
        elif node.failure_count >= 2:
            role = colored("repair specialist  ↑", RED)
        elif node.fix_count > 0:
            role = colored("stabilized         ✓", GREEN)
        elif node.git_change_count > 8:
            role = colored("high-churn         ⚡", MAGENTA)
        elif node.complexity > 12:
            role = colored("complexity         ⚙", CYAN)
        else:
            role = colored("general", GRAY)
        print(f"  {pct:6}%  {bar} {colored(node.id, WHITE):<46} {role}")
        if node.failure_count > 0:
            print(colored(f"          ↳ world-line: {node.failure_count} fail "
                          f"{node.fix_count} fix  rate={node.recent_failure_rate*100:.0f}%", GRAY))

    print()
    print(colored("  In a MoE+WLBS system, high-κ nodes activate specialized LoRA adapters.", GRAY))
    print(colored("  Singularities are targeted first when failure propagates upstream.", GRAY))
    print(colored("━"*60, CYAN))
    print()

# ── README badge generator ────────────────────────────────────────────────────
def print_badges(graph, store, root):
    nodes  = list(graph.nodes.values())
    total  = len(nodes)
    high   = sum(1 for n in nodes if n.curvature >= 0.7)
    sings  = find_singularities(graph)
    tf, tfx = store.total_failures, store.total_fixes
    avg_k  = sum(n.curvature for n in nodes) / total if total else 0
    health = max(0, int((1 - avg_k) * 100))
    hc = "brightgreen" if health >= 80 else ("yellow" if health >= 60 else "red")
    def shield(label, val, color):
        l = label.replace("-","--").replace(" ","_")
        v = str(val).replace("-","--").replace(" ","_")
        return f"https://img.shields.io/badge/{l}-{v}-{color}"
    badges = [
        ("wlbs_health",     f"{health}%", hc),
        ("high_risk_nodes", str(high), "red" if high > 0 else "brightgreen"),
        ("singularities",   str(len(sings)), "orange" if sings else "brightgreen"),
        ("failures_recorded", str(tf), "red" if tf > 0 else "brightgreen"),
    ]
    print()
    print(colored("━"*55, CYAN, BOLD))
    print(colored("  README Badges", WHITE, BOLD))
    print(colored("━"*55, CYAN, BOLD))
    print()
    for label, val, color in badges:
        url = shield(label, val, color)
        print(f"  [![{label}]({url})]()")
    print()
    print(colored("━"*55, CYAN))
    print()

# ── Watch + auto-pytest ────────────────────────────────────────────────────────
def watch_with_pytest(root, test_path, store, lang, interval=10):
    import hashlib
    def _hash(root, lang):
        exts = {".py"} if lang=="python" else {".js",".ts",".jsx",".tsx"}
        skip = {"__pycache__",".git",".wlbs","node_modules","venv",".venv"}
        h = hashlib.md5()
        for p in sorted(root.rglob("*")):
            if any(x in p.parts for x in skip): continue
            if p.suffix in exts:
                try: h.update(p.read_bytes())
                except: pass
        return h.hexdigest()

    print(colored(f"  Watch+pytest mode  (Ctrl+C to stop)", CYAN))
    last_hash = _hash(root, lang)
    last_run  = 0.0
    while True:
        try:
            time.sleep(interval)
            curr = _hash(root, lang)
            if curr != last_hash or (time.time()-last_run) > 120:
                last_hash = curr; last_run = time.time()
                ts = datetime.now().strftime("%H:%M:%S")
                print(colored(f"  [{ts}] Change detected — running pytest...", CYAN))
                graph   = build_graph(root, lang=lang)
                results = _run_pytest_and_record(test_path, root, store, graph.file_to_module)
                if "error" in results:
                    print(colored(f"  ✗ {results['error']}", RED))
                else:
                    ps = colored(str(results["passed"]), GREEN)
                    fs = colored(str(results["failed"]), RED) if results["failed"] else colored("0",GREEN)
                    print(colored(f"  ✓ {ps} passed  {fs} failed", WHITE))
                    for kind, nid, _ in results.get("recorded",[])[:3]:
                        print(f"    {colored('✗',RED) if kind=='failure' else colored('✓',GREEN)} {nid}")
                compute_curvature(graph, store=store)
                save_snapshot(graph, root)
                top3 = sorted(graph.nodes.values(), key=lambda n:n.curvature, reverse=True)[:3]
                print(colored("  Top-κ: " + "  ".join(f"{n.id}={n.curvature:.3f}" for n in top3), GRAY))
                print()
        except KeyboardInterrupt:
            print(colored("\n  Stopped.", GRAY)); break

def main():
    p=argparse.ArgumentParser(prog="wlbs-scan",
        description="WLBS scanner — learns from failures, gets smarter over time",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  wlbs-scan .                                  # scan project
  wlbs-scan . --record-failure rbac            # test just failed in rbac
  wlbs-scan . --record-failure rbac.RBACManager.grant_permissions --detail "NoneType"
  wlbs-scan . --record-fix roles               # you just fixed roles.py
  wlbs-scan . --history                        # what has it learned
  wlbs-scan . --json | jq '.singularities'     # CI/CD integration
  wlbs-scan . --dist roles rbac                # behavioral distance
  wlbs-scan . --reset                          # clear all memory
  wlbs-scan . --runtime tests/                 # runtime tracing (dynamic curvature)
  wlbs-scan . --moe                            # MoE expert routing map
  wlbs-scan . --badges                         # README shield badges
  wlbs-scan . --watch --pytest tests/          # watch + auto-pytest
        """)
    p.add_argument("path")
    p.add_argument("--top",type=int,default=15)
    p.add_argument("--json",action="store_true")
    p.add_argument("--since",type=float,metavar="DAYS")
    p.add_argument("--watch",action="store_true")
    p.add_argument("--threshold",type=float,default=0.55)
    p.add_argument("--no-singularities",action="store_true")
    p.add_argument("--dist",nargs=2,metavar=("SRC","DST"))
    p.add_argument("--history",action="store_true")
    p.add_argument("--record-failure",metavar="NODE")
    p.add_argument("--record-fix",metavar="NODE")
    p.add_argument("--detail",metavar="MSG",default="")
    p.add_argument("--reset",action="store_true")
    p.add_argument("--version",action="version",version=f"wlbs-scan {__version__}")
    p.add_argument("--pytest",metavar="TEST_PATH",
                   help="Run pytest and auto-record results into world-lines")
    p.add_argument("--ci",action="store_true",
                   help="CI mode: exit 1 if any node exceeds --fail-above threshold")
    p.add_argument("--fail-above",type=float,default=0.85,metavar="K",
                   help="CI failure threshold (default 0.85)")
    p.add_argument("--suggest",action="store_true",
                   help="Show actionable suggestions for high-risk nodes")
    p.add_argument("--blame",action="store_true",
                   help="Show git blame for high-curvature nodes")
    p.add_argument("--lang",default="python",metavar="LANG",
                   help="Language: python (default), js, ts")
    p.add_argument("--diff",action="store_true",
                   help="Show curvature changes since last scan")
    p.add_argument("--export-html",metavar="FILE",
                   help="Export HTML visualization report")
    p.add_argument("--init-hook",action="store_true",
                   help="Install wlbs-scan as git pre-commit hook")
    p.add_argument("--runtime",metavar="TEST_PATH",
                   help="Run pytest with sys.settrace dynamic call tracing")
    p.add_argument("--moe",action="store_true",
                   help="Show MoE expert routing suggestions based on curvature")
    p.add_argument("--badges",action="store_true",
                   help="Print README shield badge markdown")
    args=p.parse_args()

    root=Path(args.path).resolve()
    if not root.exists():
        print(f"Error: not found: {root}",file=sys.stderr); sys.exit(1)
    if root.is_file(): root=root.parent

    store=WorldLineStore(root)

    if args.reset:
        store.reset(); print(colored("  Memory cleared.",GREEN)); return

    if args.pytest:
        test_path = Path(args.pytest)
        if not test_path.exists():
            print(colored(f"  Error: test path not found: {test_path}", RED))
            sys.exit(1)
        print(colored(f"  Running pytest on {test_path}...", CYAN))
        # Build graph first to get file→module mapping
        graph = build_graph(root, lang=args.lang)
        results = _run_pytest_and_record(test_path, root, store, graph.file_to_module)
        if "error" in results:
            print(colored(f"  ✗ pytest failed: {results['error']}", RED))
        else:
            print(colored(f"  ✓ {results['passed']} passed  "
                         f"{colored(str(results['failed']), RED)} failed", GREEN))
            for kind, nid, detail in results.get("recorded", []):
                icon = colored("✗", RED) if kind == "failure" else colored("✓", GREEN)
                print(f"    {icon} {kind}: {colored(nid, CYAN)}")
                if detail: print(colored(f"       {detail[:70]}", GRAY))
        print(colored(f"  World-lines updated: .wlbs/world_lines.json", GRAY))
        return

    if args.record_failure:
        store.record_failure(args.record_failure, args.detail)
        wl=store.get(args.record_failure)
        print(colored(f"  ✗ Failure recorded: {args.record_failure}",RED))
        if args.detail: print(colored(f"    {args.detail}",GRAY))
        print(colored(f"    Total: {wl.failure_count} failures, {wl.fix_count} fixes "
                      f"(rate {wl.recent_failure_rate*100:.0f}%)",GRAY))
        return

    if args.record_fix:
        store.record_fix(args.record_fix, args.detail)
        print(colored(f"  ✓ Fix recorded: {args.record_fix}",GREEN))
        return

    if args.history:
        print_history(store); return

    if args.init_hook:
        if install_hook(root):
            print(colored("  ✓ pre-commit hook installed in .git/hooks/pre-commit", GREEN))
            print(colored("  Set WLBS_THRESHOLD=0.85 to customize the fail threshold.", GRAY))
        else:
            print(colored("  ✗ Not a git repository (no .git/hooks/ found)", RED))
        return

    if args.export_html:
        graph = build_graph(root, since_days=args.since, lang=args.lang)
        compute_curvature(graph, store=store)
        out = Path(args.export_html)
        n = export_html(graph, store, out)
        print(colored(f"  ✓ HTML report: {out}  ({n} nodes)", GREEN))
        return

    if args.runtime:
        tp = Path(args.runtime)
        if not tp.exists():
            print(colored(f"  Error: not found: {tp}", RED)); sys.exit(1)
        print(colored(f"  Running with runtime tracing on {tp}...", CYAN))
        graph   = build_graph(root, lang=args.lang)
        results = run_with_tracing(tp, root, store, graph.file_to_module)
        if "error" in results:
            print(colored(f"  ✗ {results['error']}", RED))
        else:
            print(colored(f"  ✓ Traced {results['total_nodes_traced']} nodes", GREEN))
            print(colored(f"    {results['failing_test_nodes']} nodes in failing-test call stacks", GRAY))
            if results["recorded"]:
                print(colored(f"    World-lines updated ({len(results['recorded'])} nodes):", GRAY))
                for nid in results["recorded"][:6]:
                    print(colored(f"      ↑ {nid}", RED))
            if results["failed_tests"]:
                print(colored(f"    Failing: {', '.join(list(results['failed_tests'])[:3])}", GRAY))
        return

    if args.badges:
        graph = build_graph(root, since_days=args.since, lang=args.lang)
        compute_curvature(graph, store=store)
        print_badges(graph, store, root)
        return

    _ci_failed = False
    def scan():
        nonlocal _ci_failed
        graph=build_graph(root, since_days=args.since, lang=args.lang)
        compute_curvature(graph, store=store)
        if args.diff:
            print_diff(graph, root)
            save_snapshot(graph, root)
            return
        save_snapshot(graph, root)
        if args.dist:
            src,dst=args.dist; d=behavioral_distance(graph,src,dst)
            label=f"{d} hop(s)" if d<999 else "unreachable"
            if args.json: print(json.dumps({"src":src,"dst":dst,"distance":d}))
            else: print(f"\n  d({colored(src,CYAN)}, {colored(dst,CYAN)}) = {colored(label,WHITE,BOLD)}\n")
            return
        if args.suggest:
            print_suggestions(graph, store)
            return
        if args.blame:
            print_blame(graph, root, top_n=args.top)
            return
        if args.moe:
            print_moe_routing(graph, store)
            return
        if args.json:
            print(json.dumps(report_json(graph,store),indent=2,ensure_ascii=False))
        else:
            print_report(graph,store,top_n=args.top,show_sing=not args.no_singularities)
        # CI mode: fail if any node exceeds threshold
        if args.ci:
            bad = [n for n in graph.nodes.values() if n.curvature >= args.fail_above]
            if bad:
                print(colored(f"  CI FAIL: {len(bad)} node(s) above κ={args.fail_above}", RED, BOLD))
                for n in sorted(bad, key=lambda x: x.curvature, reverse=True)[:5]:
                    print(colored(f"    {n.id}  κ={n.curvature:.3f}", RED))
                _ci_failed = True
            else:
                print(colored(f"  CI PASS: all nodes below κ={args.fail_above}", GREEN))

    if args.watch and args.pytest:
        watch_with_pytest(root, Path(args.pytest), store, args.lang)
    elif args.watch:
        import hashlib
        def _fhash(r):
            skip = {"__pycache__",".git",".wlbs","node_modules","venv",".venv"}
            exts = {".py"} if args.lang=="python" else {".js",".ts",".jsx",".tsx"}
            h = hashlib.md5()
            for p in sorted(r.rglob("*")):
                if any(x in p.parts for x in skip): continue
                if p.suffix in exts:
                    try: h.update(p.read_bytes())
                    except: pass
            return h.hexdigest()
        print(colored(f"  Watching {root} for changes (Ctrl+C to stop)", GRAY))
        last = _fhash(root)
        scan()
        while True:
            try:
                time.sleep(5)
                curr = _fhash(root)
                if curr != last:
                    last = curr
                    ts = datetime.now().strftime("%H:%M:%S")
                    print(colored(f"  [{ts}] Change detected — rescanning...", CYAN))
                    scan()
            except KeyboardInterrupt: print("\n  Stopped."); break
    else:
        scan()
        if _ci_failed:
            sys.exit(1)

if __name__=="__main__":
    main()
