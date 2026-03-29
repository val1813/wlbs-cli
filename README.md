# WLBS: Weighted Location by Behavior Singularity

**依赖图曲率传播：一种跨文件软件故障根因定位方法**

CN Patent Applications 2026103746505 / 2026103756225 (filed 2026-03-25)

---

## 核心思想

SBFL（谱分析故障定位）只能根据直接执行频率对方法打分，当 buggy file 没有被 failing test 直接覆盖时（cross-file bug），SBFL 得分为 0，无法定位。

WLBS 通过静态调用图，将失败信号从 failing node 向上游传播：

```
Δκ(n) = α · λ^d(n, failing_node)
```

上游节点即使没有被直接覆盖，也会积累 kappa 值，从而被识别为候选根因。

---

## 环境要求

- Windows 11 + WSL Ubuntu 22.04
- OpenJDK 11（WSL内）：`/usr/lib/jvm/java-11-openjdk-amd64`
- Defects4J v2.0（WSL内）：`/opt/defects4j`
- Python 3.12（Windows端）

## 安装

```bash
pip install -r requirements.txt
```

---

## 快速验证

### 1. 合成 cross-file 案例（无需 Defects4J）

```bash
python synthetic_case.py
```

输出示例：
```
SBFL rank for root cause: NOT FOUND (score=0.000)
WLBS rank for root cause: 4 (kappa=0.0375, propagated 3 hops)
```

### 2. 端到端测试（需要 Defects4J + WSL）

```bash
python experiment_runner.py test
```

### 3. 完整实验

```bash
# 实验1：WLBS vs Ochiai，30个bug
python experiment_runner.py exp1

# 查看结果
python -c "import json; r=json.load(open('results/exp1_results.json')); print(r['summary'])"
```

---

## 核心参数

| 参数 | 值 | 含义 |
|------|-----|------|
| α (ALPHA) | 0.1 | 每次失败的基础曲率增量 |
| λ (LAMBDA) | 0.5 | 衰减系数（每跳乘以0.5）|
| γ (GAMMA) | 0.9 | 通过测试的阻尼系数 |
| θ (KAPPA_THRESHOLD) | 0.3 | Singularity判断阈值 |
| MAX_CLASSES | 300 | 调用图最大分析class数 |

---

## 算法

```
Singularity 条件（三者同时满足）:
  (a) κ(n) >= θ
  (b) n 在某条从 failing node 到图根的路径上
  (c) δ_f(n) = 0（无直接失败记录）
```

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `wlbs_core.py` | BehaviorGraph、curvature传播、singularity检测 |
| `sbfl_baseline.py` | Ochiai SBFL baseline |
| `callgraph_extractor.py` | javap 静态调用图提取 |
| `defects4j_bridge.py` | Defects4J WSL桥接、覆盖收集 |
| `experiment_runner.py` | 实验1/2/3 runner |
| `synthetic_case.py` | 合成 cross-file 案例演示 |
| `paper/main.tex` | 论文 LaTeX 源码 |

---

## 实验结果（30 bugs: Lang×15 + Math×15）

见 `results/exp1_results.json` 和 `results/summary.md`

---

## 引用

```bibtex
@misc{huang2026wlbs,
  title={依赖图曲率传播：一种跨文件软件故障根因定位方法},
  author={Huang, Zhongchang},
  note={CN Patent 2026103746505, 2026103756225},
  year={2026}
}
```
