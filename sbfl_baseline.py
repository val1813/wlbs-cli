"""
SBFL Baseline: Ochiai coefficient
Formula: ochiai(n) = failed(n) / sqrt(total_failed * (failed(n) + passed(n)))

Reference: Abreu et al. (2007). On the accuracy of spectrum-based fault localization.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class SBFLNode:
    node_id: str
    file_path: str
    ef: int = 0   # executed by failing tests
    ep: int = 0   # executed by passing tests
    nf: int = 0   # NOT executed by failing tests
    np: int = 0   # NOT executed by passing tests
    ochiai: float = 0.0
    rank: int = 0


class OchiaiSBFL:
    """
    Spectrum-Based Fault Localization using the Ochiai coefficient.
    Input: same coverage format as WLBS build_graph_from_coverage.
    """

    def __init__(self):
        self._nodes: Dict[str, SBFLNode] = {}
        self._total_failed = 0
        self._total_passed = 0

    def load_coverage(self, coverage_file: str):
        coverage = json.loads(Path(coverage_file).read_text(encoding='utf-8'))

        # First pass: count totals and collect per-node ef/ep
        for test_id, info in coverage.items():
            status = info.get('status', 'pass')
            nodes = info.get('nodes', [])
            files = info.get('files', {})

            if status == 'fail':
                self._total_failed += 1
            else:
                self._total_passed += 1

            for nid in nodes:
                fp = files.get(nid, 'unknown')
                if nid not in self._nodes:
                    self._nodes[nid] = SBFLNode(node_id=nid, file_path=fp)
                if status == 'fail':
                    self._nodes[nid].ef += 1
                else:
                    self._nodes[nid].ep += 1

        # Second pass: compute nf, np
        for node in self._nodes.values():
            node.nf = self._total_failed - node.ef
            node.np = self._total_passed - node.ep

    def compute(self):
        """Compute Ochiai scores and rank all nodes."""
        import math
        for node in self._nodes.values():
            denom = math.sqrt(self._total_failed * (node.ef + node.ep))
            node.ochiai = node.ef / denom if denom > 0 else 0.0

        ranked = sorted(self._nodes.values(), key=lambda n: n.ochiai, reverse=True)
        for i, node in enumerate(ranked, 1):
            node.rank = i

    def ranked_nodes(self) -> List[SBFLNode]:
        return sorted(self._nodes.values(), key=lambda n: n.ochiai, reverse=True)

    def top_n_files(self, n: int = 5) -> List[Tuple[str, float]]:
        """File-level ranking by max Ochiai score in that file."""
        file_score: Dict[str, float] = {}
        for node in self._nodes.values():
            fp = node.file_path
            file_score[fp] = max(file_score.get(fp, 0.0), node.ochiai)
        ranked = sorted(file_score.items(), key=lambda x: x[1], reverse=True)
        return ranked[:n]

    def rank_of_file(self, target_file: str) -> int:
        """Return 1-based file rank for target_file, or -1 if not found."""
        ranked = self.top_n_files(n=len(self._nodes))
        for i, (fp, _) in enumerate(ranked, 1):
            if fp == target_file or Path(fp).name == Path(target_file).name:
                return i
        return -1


if __name__ == '__main__':
    # Smoke test with synthetic data
    import tempfile, os
    cov = {
        'test_fail_1': {'status': 'fail', 'nodes': ['A', 'B', 'C'], 'files': {'A': 'Test.java', 'B': 'Proc.java', 'C': 'Valid.java'}},
        'test_fail_2': {'status': 'fail', 'nodes': ['A', 'B'], 'files': {'A': 'Test.java', 'B': 'Proc.java'}},
        'test_pass_1': {'status': 'pass', 'nodes': ['A', 'D'], 'files': {'A': 'Test.java', 'D': 'Other.java'}},
        'test_pass_2': {'status': 'pass', 'nodes': ['D'], 'files': {'D': 'Other.java'}},
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(cov, f)
        tmp = f.name
    sbfl = OchiaiSBFL()
    sbfl.load_coverage(tmp)
    sbfl.compute()
    os.unlink(tmp)
    print("Ochiai ranking:")
    for node in sbfl.ranked_nodes():
        print(f"  {node.node_id:20s}  ochiai={node.ochiai:.4f}  rank={node.rank}")
    print("Top files:", sbfl.top_n_files())
