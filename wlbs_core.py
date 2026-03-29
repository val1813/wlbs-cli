"""
WLBS Core: Weighted Location by Behavior Singularity
Implements curvature propagation and singularity detection as described in
Huang (2026), CN Patent Applications 2026103746505 / 2026103756225.
"""

from __future__ import annotations
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class WorldLineEvent:
    """Single append-only event on a node's world-line."""
    timestamp: float
    event_type: str          # 'test_fail' | 'test_pass' | 'curvature_update'
    source_test: str = ""
    delta_kappa: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class BehaviorNode:
    """A function-level node in the behavior graph."""
    node_id: str             # e.g. "pkg.ClassName#methodName"
    file_path: str           # source file
    kappa: float = 0.0       # curvature accumulator
    direct_failure_count: int = 0
    world_line: List[WorldLineEvent] = field(default_factory=list)
    is_singularity: bool = False
    singularity_rank: Optional[int] = None

    def record_event(self, event: WorldLineEvent):
        self.world_line.append(event)


# ---------------------------------------------------------------------------
# BehaviorGraph
# ---------------------------------------------------------------------------

class BehaviorGraph:
    """
    Maintains the function-level behavior graph, world-lines, and curvatures.

    Nodes  : BehaviorNode
    Edges  : directed dependency edges  parent -> child
             (child DEPENDS ON parent, so failures propagate child -> parent)
    """

    # Curvature propagation constants (from paper Section 3.2)
    ALPHA: float = 0.1    # base increment per failure
    LAMBDA: float = 0.5   # decay coefficient
    GAMMA: float = 0.9    # success damping factor
    KAPPA_THRESHOLD: float = 0.3   # singularity threshold

    def __init__(self):
        self._nodes: Dict[str, BehaviorNode] = {}
        # adjacency: node_id -> set of node_ids it depends on (upstream)
        self._deps: Dict[str, Set[str]] = defaultdict(set)
        # reverse: node_id -> set of node_ids that depend on it (downstream)
        self._rdeps: Dict[str, Set[str]] = defaultdict(set)
        # test -> set of nodes exercised by that test
        self._test_coverage: Dict[str, Set[str]] = defaultdict(set)

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def add_node(self, node_id: str, file_path: str) -> BehaviorNode:
        if node_id not in self._nodes:
            self._nodes[node_id] = BehaviorNode(node_id=node_id, file_path=file_path)
        return self._nodes[node_id]

    def add_edge(self, from_node: str, to_node: str):
        """from_node depends on to_node (to_node is upstream)."""
        self._deps[from_node].add(to_node)
        self._rdeps[to_node].add(from_node)

    def add_test_coverage(self, test_id: str, node_ids: List[str]):
        self._test_coverage[test_id].update(node_ids)

    # ------------------------------------------------------------------
    # Behavioral distance (BFS over dependency edges)
    # ------------------------------------------------------------------

    def behavioral_distance(self, source: str, target: str) -> int:
        """
        Shortest path length from source to target following dependency edges
        (upstream direction). Returns -1 if unreachable.
        """
        if source == target:
            return 0
        visited = {source}
        queue = deque([(source, 0)])
        while queue:
            node, dist = queue.popleft()
            for upstream in self._deps.get(node, set()):
                if upstream == target:
                    return dist + 1
                if upstream not in visited:
                    visited.add(upstream)
                    queue.append((upstream, dist + 1))
        return -1

    # ------------------------------------------------------------------
    # Curvature propagation (Section 3.2)
    # ------------------------------------------------------------------

    def on_test_failure(self, test_id: str, failing_node: str):
        """
        Propagate curvature upstream from failing_node.
        Δκ(n) = α · λ^d(n, failing_node)
        """
        t = time.time()
        # Record direct failure
        if failing_node in self._nodes:
            self._nodes[failing_node].direct_failure_count += 1
            self._nodes[failing_node].record_event(WorldLineEvent(
                timestamp=t, event_type='test_fail',
                source_test=test_id, delta_kappa=0.0
            ))

        # BFS upstream, accumulate curvature
        visited = set()
        queue = deque([(failing_node, 0)])
        while queue:
            node_id, dist = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            if node_id not in self._nodes:
                continue
            delta = self.ALPHA * (self.LAMBDA ** dist)
            self._nodes[node_id].kappa += delta
            self._nodes[node_id].record_event(WorldLineEvent(
                timestamp=t, event_type='curvature_update',
                source_test=test_id, delta_kappa=delta
            ))
            for upstream in self._deps.get(node_id, set()):
                if upstream not in visited:
                    queue.append((upstream, dist + 1))

    def on_test_success(self, test_id: str, covered_nodes: Optional[List[str]] = None):
        """
        Damp curvature for all covered nodes on test pass.
        κ(n) ← κ(n) · γ
        """
        t = time.time()
        nodes = covered_nodes or list(self._test_coverage.get(test_id, []))
        for node_id in nodes:
            if node_id in self._nodes:
                self._nodes[node_id].kappa *= self.GAMMA
                self._nodes[node_id].record_event(WorldLineEvent(
                    timestamp=t, event_type='test_pass',
                    source_test=test_id, delta_kappa=0.0
                ))

    # ------------------------------------------------------------------
    # Singularity detection (Definition 4 from paper)
    # ------------------------------------------------------------------

    def detect_singularities(self) -> List[BehaviorNode]:
        """
        A node n is a SINGULARITY iff ALL three conditions hold:
          (a) κ(n) >= KAPPA_THRESHOLD
          (b) n lies on at least one path from a failing node to the graph root
          (c) n has no direct test failure record (cross-file condition)

        Returns ranked list (highest curvature first).
        """
        # Find all nodes with direct failures
        direct_fail_nodes: Set[str] = {
            nid for nid, nd in self._nodes.items()
            if nd.direct_failure_count > 0
        }

        # Find nodes reachable upstream from any failing node
        upstream_of_failure: Set[str] = set()
        for fn in direct_fail_nodes:
            visited: Set[str] = set()
            queue = deque([fn])
            while queue:
                cur = queue.popleft()
                if cur in visited:
                    continue
                visited.add(cur)
                upstream_of_failure.add(cur)
                for up in self._deps.get(cur, set()):
                    queue.append(up)

        singularities = []
        for nid, node in self._nodes.items():
            cond_a = node.kappa >= self.KAPPA_THRESHOLD
            cond_b = nid in upstream_of_failure
            cond_c = node.direct_failure_count == 0
            node.is_singularity = cond_a and cond_b and cond_c
            if node.is_singularity:
                singularities.append(node)

        # Rank by curvature descending
        singularities.sort(key=lambda n: n.kappa, reverse=True)
        for rank, node in enumerate(singularities, 1):
            node.singularity_rank = rank

        return singularities

    # ------------------------------------------------------------------
    # Ranking: all nodes sorted by curvature (for Top-N evaluation)
    # ------------------------------------------------------------------

    def ranked_nodes(self) -> List[BehaviorNode]:
        """All nodes sorted by kappa descending."""
        return sorted(self._nodes.values(), key=lambda n: n.kappa, reverse=True)

    def top_n_files(self, n: int = 5) -> List[Tuple[str, float]]:
        """Deduplicated file-level ranking by max node kappa in that file."""
        file_kappa: Dict[str, float] = {}
        for node in self._nodes.values():
            fp = node.file_path
            file_kappa[fp] = max(file_kappa.get(fp, 0.0), node.kappa)
        ranked = sorted(file_kappa.items(), key=lambda x: x[1], reverse=True)
        return ranked[:n]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            'nodes': {
                nid: {
                    'file_path': nd.file_path,
                    'kappa': nd.kappa,
                    'direct_failure_count': nd.direct_failure_count,
                    'is_singularity': nd.is_singularity,
                    'singularity_rank': nd.singularity_rank,
                    'world_line_len': len(nd.world_line),
                }
                for nid, nd in self._nodes.items()
            },
            'edges': {
                nid: list(ups) for nid, ups in self._deps.items()
            },
        }

    def save(self, path: str):
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding='utf-8')

    @classmethod
    def load(cls, path: str) -> 'BehaviorGraph':
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        g = cls()
        for nid, nd in data['nodes'].items():
            node = g.add_node(nid, nd['file_path'])
            node.kappa = nd['kappa']
            node.direct_failure_count = nd['direct_failure_count']
            node.is_singularity = nd['is_singularity']
            node.singularity_rank = nd['singularity_rank']
        for from_node, upstreams in data['edges'].items():
            for to_node in upstreams:
                g.add_edge(from_node, to_node)
        return g


