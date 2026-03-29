"""
合成 cross-file 案例研究
展示 WLBS 在 SBFL 完全失败时的优势

场景:
  TestClass -> ServiceFacade -> DataProcessor -> BuggyHelper

  failing test 直接覆盖 TestClass + ServiceFacade
  BuggyHelper 没有被任何测试直接覆盖

  SBFL: BuggyHelper.ochiai = 0.0 (rank = 最末)
  WLBS: BuggyHelper.kappa = 0.1*0.5^2 = 0.025 (rank = Top-1 via singularity)
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'D:/papers/WLBS/code')
from wlbs_core import BehaviorGraph
from sbfl_baseline import OchiaiSBFL, SBFLNode


def run_synthetic_case():
    # ---------- 构建场景 ----------
    # 4个文件，3跳依赖链
    # test -> facade -> processor -> buggy_helper

    nodes = {
        'com.example.TestClass#testMethod':       'test/TestClass.java',
        'com.example.ServiceFacade#process':       'src/ServiceFacade.java',
        'com.example.DataProcessor#compute':       'src/DataProcessor.java',
        'com.example.BuggyHelper#validate':        'src/BuggyHelper.java',  # root cause
        'com.example.OtherUtil#helper':            'src/OtherUtil.java',
        'com.example.AnotherClass#method':         'src/AnotherClass.java',
    }

    # Coverage: 2 failing tests, 5 passing tests
    # Failing tests cover TestClass + ServiceFacade ONLY
    # BuggyHelper is NEVER directly covered by any test
    coverage = {
        'test_fail_1': {
            'status': 'fail',
            'nodes': ['com.example.TestClass#testMethod', 'com.example.ServiceFacade#process'],
            'files': {
                'com.example.TestClass#testMethod': 'test/TestClass.java',
                'com.example.ServiceFacade#process': 'src/ServiceFacade.java',
            }
        },
        'test_fail_2': {
            'status': 'fail',
            'nodes': ['com.example.TestClass#testMethod'],
            'files': {'com.example.TestClass#testMethod': 'test/TestClass.java'}
        },
        'test_pass_1': {
            'status': 'pass',
            'nodes': ['com.example.OtherUtil#helper', 'com.example.AnotherClass#method'],
            'files': {
                'com.example.OtherUtil#helper': 'src/OtherUtil.java',
                'com.example.AnotherClass#method': 'src/AnotherClass.java',
            }
        },
        'test_pass_2': {'status': 'pass', 'nodes': ['com.example.OtherUtil#helper'],
                        'files': {'com.example.OtherUtil#helper': 'src/OtherUtil.java'}},
        'test_pass_3': {'status': 'pass', 'nodes': ['com.example.AnotherClass#method'],
                        'files': {'com.example.AnotherClass#method': 'src/AnotherClass.java'}},
    }

    # Call graph edges (caller depends on callee)
    call_graph = {
        'com.example.TestClass#testMethod':  ['com.example.ServiceFacade#process'],
        'com.example.ServiceFacade#process': ['com.example.DataProcessor#compute'],
        'com.example.DataProcessor#compute': ['com.example.BuggyHelper#validate'],
        'com.example.OtherUtil#helper':      ['com.example.AnotherClass#method'],
    }

    # ---------- SBFL (Ochiai) ----------
    sbfl = OchiaiSBFL()
    for test_id, info in coverage.items():
        status = info['status']
        test_nodes = info['nodes']
        files = info['files']
        if status == 'fail': sbfl._total_failed += 1
        else: sbfl._total_passed += 1
        for nid in test_nodes:
            if nid not in sbfl._nodes:
                sbfl._nodes[nid] = SBFLNode(node_id=nid, file_path=files.get(nid, ''))
            if status == 'fail': sbfl._nodes[nid].ef += 1
            else: sbfl._nodes[nid].ep += 1
    for nd in sbfl._nodes.values():
        nd.nf = sbfl._total_failed - nd.ef
        nd.np = sbfl._total_passed - nd.ep
    sbfl.compute()

    # ---------- WLBS ----------
    g = BehaviorGraph()
    # Add all nodes
    for nid, fp in nodes.items():
        g.add_node(nid, fp)
    # Add call graph edges FIRST
    for caller, callees in call_graph.items():
        for callee in callees:
            g.add_edge(caller, callee)
    # Propagate failure signal
    fail_nodes = set()
    pass_nodes = set()
    for info in coverage.values():
        if info['status'] == 'fail':
            fail_nodes.update(info['nodes'])
        else:
            pass_nodes.update(info['nodes'])
    for nid in fail_nodes:
        g.on_test_failure('fail', nid)
    for nid in (pass_nodes - fail_nodes):
        if nid in g._nodes:
            g._nodes[nid].kappa *= g.GAMMA
    sings = g.detect_singularities()

    # ---------- Print results ----------
    print('=' * 60)
    print('SYNTHETIC CROSS-FILE CASE STUDY')
    print('=' * 60)
    print('Scenario:')
    print('  TestClass -> ServiceFacade -> DataProcessor -> BuggyHelper')
    print('  Failing tests cover: TestClass, ServiceFacade')
    print('  BuggyHelper: NEVER directly covered by any test')
    print()

    print('--- SBFL (Ochiai) File Ranking ---')
    sbfl_files = sbfl.top_n_files(n=10)
    buggy_in_sbfl = False
    for i, (fp, score) in enumerate(sbfl_files, 1):
        marker = ' <-- ROOT CAUSE' if 'BuggyHelper' in fp else ''
        print(f'  #{i}  {fp}  ochiai={score:.4f}{marker}')
    # BuggyHelper not in list = rank infinity
    all_sbfl_files = [fp for fp, _ in sbfl.top_n_files(n=100)]
    sbfl_rank = next((i+1 for i, fp in enumerate(all_sbfl_files) if 'BuggyHelper' in fp), 'NOT FOUND')
    print(f'  BuggyHelper rank in SBFL: {sbfl_rank}')
    print()

    print('--- WLBS Curvature Ranking ---')
    wlbs_files = g.top_n_files(n=10)
    for i, (fp, kappa) in enumerate(wlbs_files, 1):
        marker = ' <-- ROOT CAUSE' if 'BuggyHelper' in fp else ''
        print(f'  #{i}  {fp}  kappa={kappa:.4f}{marker}')
    wlbs_rank = next((i+1 for i, (fp, _) in enumerate(wlbs_files) if 'BuggyHelper' in fp), 'NOT FOUND')
    print(f'  BuggyHelper rank in WLBS: {wlbs_rank}')
    print()

    print('--- Propagation Path ---')
    path_nodes = [
        'com.example.TestClass#testMethod',
        'com.example.ServiceFacade#process',
        'com.example.DataProcessor#compute',
        'com.example.BuggyHelper#validate',
    ]
    for i, nid in enumerate(path_nodes):
        nd = g._nodes.get(nid)
        kappa = nd.kappa if nd else 0
        theoretical = 0.1 * (0.5 ** i) * 2  # 2 failing tests
        sing = ' [SINGULARITY]' if (nd and nd.is_singularity) else ''
        print(f'  hop {i}: {nid.split(".")[-1]}  kappa={kappa:.4f}  theoretical={theoretical:.4f}{sing}')
    print()
    print('--- Conclusion ---')
    print(f'  SBFL rank for root cause: {sbfl_rank} (score=0.000, never covered)')
    print(f'  WLBS rank for root cause: {wlbs_rank} (kappa>0, propagated from {len(fail_nodes)} failing nodes)')
    print(f'  Singularities detected: {[(s.node_id.split(".")[-1], round(s.kappa,4)) for s in sings]}')

    return {
        'sbfl_rank': sbfl_rank,
        'wlbs_rank': wlbs_rank,
        'propagation': [
            {'hop': i, 'node': nid.split('.')[-1],
             'kappa': g._nodes[nid].kappa if nid in g._nodes else 0}
            for i, nid in enumerate(path_nodes)
        ],
        'singularities': [(s.node_id, round(s.kappa, 4)) for s in sings],
    }


if __name__ == '__main__':
    result = run_synthetic_case()
