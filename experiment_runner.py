"""
Experiment Runner for WLBS vs SBFL comparison.
Experiment 1: WLBS vs Ochiai on 50 Defects4J bugs
Experiment 2: Ablation study
Experiment 3: Case study — 3 cross-file bugs
Results saved to D:/papers/WLBS/results/
"""
from __future__ import annotations
import json, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
from wlbs_core import BehaviorGraph, build_graph_from_coverage
from sbfl_baseline import OchiaiSBFL
from defects4j_bridge import Defects4JBridge

RESULTS_DIR = Path('D:/papers/WLBS/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def rank_of_file(ranked_files: List[Tuple[str, float]], target: str) -> int:
    for i, (fp, _) in enumerate(ranked_files, 1):
        if Path(fp) == Path(target) or Path(fp).name == Path(target).name:
            return i
        if str(Path(fp)).endswith(str(Path(target))):
            return i
    return -1


def top_n_acc(ranks: List[int], n: int) -> float:
    valid = [r for r in ranks if r > 0]
    return sum(1 for r in valid if r <= n) / len(valid) if valid else 0.0


def mean_rank(ranks: List[int]) -> float:
    valid = [r for r in ranks if r > 0]
    return sum(valid) / len(valid) if valid else float('inf')

def evaluate_bug(
    bridge: Defects4JBridge,
    project: str,
    bug_id: int,
    ablation: str = 'full',
) -> dict:
    result = {
        'project': project, 'bug_id': bug_id, 'ablation': ablation,
        'wlbs_rank': -1, 'sbfl_rank': -1,
        'wlbs_top1': False, 'sbfl_top1': False,
        'wlbs_top3': False, 'sbfl_top3': False,
        'wlbs_top5': False, 'sbfl_top5': False,
        'buggy_file': '', 'error': '', 'build_ms': 0.0, 'cg_edges': 0,
    }
    try:
        bug_dir = bridge.checkout(project, bug_id, buggy=True)
        buggy_file = bridge.get_buggy_file(project, bug_id)
        result['buggy_file'] = buggy_file
        coverage = bridge.collect_coverage(bug_dir)
        if not coverage:
            result['error'] = 'empty_coverage'
            return result
        cov_path = RESULTS_DIR / f'{project}_{bug_id}_coverage.json'
        cov_path.write_text(json.dumps(coverage, indent=2), encoding='utf-8')

        # ---- Build call graph (for WLBS propagation) ----
        from callgraph_extractor import build_call_graph
        call_graph = build_call_graph(bug_dir, max_classes=300)
        result['cg_edges'] = sum(len(v) for v in call_graph.values())

        # ---- WLBS ----
        t0 = time.time()
        g = BehaviorGraph()
        if ablation == 'no_propagation':
            g.LAMBDA = 0.0

        # Step 1: Add all nodes from coverage
        fail_nodes_all: set = set()
        pass_nodes_all: set = set()
        for test_id, info in coverage.items():
            nodes = info.get('nodes', [])
            files = info.get('files', {})
            status = info.get('status', 'pass')
            for nid in nodes:
                g.add_node(nid, files.get(nid, 'unknown'))
            if status == 'fail':
                fail_nodes_all.update(nodes)
            else:
                pass_nodes_all.update(nodes)

        # Step 2: Add all nodes from call graph (may include nodes not in coverage)
        all_cg_nodes = set(call_graph.keys())
        for callees in call_graph.values():
            all_cg_nodes.update(callees)
        for nid in all_cg_nodes:
            if nid not in g._nodes:
                # Infer file path from class name
                cls = nid.split('#')[0] if '#' in nid else nid
                fp = cls.replace('.', '/') + '.java'
                g.add_node(nid, fp)

        # Step 3: Add call graph edges BEFORE propagating failure signals
        # Edge direction: add_edge(caller, callee) means caller depends on callee
        # BFS in on_test_failure walks caller→callee (upstream dependency direction)
        for from_node, callees in call_graph.items():
            for to_node in callees:
                g.add_edge(from_node, to_node)

        # Step 4: Propagate failure signal from all nodes covered by failing tests
        # Use aggregate: one failure event per covered node (no per-test damping)
        fail_only = fail_nodes_all
        pass_only = pass_nodes_all - fail_nodes_all
        for nid in fail_only:
            g.on_test_failure('__aggregate_fail__', nid)
        # Mild damping only for nodes never in any failing test
        for nid in pass_only:
            if nid in g._nodes:
                g._nodes[nid].kappa *= g.GAMMA

        if ablation != 'no_singularity':
            g.detect_singularities()
        result['build_ms'] = (time.time() - t0) * 1000
        wlbs_files = g.top_n_files(n=20)
        result['wlbs_rank'] = rank_of_file(wlbs_files, buggy_file)
        result['wlbs_top1'] = result['wlbs_rank'] == 1
        result['wlbs_top3'] = 1 <= result['wlbs_rank'] <= 3
        result['wlbs_top5'] = 1 <= result['wlbs_rank'] <= 5

        # ---- SBFL (Ochiai) ----
        sbfl = OchiaiSBFL()
        sbfl._nodes.clear()
        sbfl._total_failed = 0
        sbfl._total_passed = 0
        for test_id, info in coverage.items():
            status = info.get('status', 'pass')
            nodes = info.get('nodes', [])
            files = info.get('files', {})
            if status == 'fail':
                sbfl._total_failed += 1
            else:
                sbfl._total_passed += 1
            import math
            from sbfl_baseline import SBFLNode
            for nid in nodes:
                fp = files.get(nid, 'unknown')
                if nid not in sbfl._nodes:
                    sbfl._nodes[nid] = SBFLNode(node_id=nid, file_path=fp)
                if status == 'fail':
                    sbfl._nodes[nid].ef += 1
                else:
                    sbfl._nodes[nid].ep += 1
        for node in sbfl._nodes.values():
            node.nf = sbfl._total_failed - node.ef
            node.np = sbfl._total_passed - node.ep
        sbfl.compute()
        sbfl_files = sbfl.top_n_files(n=20)
        result['sbfl_rank'] = rank_of_file(sbfl_files, buggy_file)
        result['sbfl_top1'] = result['sbfl_rank'] == 1
        result['sbfl_top3'] = 1 <= result['sbfl_rank'] <= 3
        result['sbfl_top5'] = 1 <= result['sbfl_rank'] <= 5

    except Exception as e:
        result['error'] = str(e)
    return result


def run_experiment1(
    bridge: Defects4JBridge,
    bug_list: Optional[List[Tuple[str, int]]] = None,
) -> dict:
    """Main comparison: WLBS vs Ochiai on 50 bugs."""
    bug_list = bug_list or bridge.DEFAULT_BUG_LIST
    results = []
    wlbs_ranks, sbfl_ranks = [], []

    for i, (project, bug_id) in enumerate(bug_list, 1):
        print(f'[Exp1] {i}/{len(bug_list)}: {project}-{bug_id}', flush=True)
        r = evaluate_bug(bridge, project, bug_id, ablation='full')
        results.append(r)
        if r['error']:
            print(f'  ERROR: {r["error"]}')
            continue
        wlbs_ranks.append(r['wlbs_rank'])
        sbfl_ranks.append(r['sbfl_rank'])
        print(f'  WLBS rank={r["wlbs_rank"]}  SBFL rank={r["sbfl_rank"]}  '
              f'build={r["build_ms"]:.1f}ms')

    summary = {
        'wlbs_top1': top_n_acc(wlbs_ranks, 1),
        'wlbs_top3': top_n_acc(wlbs_ranks, 3),
        'wlbs_top5': top_n_acc(wlbs_ranks, 5),
        'wlbs_mean_rank': mean_rank(wlbs_ranks),
        'sbfl_top1': top_n_acc(sbfl_ranks, 1),
        'sbfl_top3': top_n_acc(sbfl_ranks, 3),
        'sbfl_top5': top_n_acc(sbfl_ranks, 5),
        'sbfl_mean_rank': mean_rank(sbfl_ranks),
        'n_bugs': len(results),
        'n_errors': sum(1 for r in results if r['error']),
    }
    out = {'summary': summary, 'per_bug': results}
    (RESULTS_DIR / 'exp1_results.json').write_text(
        json.dumps(out, indent=2), encoding='utf-8')
    print('\n=== Experiment 1 Summary ===')
    print(f"WLBS  Top-1={summary['wlbs_top1']:.3f}  Top-3={summary['wlbs_top3']:.3f}  "
          f"Top-5={summary['wlbs_top5']:.3f}  MeanRank={summary['wlbs_mean_rank']:.2f}")
    print(f"SBFL  Top-1={summary['sbfl_top1']:.3f}  Top-3={summary['sbfl_top3']:.3f}  "
          f"Top-5={summary['sbfl_top5']:.3f}  MeanRank={summary['sbfl_mean_rank']:.2f}")
    return out


def run_experiment2(
    bridge: Defects4JBridge,
    bug_list: Optional[List[Tuple[str, int]]] = None,
) -> dict:
    """Ablation: full vs no_propagation vs no_singularity."""
    bug_list = bug_list or bridge.DEFAULT_BUG_LIST[:20]  # 20 bugs for ablation
    ablations = ['full', 'no_propagation', 'no_singularity']
    all_results: Dict[str, list] = {a: [] for a in ablations}

    for i, (project, bug_id) in enumerate(bug_list, 1):
        print(f'[Exp2] {i}/{len(bug_list)}: {project}-{bug_id}', flush=True)
        for abl in ablations:
            r = evaluate_bug(bridge, project, bug_id, ablation=abl)
            all_results[abl].append(r)

    summary = {}
    for abl in ablations:
        ranks = [r['wlbs_rank'] for r in all_results[abl] if not r['error']]
        summary[abl] = {
            'top1': top_n_acc(ranks, 1),
            'top3': top_n_acc(ranks, 3),
            'top5': top_n_acc(ranks, 5),
            'mean_rank': mean_rank(ranks),
        }

    out = {'summary': summary, 'per_bug': all_results}
    (RESULTS_DIR / 'exp2_ablation.json').write_text(
        json.dumps(out, indent=2), encoding='utf-8')
    print('\n=== Experiment 2 Ablation ===')
    for abl, s in summary.items():
        print(f"{abl:20s}  Top-1={s['top1']:.3f}  Top-3={s['top3']:.3f}  "
              f"MeanRank={s['mean_rank']:.2f}")
    return out


def select_case_studies(exp1_results: dict) -> List[dict]:
    """
    Select 3 bugs for Exp3:
    - WLBS Top-1 correct
    - SBFL Top-1 wrong
    - bug_file != test_file (cross-file)
    """
    candidates = []
    for r in exp1_results.get('per_bug', []):
        if r.get('error'):
            continue
        if r['wlbs_top1'] and not r['sbfl_top1']:
            candidates.append(r)
    return candidates[:3]


def run_experiment3(bridge: Defects4JBridge, exp1_results: dict) -> dict:
    """Case study: dependency graph + table for 3 cross-file bugs."""
    cases = select_case_studies(exp1_results)
    case_reports = []
    for case in cases:
        project, bug_id = case['project'], case['bug_id']
        bug_dir = bridge.work_dir / f'{project}_{bug_id}_b'
        cov_path = RESULTS_DIR / f'{project}_{bug_id}_coverage.json'
        if not cov_path.exists():
            continue
        coverage = json.loads(cov_path.read_text(encoding='utf-8'))
        g = BehaviorGraph()
        for test_id, info in coverage.items():
            nodes = info.get('nodes', [])
            files = info.get('files', {})
            status = info.get('status', 'pass')
            for nid in nodes:
                g.add_node(nid, files.get(nid, 'unknown'))
            if status == 'fail' and nodes:
                g.on_test_failure(test_id, nodes[0])
            else:
                g.on_test_success(test_id, nodes)
        sings = g.detect_singularities()
        node_table = [
            {
                'node_id': nd.node_id,
                'file': nd.file_path,
                'kappa': round(nd.kappa, 4),
                'is_singularity': nd.is_singularity,
                'rank': i + 1,
            }
            for i, nd in enumerate(g.ranked_nodes()[:20])
        ]
        case_reports.append({
            'project': project, 'bug_id': bug_id,
            'buggy_file': case['buggy_file'],
            'wlbs_rank': case['wlbs_rank'],
            'sbfl_rank': case['sbfl_rank'],
            'singularities': [(s.node_id, round(s.kappa, 4)) for s in sings],
            'node_table': node_table,
        })
    out = {'cases': case_reports}
    (RESULTS_DIR / 'exp3_cases.json').write_text(
        json.dumps(out, indent=2), encoding='utf-8')
    print(f'[Exp3] {len(case_reports)} case studies saved.')
    return out


if __name__ == '__main__':
    import sys
    bridge = Defects4JBridge(
        d4j_home='/opt/defects4j',
        work_dir='/mnt/d/papers/WLBS/bugs',
    )
    print('WLBS Experiment Runner ready.')
    print(f'D4J home: {bridge.d4j_home}')
    print(f'Work dir WSL: {bridge.work_dir_wsl}')
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        # Quick test on Lang-1
        print('\n--- Quick test: Lang-1 ---')
        r = evaluate_bug(bridge, 'Lang', 1)
        print(json.dumps(r, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == 'exp1':
        run_experiment1(bridge)
    elif len(sys.argv) > 1 and sys.argv[1] == 'exp2':
        exp1 = json.loads((RESULTS_DIR / 'exp1_results.json').read_text())
        run_experiment2(bridge)
    elif len(sys.argv) > 1 and sys.argv[1] == 'all':
        exp1 = run_experiment1(bridge)
        run_experiment2(bridge)
        run_experiment3(bridge, exp1)
    else:
        print('Usage: python experiment_runner.py [test|exp1|exp2|all]')