# ---------------------------------------------------------------------------
# Resolution-Decay Context Assembly (Section 3.3)
# ---------------------------------------------------------------------------

class ResolutionLayer:
    """
    Three-tier foveal context assembly by behavioral distance.
    Tier 1 (d<=1): full fidelity  — last 20 world-line events
    Tier 2 (d<=3): medium fidelity — last 5 world-line events
    Tier 3 (d> 3): structural only — kappa value only
    """

    TIER1_EVENTS = 20
    TIER2_EVENTS = 5

    def assemble(self, graph: BehaviorGraph, focal_node: str) -> dict:
        context = {'focal': focal_node, 'tiers': {}}
        for nid, node in graph._nodes.items():
            d = graph.behavioral_distance(focal_node, nid)
            if d == -1:
                d = graph.behavioral_distance(nid, focal_node)
            if d == -1:
                d = 999

            if d <= 1:
                tier = 1
                events = [vars(e) for e in node.world_line[-self.TIER1_EVENTS:]]
            elif d <= 3:
                tier = 2
                events = [vars(e) for e in node.world_line[-self.TIER2_EVENTS:]]
            else:
                tier = 3
                events = []

            context['tiers'][nid] = {
                'tier': tier,
                'distance': d,
                'kappa': node.kappa,
                'is_singularity': node.is_singularity,
                'events': events,
            }
        return context


