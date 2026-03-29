# WLBS 实验结果汇总

## 主实验（30 bugs: Lang×15 + Math×15）

| 指标 | 数值 |
|------|------|
| 总 bug 数 | 30（Lang×15，Math×15）|
| WLBS Top-1 准确率 | 30/30 (100.0%) |
| SBFL Top-1 准确率 | 30/30 (100.0%) |
| 平均 build time | 9.2 ms |
| 最小 build time | 1.0 ms (Lang-57) |
| 最大 build time | 24.2 ms (Math-5) |
| 标准差 | 5.9 ms |
| 平均调用图边数 | 1900 条 |
| 最小调用图边数 | 929 条 (Lang-57) |
| 最大调用图边数 | 5744 条 (Lang-39) |
| 平均调用图节点数（callers） | 732 个 |

## 分项目统计

| 项目 | Bug数 | WLBS Top-1 | SBFL Top-1 | 平均build(ms) | 平均边数 |
|------|-------|-----------|-----------|--------------|----------|
| Lang | 15 | 15/15 | 15/15 | 8.1 | 2167 |
| Math | 15 | 15/15 | 15/15 | 10.4 | 1633 |

## kappa 传播验证（Lang-1）

```
参数：α=0.1，λ=0.5，γ=0.9，θ=0.3

Failing node：
  org.apache.commons.lang3.math.NumberUtils#createNumber
  kappa = 0.10（直接失败节点）

传播验证：
  StringUtils#isEmpty（2跳上游）kappa = 0.125
  NumberUtils 多个方法 kappa = 0.10–0.20

传播确认：边先加入图再传播信号，BFS沿调用链向下游传播
```

## 两方法结果相同的说明

Cobertura 提供聚合覆盖（所有测试的并集），buggy file 在覆盖集中，
SBFL 和 WLBS 输入等价，结果相同。这是覆盖工具的局限，不是算法缺陷。

**per-test 覆盖下 WLBS 优势：见 synthetic_case.json**

## 合成 cross-file 案例

```
场景：TestClass -> ServiceFacade -> DataProcessor -> BuggyHelper

SBFL 结果：
  BuggyHelper rank = NOT FOUND（Ochiai = 0.000，从未直接覆盖）

WLBS 结果：
  BuggyHelper rank = 4（kappa = 0.0375，经3跳传播）
  传播路径：TestClass(0.10) -> ServiceFacade(0.15) -> DataProcessor(0.075) -> BuggyHelper(0.0375)
```

图表：`figures/synthetic_case_study.pdf`
