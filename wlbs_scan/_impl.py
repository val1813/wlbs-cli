#!/usr/bin/env python3
"""
wlbs-scan v0.6 — WLBS Behavior Graph Scanner
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
import ast, argparse, importlib.util, json, os, subprocess, sys, time, uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

__version__ = "0.6.1"

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
        self.task_memory: dict[str, dict] = {}
        self.routing_stats: dict[str, float | int] = {
            "total_tasks": 0,
            "suggestion_follow_rate": 0.0,
            "suggestion_accuracy": 0.0,
            "avg_test_improvement": 0.0,
        }
        self.routing_policy: dict[str, dict[str, float | int]] = {}
        self._load()
    def _load(self):
        if not self.path.exists(): return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for nid, wl_data in data.get("world_lines", {}).items():
                wl = WorldLine(node_id=nid)
                wl.events = wl_data.get("events", [])
                self._lines[nid] = wl
            self.task_memory = data.get("task_memory", {}) or {}
            stats = data.get("routing_stats", {}) or {}
            self.routing_stats.update(stats)
            self.routing_policy = data.get("routing_policy", {}) or {}
        except Exception: pass
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": __version__,
                "updated": datetime.now(timezone.utc).isoformat(),
                "world_lines": {nid: {"events": wl.events}
                                for nid, wl in self._lines.items()},
                "task_memory": self.task_memory,
                "routing_stats": self.routing_stats,
                "routing_policy": self.routing_policy}
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    def get(self, nid: str) -> WorldLine:
        if nid not in self._lines: self._lines[nid] = WorldLine(node_id=nid)
        return self._lines[nid]
    def record_failure(self, nid, detail=""):
        self.get(nid).append("failure", detail); self.save()
    def record_fix(self, nid, detail=""):
        self.get(nid).append("fix", detail); self.save()
    def record_outcome(self, task_record: dict):
        task_id = task_record["task_id"]
        self.task_memory[task_id] = task_record
        self._update_routing_policy(task_record)
        self._recompute_routing_stats()
        self.save()
    def _update_routing_policy(self, task_record: dict, alpha: float = 0.3):
        suggested = task_record.get("wlbs_suggested_target") or ""
        symptom = task_record.get("symptom") or ""
        if not suggested or not symptom:
            return
        key = f"{symptom}->{suggested}"
        current = float(self.routing_policy.get(key, {}).get("confidence", 0.75))
        followed = bool(task_record.get("suggestion_was_followed"))
        result = task_record.get("result")
        if followed and result == "pass":
            reward = 1.0
            outcome = "pass_followed"
        elif (not followed) and result == "pass":
            reward = -0.2
            outcome = "pass_ignored"
        elif followed and result == "fail":
            reward = -1.0
            outcome = "fail_followed"
        else:
            reward = 0.0
            outcome = "fail_ignored"
        updated = max(0.0, min(1.0, current * (1 - alpha) + reward * alpha))
        self.routing_policy[key] = {
            "confidence": round(updated, 3),
            "updates": int(self.routing_policy.get(key, {}).get("updates", 0)) + 1,
            "last_outcome": outcome,
        }
    def _recompute_routing_stats(self):
        tasks = list(self.task_memory.values())
        total = len(tasks)
        if total == 0:
            self.routing_stats = {
                "total_tasks": 0,
                "suggestion_follow_rate": 0.0,
                "suggestion_accuracy": 0.0,
                "avg_test_improvement": 0.0,
            }
            return
        followed = sum(1 for t in tasks if t.get("suggestion_was_followed"))
        accurate = sum(
            1 for t in tasks
            if (t.get("suggestion_was_followed") and t.get("result") == "pass")
        )
        improvements = [t.get("test_delta", 0) for t in tasks]
        self.routing_stats = {
            "total_tasks": total,
            "suggestion_follow_rate": round(followed / total, 3),
            "suggestion_accuracy": round(accurate / total, 3),
            "avg_test_improvement": round(sum(improvements) / total, 3),
        }
    def reset(self):
        if self.path.exists(): self.path.unlink()
        self._lines = {}
        self.task_memory = {}
        self.routing_stats = {
            "total_tasks": 0,
            "suggestion_follow_rate": 0.0,
            "suggestion_accuracy": 0.0,
            "avg_test_improvement": 0.0,
        }
        self.routing_policy = {}
    def all_lines(self): return list(self._lines.values())
    def all_tasks(self): return list(self.task_memory.values())
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
            dep_ids = _resolve_dependency_targets(graph, node.calls, _bp_idx)
            for dep_id in dep_ids:
                if dep_id not in graph.nodes: continue
                contrib = round(seed_k * (DECAY ** depth), 4)
                graph.nodes[dep_id].curvature = round(
                    min(graph.nodes[dep_id].curvature + contrib, 1.0), 3)
                if dep_id not in visited:
                    visited.add(dep_id); queue.append((dep_id, depth + 1))

def _resolve_dependency_targets(graph: BehaviorGraph, calls: list[str], idx: Optional[dict] = None) -> set[str]:
    if idx is None:
        idx = defaultdict(list)
        for nid in graph.nodes:
            idx[nid.split(".")[-1]].append(nid)
    dep_ids: set[str] = set()
    for short in calls:
        for cand in idx.get(short, []):
            dep_ids.add(cand)
        if short in graph.nodes:
            dep_ids.add(short)
    return dep_ids

def _downstream_failure_count(graph: BehaviorGraph, start_id: str) -> int:
    """Count failure events in dependent nodes reachable downstream of start_id.

    A singularity is meant to surface an upstream candidate whose own world-line
    stays clean while failures keep appearing in nodes that depend on it.
    """
    if start_id not in graph.nodes:
        return 0
    total = 0
    visited = {start_id}
    queue = [start_id]
    while queue:
        current = queue.pop(0)
        node = graph.nodes.get(current)
        if not node:
            continue
        for dep_id in node.called_by:
            if dep_id in visited or dep_id not in graph.nodes:
                continue
            visited.add(dep_id)
            dep_node = graph.nodes[dep_id]
            total += dep_node.failure_count
            queue.append(dep_id)
    return total

def find_singularities(graph: BehaviorGraph, threshold=0.55):
    out = []
    for node in graph.nodes.values():
        if node.curvature < threshold:
            continue
        if node.failure_count > 0:
            continue
        if node.complexity < 2:
            continue
        downstream_failures = _downstream_failure_count(graph, node.id)
        if downstream_failures < 2:
            continue
        if len(node.called_by) == 0 and node.is_imported_by_count == 0:
            continue
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
        neighbors.extend(_resolve_dependency_targets(graph, node.calls, idx))
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
    tasks = sorted(store.all_tasks(), key=lambda t: t.get("ts", ""), reverse=True)
    if not lines and not tasks:
        print(colored("\n  No history yet.\n",GRAY)); return
    lines.sort(key=lambda w: w.failure_count, reverse=True)
    print()
    print(colored("━"*55,CYAN,BOLD))
    print(colored("  World-Line History — what the system has learned",WHITE,BOLD))
    print(colored("━"*55,CYAN,BOLD))
    print(colored(
        f"  World-line events: {sum(len(w.events) for w in store.all_lines())}  "
        f"Task memory: {len(tasks)} task(s)",
        GRAY,
    ))
    print()
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
    if tasks:
        print()
        print(colored("  Recent tasks:", WHITE, BOLD))
        for task in tasks[:5]:
            status_color = GREEN if task.get("result") == "pass" else RED
            delta = task.get("test_delta", 0)
            delta_txt = f"{delta:+d} tests" if isinstance(delta, int) else str(delta)
            followed = "followed ✓" if task.get("suggestion_was_followed") else "followed no"
            print(
                f"    {task['task_id']}  {task.get('symptom')} -> {task.get('final_target')}  "
                f"{colored(task.get('result','').upper(), status_color)}  {delta_txt}"
            )
            print(colored(
                f"                   wlbs suggestion: {task.get('wlbs_suggested_target')}  ({followed})",
                GRAY,
            ))
        print()
        stats = store.routing_stats
        print(colored(
            f"  Routing accuracy:  {stats['suggestion_accuracy']*100:.0f}%   "
            f"Follow rate: {stats['suggestion_follow_rate']*100:.0f}%   "
            f"Avg test improvement: {stats['avg_test_improvement']:+.2f}",
            GRAY,
        ))
    print(colored("━"*55,CYAN))
    print()

def print_advisory(payload: dict):
    primary = payload["advisory"]["primary_suggestion"]
    print()
    print(colored("━"*60, CYAN, BOLD))
    print(colored(f"  Advisory  symptom={payload['symptom']}", WHITE, BOLD))
    print(colored("━"*60, CYAN, BOLD))
    print(colored(
        f"  wlbs thinks: {primary['text']}  "
        f"(confidence={primary['confidence']:.2f}, tone={primary['tone']})",
        YELLOW if primary["tone"] == "suggestion" else GRAY,
    ))
    if primary.get("reasoning"):
        print(colored("  Why:", WHITE, BOLD))
        for item in primary["reasoning"]:
            print(colored(f"    - {item}", GRAY))
    if payload["advisory"].get("alternative_suggestions"):
        print(colored("  Alternatives:", WHITE, BOLD))
        for alt in payload["advisory"]["alternative_suggestions"]:
            print(colored(
                f"    - {alt['text']} (confidence={alt['confidence']:.2f})",
                GRAY,
            ))
    if payload["advisory"].get("open_questions"):
        print(colored("  Open questions:", WHITE, BOLD))
        for question in payload["advisory"]["open_questions"]:
            print(colored(f"    - {question}", GRAY))
    print(colored("━"*60, CYAN))
    print()

def query_points(api_key: str, hub_url: str) -> dict | None:
    try:
        from wlbs_scan.cloud import cmd_account_status
        return cmd_account_status(api_key=api_key, hub_url=hub_url)
    except Exception:
        return None

def write_auto_advice(graph: BehaviorGraph, store: WorldLineStore, root: Path, api_key: str, hub_url: str):
    sings = find_singularities(graph)
    high_risk = sorted([n for n in graph.nodes.values() if n.curvature >= 0.5], key=lambda n: n.curvature, reverse=True)[:5]
    advice_path = root / ".wlbs" / "current_advice.md"
    advice_path.parent.mkdir(parents=True, exist_ok=True)
    if not high_risk and not sings:
        advice_path.write_text("<!-- wlbs: no high-risk nodes detected -->", encoding="utf-8")
        return
    lines = [
        "<!-- wlbs-scan auto-advice (Pro) -->",
        f"<!-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} -->",
        "",
    ]
    if sings:
        lines.append("## Likely Root Causes (Singularities)")
        for s in sings[:2]:
            node = graph.nodes[s.id]
            suggestion = build_repair_suggestion(graph, store, s.id)
            first_reason = suggestion["reasoning_chain"][0] if suggestion["reasoning_chain"] else "high curvature upstream node"
            lines.append(f"- **{s.id}** (kappa={node.curvature:.2f}): {first_reason}")
        lines.append("")
    lines.append("## High-Risk Files")
    for node in high_risk:
        flag = " ROOT-CAUSE" if node.id in {s.id for s in sings} else ""
        lines.append(f"- `{node.id}` - kappa={node.curvature:.2f}, failures={node.failure_count}{flag}")
    points_info = query_points(api_key, hub_url) if api_key else None
    cloud_lines = []
    if api_key:
        try:
            from wlbs_scan.cloud import cmd_download_crystals
            crystals = cmd_download_crystals(api_key=api_key, hub_url=hub_url).get("crystals", [])
            for crystal in crystals[:3]:
                rule = crystal.get("rule", "")
                if rule:
                    cloud_lines.append(f"- {rule}")
        except Exception:
            pass
    if points_info:
        lines.extend([
            "",
            "## Account",
            f"- Tier: {points_info.get('tier', 'free')}",
            f"- Points: {points_info.get('points', 0)} / 100",
        ])
    if cloud_lines:
        lines.extend(["", "## Shared Experience", *cloud_lines])
    lines.extend([
        "",
        "## Suggestion",
        "Investigate singularity nodes before modifying symptom files.",
    ])
    advice_path.write_text("\n".join(lines), encoding="utf-8")

def print_status(graph: BehaviorGraph, store: WorldLineStore, api_key: str = "", hub_url: str = ""):
    sings = find_singularities(graph)
    high_risk = sorted([n for n in graph.nodes.values() if n.curvature >= 0.4], key=lambda n: n.curvature, reverse=True)[:10]
    print()
    print(colored("━"*55, CYAN, BOLD))
    print(colored("  wlbs-scan Status", WHITE, BOLD))
    print(colored("━"*55, CYAN, BOLD))
    if sings:
        print()
        print(colored("  Likely root causes:", YELLOW, BOLD))
        for s in sings[:3]:
            node = graph.nodes[s.id]
            print(colored(f"    * {s.id}  kappa={node.curvature:.3f}  failures={node.failure_count}", RED))
    if high_risk:
        print()
        print(colored("  High-risk files to investigate:", WHITE, BOLD))
        for node in high_risk[:5]:
            flag = " SINGULARITY" if node.id in {s.id for s in sings} else ""
            print(f"    {colored(node.id, WHITE)}  kappa={node.curvature:.3f}{colored(flag, RED) if flag else ''}")
    if api_key:
        info = query_points(api_key, hub_url)
        if info:
            print()
            print(colored("  Account:", WHITE, BOLD))
            print(colored(f"    Points: {info.get('points', 0):.1f} / 100", CYAN))
            print(colored(f"    Tier:   {info.get('tier', 'free')}", GRAY))
            expires = info.get("key_expires_at", "")
            if expires:
                print(colored(f"    Key expires: {expires[:10]}", GRAY))
    else:
        print()
        print(colored("  Add --api-key <key> to see account info", GRAY))
    print()
    print(colored("━"*55, CYAN))
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
        "task_memory_count": len(store.task_memory),
        "routing_stats": store.routing_stats,
        "singularities": [s.id for s in sings],
        "nodes": [
            {"id":n.id,"file":n.file,"kind":n.kind,
             "curvature":n.curvature,"static":n.static_curvature,
             "history":n.history_curvature,"git":n.git_curvature,
             "complexity":n.complexity,"lines":n.line_count,
             "git_changes":n.git_change_count,
             "failures":n.failure_count,"fixes":n.fix_count,
             "downstream_failures":_downstream_failure_count(graph, n.id),
             "recent_failure_rate":n.recent_failure_rate,
             "is_singularity":n.id in sing_ids}
            for n in sorted(graph.nodes.values(),key=lambda n:n.curvature,reverse=True)
        ]
    }

def _distance_map(graph: BehaviorGraph, focus: str) -> dict[str, int]:
    if focus not in graph.nodes:
        return {}
    idx: dict = defaultdict(list)
    for nid in graph.nodes:
        idx[nid.split(".")[-1]].append(nid)
    distances = {focus: 0}
    queue = [focus]
    while queue:
        current = queue.pop(0)
        node = graph.nodes.get(current)
        if not node:
            continue
        neighbors = set(node.called_by)
        neighbors.update(_resolve_dependency_targets(graph, node.calls, idx))
        for neighbor in neighbors:
            if neighbor not in graph.nodes or neighbor in distances:
                continue
            distances[neighbor] = distances[current] + 1
            queue.append(neighbor)
    return distances

def assemble_resolution_context(graph: BehaviorGraph, store: WorldLineStore, focus: str,
                                near_distance: int = 1, mid_distance: int = 2,
                                near_events: int = 5, mid_events: int = 2) -> dict:
    """Build a three-tier context view as described in PAPER §3.3.

    Tier 1 (near): full-fidelity local neighborhood with recent world-line events.
    Tier 2 (mid): summarized metadata with the most recent event only.
    Tier 3 (far): compressed structural summary for all other reachable nodes.
    """
    distances = _distance_map(graph, focus)
    if not distances:
        raise KeyError(focus)
    sings = {s.id for s in find_singularities(graph)}
    tiers = {"near": [], "mid": [], "far": []}
    for nid, dist in sorted(distances.items(), key=lambda item: (item[1], -graph.nodes[item[0]].curvature, item[0])):
        node = graph.nodes[nid]
        wl = store._lines.get(nid)
        base = {
            "id": nid,
            "distance": dist,
            "kind": node.kind,
            "curvature": node.curvature,
            "static": node.static_curvature,
            "failures": node.failure_count,
            "fixes": node.fix_count,
            "downstream_failures": _downstream_failure_count(graph, nid),
            "is_singularity": nid in sings,
        }
        if dist <= near_distance:
            item = dict(base)
            item.update({
                "calls": sorted(_resolve_dependency_targets(graph, node.calls)),
                "called_by": sorted(node.called_by),
                "recent_events": (wl.events[-near_events:] if wl else []),
            })
            tiers["near"].append(item)
        elif dist <= mid_distance:
            item = dict(base)
            item.update({
                "calls_count": len(_resolve_dependency_targets(graph, node.calls)),
                "called_by_count": len(node.called_by),
                "recent_event": (wl.events[-1] if wl and wl.events else None),
            })
            tiers["mid"].append(item)
        else:
            tiers["far"].append({
                "id": nid,
                "distance": dist,
                "curvature": node.curvature,
                "is_singularity": nid in sings,
            })
    approx_units = (
        sum(8 + len(item.get("recent_events", [])) * 6 for item in tiers["near"]) +
        sum(4 for _ in tiers["mid"]) +
        sum(2 for _ in tiers["far"])
    )
    return {
        "focus": focus,
        "focus_curvature": graph.nodes[focus].curvature,
        "tiers": tiers,
        "tier_counts": {name: len(items) for name, items in tiers.items()},
        "approx_context_units": approx_units,
    }

def _choose_repair_target(graph: BehaviorGraph, focus: str, context: dict) -> str:
    if focus not in graph.nodes:
        return focus
    near_nodes = context["tiers"]["near"]
    candidates = sorted(
        near_nodes,
        key=lambda item: (
            0 if item["is_singularity"] else 1,
            -item["downstream_failures"],
            -item["curvature"],
            item["distance"],
            item["id"],
        ),
    )
    for item in candidates:
        if item["id"] != focus and (item["is_singularity"] or item["curvature"] >= graph.nodes[focus].curvature):
            return item["id"]
    return focus

def build_repair_suggestion(graph: BehaviorGraph, store: WorldLineStore, focus: str) -> dict:
    context = assemble_resolution_context(graph, store, focus)
    target = _choose_repair_target(graph, focus, context)
    focus_node = graph.nodes[focus]
    target_node = graph.nodes[target]
    target_distance = next((item["distance"] for item in context["tiers"]["near"] if item["id"] == target), None)
    evidence = []
    if target != focus:
        evidence.append(
            f"symptom appears at {focus}, but higher-priority upstream candidate "
            f"{target} sits {target_distance if target_distance is not None else '?'} hop(s) away"
        )
    if target in {item['id'] for item in context["tiers"]["near"] if item["is_singularity"]}:
        evidence.append(f"{target} is a singularity: no direct failures, but downstream failures accumulated behind it")
    if target_node.curvature > target_node.static_curvature:
        evidence.append(
            f"{target} carries historical lift beyond static risk "
            f"({target_node.static_curvature:.3f} -> {target_node.curvature:.3f})"
        )
    if focus_node.failure_count > 0:
        evidence.append(
            f"{focus} has {focus_node.failure_count} recorded failure event(s), making it a symptom seed for backpropagation"
        )
    recent = store._lines.get(target)
    recent_events = recent.events[-3:] if recent and recent.events else []
    action_chain = [
        f"inspect {target} first",
        f"review exported interfaces / dependency assumptions around {target}",
        f"add or update regression tests covering the {focus} -> {target} path",
    ]
    if not target_node.has_exception_handling and target_node.complexity >= 4:
        action_chain.append(f"consider defensive error handling inside {target}")
    return {
        "focus": focus,
        "recommended_target": target,
        "resolution_context": context,
        "reasoning_chain": evidence,
        "recent_target_events": recent_events,
        "action_chain": action_chain,
    }

def _parse_tests_summary(value: str) -> dict[str, int]:
    value = (value or "").strip()
    if not value:
        return {"pass": 0, "fail": 0, "total": 0}
    if "/" in value:
        passed, total = value.split("/", 1)
        p = int(passed)
        t = int(total)
        return {"pass": p, "fail": max(t - p, 0), "total": t}
    p = int(value)
    return {"pass": p, "fail": 0, "total": p}

def _make_task_id() -> str:
    return f"T{uuid.uuid4().hex[:16]}"

def node_feature_vector(node: BehaviorNode, graph: BehaviorGraph) -> list[float]:
    singularities = {s.id for s in find_singularities(graph)}
    return [
        round(node.static_curvature, 3),
        round(min(node.failure_count / 10, 1.0), 3),
        round(min(_downstream_failure_count(graph, node.id) / 5, 1.0), 3),
        1.0 if node.id in singularities else 0.0,
        round(min(node.is_imported_by_count / 5, 1.0), 3),
    ]

def cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb + 1e-9)

def find_similar_past_tasks(symptom: str, graph: BehaviorGraph, task_memory: dict,
                            min_similarity: float = 0.75, top_k: int = 3) -> list[dict]:
    if symptom not in graph.nodes:
        return []
    current_vec = node_feature_vector(graph.nodes[symptom], graph)
    candidates = []
    for task in task_memory.values():
        hist_vec = task.get("symptom_feature_vector")
        if not hist_vec:
            continue
        sim = cosine_sim(current_vec, hist_vec)
        if sim > min_similarity:
            candidates.append({
                "task_id": task["task_id"],
                "similarity": round(sim, 3),
                "symptom": task.get("symptom"),
                "final_target": task.get("final_target"),
                "result": task.get("result"),
                "detail": task.get("detail", ""),
            })
    return sorted(candidates, key=lambda item: item["similarity"], reverse=True)[:top_k]

def build_task_record(graph: BehaviorGraph, store: WorldLineStore, symptom: str,
                      final_target: str, result: str, task_id: Optional[str] = None,
                      tests_before: str = "", tests_after: str = "", detail: str = "") -> dict:
    suggestion = build_repair_suggestion(graph, store, symptom) if symptom in graph.nodes else None
    suggested_target = suggestion["recommended_target"] if suggestion else symptom
    before = _parse_tests_summary(tests_before)
    after = _parse_tests_summary(tests_after)
    focus_node = graph.nodes.get(symptom)
    feature_vector = node_feature_vector(focus_node, graph) if focus_node else []
    return {
        "task_id": task_id or _make_task_id(),
        "ts": datetime.now(timezone.utc).isoformat(),
        "symptom": symptom,
        "wlbs_suggested_target": suggested_target,
        "final_target": final_target,
        "suggestion_was_followed": suggested_target == final_target,
        "result": result,
        "tests_before": before,
        "tests_after": after,
        "test_delta": after["pass"] - before["pass"],
        "detail": detail,
        "symptom_feature_vector": feature_vector,
    }

def build_advisory(graph: BehaviorGraph, store: WorldLineStore, symptom: str,
                   min_confidence: float = 0.0) -> dict:
    start = time.perf_counter()
    suggestion = build_repair_suggestion(graph, store, symptom)
    context = suggestion["resolution_context"]
    target = suggestion["recommended_target"]
    target_node = graph.nodes[target]
    symptom_node = graph.nodes[symptom]
    policy_key = f"{symptom}->{target}"
    policy_conf = float(store.routing_policy.get(policy_key, {}).get("confidence", 0.75))
    similar_tasks = find_similar_past_tasks(symptom, graph, store.task_memory)
    successful_similar = [task for task in similar_tasks if task.get("result") == "pass"]
    similar_bonus = min(0.12, 0.04 * len(successful_similar))
    distance = next(
        (item["distance"] for item in context["tiers"]["near"] if item["id"] == target),
        0,
    )
    base_confidence = min(
        0.98,
        0.35
        + target_node.curvature * 0.35
        + (0.15 if target != symptom else 0.0)
        + (0.10 if any(item["id"] == target and item["is_singularity"] for item in context["tiers"]["near"]) else 0.0)
        + min(_downstream_failure_count(graph, target) / 10, 0.08),
    )
    confidence = round(
        min(0.98, max(0.0, base_confidence * 0.7 + policy_conf * 0.3 + similar_bonus)),
        3,
    )
    primary = {
        "text": f"{target} may be worth investigating first",
        "confidence": confidence,
        "tone": "suggestion",
        "reasoning": [
            *suggestion["reasoning_chain"],
            f"behavioral distance to symptom: {distance} hop(s)",
            f"routing policy confidence for {policy_key}: {policy_conf:.3f}",
            f"successful similar-task bonus: +{similar_bonus:.3f} from {len(successful_similar)} matched task(s)",
        ],
    }
    alternatives = []
    alt_conf = round(min(0.95, 0.25 + symptom_node.curvature * 0.35), 3)
    if symptom != target and alt_conf >= min_confidence:
        alternatives.append({
            "text": f"{symptom} itself may also deserve a direct check",
            "confidence": alt_conf,
            "tone": "note",
            "reasoning": [f"{symptom} has {symptom_node.failure_count} direct failure event(s) recorded"],
        })
    if primary["confidence"] < min_confidence:
        primary = {
            "text": f"no suggestion exceeded confidence threshold {min_confidence:.2f}",
            "confidence": round(primary["confidence"], 3),
            "tone": "note",
            "reasoning": ["wlbs found candidate routes, but confidence was below the requested threshold"],
        }
    elapsed = int((time.perf_counter() - start) * 1000)
    return {
        "schema": "wlbs-advisory-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symptom": symptom,
        "advisory": {
            "primary_suggestion": primary,
            "alternative_suggestions": alternatives,
            "what_to_read_first": list(dict.fromkeys([
                Path(graph.nodes[target].file).name if target in graph.nodes else target,
                Path(graph.nodes[symptom].file).name if symptom in graph.nodes else symptom,
            ])),
            "what_might_be_safe_to_skip": [],
            "open_questions": [
                "Is the failure pattern consistent across repeated test runs?",
                f"Does {target} show recent ownership or churn worth checking with --blame?",
            ],
            "similar_past_tasks": similar_tasks,
        },
        "metadata": {
            "nodes_analyzed": len(graph.nodes),
            "world_line_events": sum(len(wl.events) for wl in store.all_lines()),
            "scan_ms": elapsed,
        },
    }

def print_resolution_context(graph: BehaviorGraph, store: WorldLineStore, focus: str):
    ctx = assemble_resolution_context(graph, store, focus)
    print()
    print(colored("━"*62, CYAN, BOLD))
    print(colored(f"  Resolution-Decay Context  focus={focus}", WHITE, BOLD))
    print(colored("━"*62, CYAN, BOLD))
    print(colored(
        f"  tier_counts={ctx['tier_counts']}  approx_units={ctx['approx_context_units']}",
        GRAY,
    ))
    for tier_name, title in (("near", "L1 near (full fidelity)"),
                             ("mid", "L2 mid (summary)"),
                             ("far", "L3 far (compressed)")):
        items = ctx["tiers"][tier_name]
        if not items:
            continue
        print()
        print(colored(f"  {title}", YELLOW if tier_name == "near" else CYAN, BOLD))
        for item in items[:8]:
            print(
                f"    {colored(item['id'], WHITE)}  d={item['distance']}  "
                f"κ={item['curvature']:.3f}"
                + (colored("  ★", YELLOW) if item.get("is_singularity") else "")
            )
            if tier_name == "near":
                print(colored(
                    f"       fail={item['failures']} fix={item['fixes']} "
                    f"calls={len(item['calls'])} called_by={len(item['called_by'])}",
                    GRAY,
                ))
                for ev in item.get("recent_events", [])[-3:]:
                    detail = ev.get("detail", "")
                    print(colored(f"       - {ev['kind']} {detail[:60]}", GRAY))
            elif tier_name == "mid":
                print(colored(
                    f"       fail={item['failures']} fix={item['fixes']} "
                    f"recent={'yes' if item.get('recent_event') else 'no'}",
                    GRAY,
                ))
    print()
    print(colored("━"*62, CYAN))
    print()

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
    try:
        import pytest  # noqa: F401
        pytest_available = True
    except Exception:
        pytest_available = False
    if not pytest_available:
        return _run_simple_tests_and_record(test_path, project_root, store, file_to_module)
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

def _run_simple_tests_and_record(test_path, project_root, store, file_to_module):
    results = {"passed": 0, "failed": 0, "recorded": []}
    test_path = Path(test_path)
    files = [test_path] if test_path.is_file() else sorted(test_path.rglob("test_*.py"))
    all_modules = list(file_to_module.values())
    sys.path.insert(0, str(project_root))
    try:
        for idx, file in enumerate(files):
            mod_name = f"_wlbs_simple_test_{idx}_{file.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, file)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for name in sorted(dir(module)):
                if not name.startswith("test_"):
                    continue
                fn = getattr(module, name)
                if not callable(fn):
                    continue
                node_id = _find_best_node(file.stem, name, all_modules)
                if node_id in {"unknown", file.stem, file.stem.replace("test_", "", 1)}:
                    node_id = project_root.name
                try:
                    fn()
                    results["passed"] += 1
                    wl = store._lines.get(node_id)
                    if wl and wl.failure_count > 0 and wl.recent_failure_rate > 0:
                        store.record_fix(node_id, f"test passed: {name}")
                        results["recorded"].append(("fix", node_id, name))
                except Exception as exc:
                    detail = f"{name}: {type(exc).__name__}: {exc}"
                    store.record_failure(node_id, detail[:160])
                    results["failed"] += 1
                    results["recorded"].append(("failure", node_id, detail[:160]))
    finally:
        try:
            sys.path.remove(str(project_root))
        except ValueError:
            pass
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
def print_suggestions(graph, store, focus: Optional[str] = None):
    sings = find_singularities(graph)
    sing_ids = {s.id for s in sings}
    if focus and focus in graph.nodes:
        nodes = [graph.nodes[focus]]
    else:
        nodes = sorted(graph.nodes.values(), key=lambda n: n.curvature, reverse=True)[:10]
    print()
    print(colored("━"*55, CYAN, BOLD))
    print(colored("  Actionable Suggestions", WHITE, BOLD))
    print(colored("━"*55, CYAN, BOLD))
    for node in nodes:
        if node.curvature < 0.3: break
        suggestion = build_repair_suggestion(graph, store, node.id)
        print()
        icon = colored("★", YELLOW) if node.id in sing_ids else colored("•", CYAN)
        print(f"  {icon} {colored(node.id, WHITE, BOLD)}  κ={node.curvature:.3f}")
        suggs = []
        target = suggestion["recommended_target"]
        if target != node.id:
            suggs.append(colored(f"  → Route repair effort to upstream target: {target}", YELLOW, BOLD))
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
        if suggestion["reasoning_chain"]:
            print(colored("  Reasoning chain:", WHITE, BOLD))
            for step in suggestion["reasoning_chain"]:
                print(colored(f"    - {step}", GRAY))
        if suggestion["action_chain"]:
            print(colored("  Action plan:", WHITE, BOLD))
            for step in suggestion["action_chain"]:
                print(colored(f"    - {step}", GRAY))
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
  wlbs-scan . --context rbac                   # resolution-decay context around node
  wlbs-scan . --advise rbac --json            # agent-friendly advisory output
  wlbs-scan . --record-outcome --symptom rbac --final-target roles --result pass
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
    p.add_argument("--context",metavar="NODE",
                   help="Show resolution-decay context assembly around a node")
    p.add_argument("--advise",metavar="NODE",
                   help="Show advisory output for a symptom node")
    p.add_argument("--min-confidence",type=float,default=0.0,metavar="P",
                   help="Minimum advisory confidence to surface (default 0.0)")
    p.add_argument("--history",action="store_true")
    p.add_argument("--record-failure",metavar="NODE")
    p.add_argument("--record-fix",metavar="NODE")
    p.add_argument("--detail",metavar="MSG",default="")
    p.add_argument("--record-outcome",action="store_true",
                   help="Record task-level outcome for harness learning")
    p.add_argument("--task-id",metavar="TASK_ID")
    p.add_argument("--symptom",metavar="NODE")
    p.add_argument("--final-target",metavar="NODE")
    p.add_argument("--result",choices=("pass","fail"))
    p.add_argument("--tests-before",metavar="P/T",default="")
    p.add_argument("--tests-after",metavar="P/T",default="")
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
    p.add_argument("--suggest-node",metavar="NODE",
                   help="Focus repair suggestions on a specific node")
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
    # ── cloud commands ──────────────────────────────────────────
    p.add_argument("--register",action="store_true",
                   help="Register a free account (interactive, email verification)")
    p.add_argument("--login",action="store_true",
                   help="Log in to wlbs cloud (interactive)")
    p.add_argument("--whoami",action="store_true",
                   help="Show current cloud account info")
    p.add_argument("--keygen",action="store_true",
                   help="Generate a wlbs API key (requires login)")
    p.add_argument("--set-api-key",metavar="KEY",
                   help="Save a wlbs API key to local config")
    p.add_argument("--api-key",metavar="KEY",
                   help="wlbs API key to use for --sync (overrides saved config and WLBS_API_KEY)")
    p.add_argument("--sync",action="store_true",
                   help="Upload local world-lines and pull community data")
    p.add_argument("--cloud-stats",action="store_true",
                   help="Show wlbs cloud statistics")
    p.add_argument("--status",action="store_true",
                   help="Show current risk status and account info")
    p.add_argument("--dashboard",action="store_true",
                   help="Open interactive risk heatmap in browser (Pro: includes account info)")
    p.add_argument("--hub-url",metavar="URL",
                   default=os.environ.get("WLBS_HUB_URL","http://111.231.112.127:8765"),
                   help="wlbs hub server URL (default: http://111.231.112.127:8765)")
    args=p.parse_args()

    root=Path(args.path).resolve()
    if not root.exists():
        print(f"Error: not found: {root}",file=sys.stderr); sys.exit(1)
    if root.is_file(): root=root.parent

    store=WorldLineStore(root)

    if args.reset:
        store.reset(); print(colored("  Memory cleared.",GREEN)); return

    # ── cloud commands ──────────────────────────────────────────
    if args.register:
        try:
            from wlbs_scan.cloud import interactive_register
            interactive_register()
        except ImportError:
            print(colored("  Error: cloud module not found", RED))
        return

    if args.login:
        try:
            from wlbs_scan.cloud import interactive_login
            interactive_login()
        except ImportError:
            print(colored("  Error: cloud module not found", RED))
        return

    if args.whoami:
        try:
            from wlbs_scan.cloud import cmd_whoami, CloudError
            info = cmd_whoami()
            print(colored(f"  User: {info.get('email','?')}  tier={info.get('tier','?')}  id={info.get('id','?')}", GREEN))
        except Exception as e:
            print(colored(f"  {e}", RED))
        return

    if args.keygen:
        try:
            from wlbs_scan.cloud import cmd_keygen, CloudError, CONFIG_PATH
            result = cmd_keygen(note="cli")
            print(colored(f"  API key: {result.get('key','')}", GREEN))
            print(colored(f"  tier={result.get('tier','free')}  saved to {CONFIG_PATH}", GRAY))
        except Exception as e:
            print(colored(f"  {e}", RED))
        return

    if args.set_api_key:
        try:
            from wlbs_scan.cloud import cmd_set_api_key, CONFIG_PATH
            cmd_set_api_key(args.set_api_key)
            print(colored(f"  API key saved to {CONFIG_PATH}", GREEN))
        except Exception as e:
            print(colored(f"  {e}", RED))
        return

    if args.cloud_stats:
        try:
            from wlbs_scan.cloud import cmd_cloud_stats
            stats = cmd_cloud_stats()
            print(colored(f"  wlbs cloud stats:", CYAN))
            print(colored(f"    snapshots={stats.get('snapshots',0)}  total_nodes={stats.get('total_nodes',0)}  active_keys={stats.get('active_keys',0)}", WHITE))
        except Exception as e:
            print(colored(f"  {e}", RED))
        return

    if args.sync:
        try:
            from wlbs_scan.cloud import cmd_sync, CloudError, get_api_key, cmd_set_api_key
            # --api-key inline takes priority; save it for future use
            if args.api_key:
                cmd_set_api_key(args.api_key)
            if not get_api_key():
                print(colored("  No API key found. Run: wlbs-scan . --keygen  or  --set-api-key KEY", YELLOW))
                return
            print(colored("  Syncing with wlbs cloud...", CYAN))
            result = cmd_sync(root, project_name=root.name)
            up = result.get("upload", {})
            pr = result.get("pull", {})
            print(colored(f"  Upload: snapshot_id={up.get('snapshot_id','?')}  nodes={up.get('node_count',0)}", GREEN))
            pulled = len(pr.get("items", []))
            print(colored(f"  Pull: {pulled} community snapshots merged", GREEN))
        except Exception as e:
            print(colored(f"  Sync error: {e}", RED))
        return

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

    if args.record_outcome:
        if not args.symptom or not args.final_target or not args.result:
            print(colored("  Error: --record-outcome requires --symptom, --final-target, and --result", RED))
            sys.exit(1)
        graph = build_graph(root, lang=args.lang)
        compute_curvature(graph, store=store)
        record = build_task_record(
            graph, store,
            symptom=args.symptom,
            final_target=args.final_target,
            result=args.result,
            task_id=args.task_id,
            tests_before=args.tests_before,
            tests_after=args.tests_after,
            detail=args.detail,
        )
        store.record_outcome(record)
        if args.api_key:
            try:
                from wlbs_scan.cloud import auto_upload_task_outcome
                auto_upload_task_outcome(record, api_key=args.api_key, hub_url=args.hub_url)
            except Exception:
                pass
        if args.json:
            print(json.dumps(record, indent=2, ensure_ascii=False))
        else:
            print(colored(f"  ✓ Outcome recorded: {record['task_id']}", GREEN))
            print(colored(
                f"    {record['symptom']} -> {record['final_target']}  "
                f"{record['result'].upper()}  delta={record['test_delta']:+d}",
                GRAY,
            ))
            print(colored(
                f"    wlbs suggestion: {record['wlbs_suggested_target']}  "
                f"followed={record['suggestion_was_followed']}",
                GRAY,
            ))
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

    if args.dashboard:
        from wlbs_scan.dashboard import launch_dashboard

        def graph_getter():
            graph = build_graph(root, since_days=args.since, lang=args.lang)
            compute_curvature(graph, store=store)
            payload = report_json(graph, store)
            payload["task_memory"] = store.task_memory
            return payload

        def account_getter():
            return query_points(args.api_key or "", args.hub_url) if args.api_key else None

        launch_dashboard(root, graph_getter, account_getter, args.hub_url, args.api_key or "")
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
        if args.context:
            if args.context not in graph.nodes:
                print(colored(f"  Error: unknown node: {args.context}", RED))
                _ci_failed = True
                return
            ctx = assemble_resolution_context(graph, store, args.context)
            if args.json:
                print(json.dumps(ctx, indent=2, ensure_ascii=False))
            else:
                print_resolution_context(graph, store, args.context)
            return
        if args.status:
            print_status(graph, store, api_key=args.api_key or "", hub_url=args.hub_url)
            return
        if args.advise:
            if args.advise not in graph.nodes:
                print(colored(f"  Error: unknown node: {args.advise}", RED))
                _ci_failed = True
                return
            payload = build_advisory(graph, store, args.advise, min_confidence=args.min_confidence)
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print_advisory(payload)
            return
        if args.suggest:
            if args.suggest_node and args.suggest_node not in graph.nodes:
                print(colored(f"  Error: unknown node: {args.suggest_node}", RED))
                _ci_failed = True
                return
            if args.json:
                if args.suggest_node:
                    print(json.dumps(build_repair_suggestion(graph, store, args.suggest_node), indent=2, ensure_ascii=False))
                else:
                    top_nodes = sorted(graph.nodes.values(), key=lambda n: n.curvature, reverse=True)[:5]
                    payload = [build_repair_suggestion(graph, store, node.id) for node in top_nodes if node.curvature >= 0.3]
                    print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print_suggestions(graph, store, focus=args.suggest_node)
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
        if args.api_key and not args.json and not args.ci:
            write_auto_advice(graph, store, root, args.api_key, args.hub_url)
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