# ---------------------------------------------------------------------------
# Convenience: build graph from Defects4J coverage data
# ---------------------------------------------------------------------------

def build_graph_from_coverage(
    coverage_file: str,
    call_graph_file: Optional[str] = None,
) -> BehaviorGraph:
    """
    Build a BehaviorGraph from:
      coverage_file  : JSON {test_id: {status: pass|fail, nodes: [node_id, ...], files: {node_id: file_path}}}
      call_graph_file: JSON {node_id: [dependency_node_ids]} (optional static call graph)
    """
    g = BehaviorGraph()
    t0 = time.time()

    coverage = json.loads(Path(coverage_file).read_text(encoding='utf-8'))

    # Add nodes and record test outcomes
    for test_id, info in coverage.items():
        nodes = info.get('nodes', [])
        files = info.get('files', {})
        status = info.get('status', 'pass')

        for nid in nodes:
            fp = files.get(nid, 'unknown')
            g.add_node(nid, fp)
            g.add_test_coverage(test_id, [nid])

        if status == 'fail':
            # failing node = first node in list (the test class itself)
            if nodes:
                g.on_test_failure(test_id, nodes[0])
        else:
            g.on_test_success(test_id, nodes)

    # Add static call graph edges if provided
    if call_graph_file and Path(call_graph_file).exists():
        cg = json.loads(Path(call_graph_file).read_text(encoding='utf-8'))
        for from_node, deps in cg.items():
            for to_node in deps:
                if from_node in g._nodes and to_node in g._nodes:
                    g.add_edge(from_node, to_node)

    elapsed = (time.time() - t0) * 1000
    print(f"[WLBS] Graph built in {elapsed:.1f} ms — "
          f"{len(g._nodes)} nodes, "
          f"{sum(len(v) for v in g._deps.values())} edges")
    return g


if __name__ == '__main__':
    # Quick smoke test
    g = BehaviorGraph()
    g.add_node('test.MyTest#testFoo', 'test/MyTest.java')
    g.add_node('src.Processor#process', 'src/Processor.java')
    g.add_node('src.Validator#validate', 'src/Validator.java')
    g.add_edge('test.MyTest#testFoo', 'src.Processor#process')
    g.add_edge('src.Processor#process', 'src.Validator#validate')

    # Simulate 3 failures
    for i in range(3):
        g.on_test_failure(f'test_{i}', 'test.MyTest#testFoo')
    # One pass on processor
    g.on_test_success('test_pass_1', ['src.Processor#process'])

    sings = g.detect_singularities()
    print("Singularities:", [(s.node_id, round(s.kappa, 4)) for s in sings])
    print("Ranked nodes:", [(n.node_id, round(n.kappa, 4)) for n in g.ranked_nodes()])
    print("Top files:", g.top_n_files())

