# wlbs-scan v0.5

**[English](#english) | [中文](#中文)**

---

<a name="english"></a>

## English

**Static + dynamic behavior graph scanner based on the World-Line Behavior Space (WLBS) framework.**

Learns from your failures. Gets smarter over time. Zero dependencies beyond Python 3.8+.

[![Python](https://img.shields.io/badge/python-3.8+-brightgreen)]()
[![License](https://img.shields.io/badge/license-BSL_1.1-orange)](LICENSE)
[![Validation](https://img.shields.io/badge/paper_claims-8%2F8_validated-brightgreen)](validation/VALIDATION_RESULTS.md)

---

### Install

```bash
pip install -e .
wlbs-scan --help
```

Or run directly (no install needed):
```bash
python wlbs_scan.py <path>
```

---

### Commands

| Command | What it does |
|---|---|
| `wlbs-scan .` | Scan + show risk map |
| `wlbs-scan . --record-failure rbac` | Record a test failure (teaches the system) |
| `wlbs-scan . --record-fix roles` | Record a fix (updates curvature down) |
| `wlbs-scan . --pytest tests/` | Auto-run pytest + record all results into world-lines |
| `wlbs-scan . --history` | View what the system has learned |
| `wlbs-scan . --diff` | Curvature delta since last scan |
| `wlbs-scan . --suggest` | Actionable fix recommendations for high-risk nodes |
| `wlbs-scan . --moe` | MoE expert routing map (WLBS-guided activation weights) |
| `wlbs-scan . --blame` | Git blame on high-curvature nodes (line-range attribution) |
| `wlbs-scan . --export-html report.html` | Full HTML visualization report |
| `wlbs-scan . --badges` | README shield badge markdown |
| `wlbs-scan . --ci --fail-above 0.85` | CI mode — exit 1 if threshold exceeded |
| `wlbs-scan . --init-hook` | Install as git pre-commit hook |
| `wlbs-scan . --watch --pytest tests/` | Watch files + auto-rerun tests on change |
| `wlbs-scan src/ --lang js` | Scan JavaScript / TypeScript projects |
| `wlbs-scan . --json` | JSON output for CI/CD pipelines |
| `wlbs-scan . --dist roles rbac` | Behavioral distance between two nodes |
| `wlbs-scan . --reset` | Clear all learned history |

---

### How curvature κ is computed

Curvature κ(n) ∈ [0, 1] for each node (function / class / module):

```
If world-line history exists (failure_count > 0):
    bonus = 0.40 × history_signal + 0.15 × git_signal
    κ(n)  = static_curvature + bonus          # additive — failures only raise κ
Else if git history exists:
    κ(n)  = 0.45 × static + 0.55 × git
Else:
    κ(n)  = static_curvature

static_curvature = 0.35×(complexity/max_c) + 0.25×(import_count/max_i)
                 + 0.10×(line_count/max_l) + 0.15×(no_exception_handling)

history_signal   = recent_failure_rate × 0.8 + (failure_count/20) × 0.2
                   × discount (0.7 if last event was a fix, else 1.0)
```

**Aporia / Backpropagation** — when a node with `failure_count > 0` reaches κ ≥ 0.5,
its failure signal propagates upstream along dependency edges with exponential decay:

```
Δκ(dep) = κ(seed) × 0.5^depth        (paper §3.2: Δκ = α·λ^d)
```

This allows the system to identify **root-cause modules** that have no direct failures
but are depended upon by failing nodes.

---

### Singularity detection

A **singularity** is a high-curvature node (κ ≥ 0.55) that:
- Has at least one caller (`called_by > 0`) or is imported by other modules
- Has structural complexity > 2

Singularities are upstream root-cause candidates — the place to look when a failure
manifests downstream.

---

### Validated claims (paper § cross-reference)

All claims below are reproduced by running `python validation/run_validation.py`.
See [`validation/VALIDATION_RESULTS.md`](validation/VALIDATION_RESULTS.md) for the full run log.

| Paper Section | Claim | Result | Measured |
|---|---|---|---|
| §4 Impl | Graph construction speed | ✅ | avg 95–100 ms (3-file demo project) |
| §3.1 Def 2 | Behavioral distance d(roles, rbac) = 1 hop | ✅ | d = 1 |
| §3.2 | rbac κ rises after recording failures | ✅ | 0.820 → 1.000 (+0.180) |
| §3.2 | Aporia: roles κ rises via backprop (no direct failure) | ✅ | 0.405 → 0.905 (+0.500) |
| §3.1 Def 4 | Singularity detected after cross-file failures | ✅ | singularities=[rbac] |
| §3.1 Def 4 | roles identified via backprop (κ > static) | ✅ | κ=0.905, static=0.405 |
| §3 General | World-line accumulation: κ non-decreasing | ✅ | monotone series confirmed |
| §4 Impl | --pytest auto-records pass/fail into world-lines | ✅ | 2 events written |

> **Reproduce:** `python validation/run_validation.py` — rewrites `VALIDATION_RESULTS.md` with live data.

---

### Demo project (roles.py → rbac.py)

The `demo/` directory mirrors the paper's Figure 1 concrete failure scenario:

```
demo/
  roles.py          # root-cause module — 'admin' key missing in PERMISSIONS
  rbac.py           # downstream — imports roles.get_permissions(), crashes on 'admin'
  tests/
    test_rbac.py    # 4 pass / 2 intentional fail (test_admin_access, test_grant_permissions)
```

Run the demo:
```bash
cd demo
python ../wlbs_scan.py . --pytest tests/
python ../wlbs_scan.py . --history
python ../wlbs_scan.py . --dist roles rbac
```

---

### MoE integration

`--moe` shows how a Mixture-of-Experts system routes gate decisions using curvature as activation weight:

```
p(expert_n) = κ(n) / Σκ
```

High-curvature nodes activate specialized experts (LoRA adapters in a full system).
Singularities are targeted first when failure signals propagate upstream.

See: *World-Line Behavior Space* (Huang, 2026) · CN 2026103746505 · CN 2026103756225

---

### Memory

All history is stored in `.wlbs/world_lines.json` in your project root.
The file accumulates across sessions — the longer you use wlbs-scan, the more accurate its curvature estimates become.

```bash
wlbs-scan . --history    # see everything it has learned
wlbs-scan . --reset      # start over
```

---

### Roadmap

| Feature | Status |
|---|---|
| Python AST graph + curvature | ✅ v0.5 |
| World-line persistence | ✅ v0.5 |
| Aporia backpropagation (Δκ = α·λ^d) | ✅ v0.5 |
| Singularity detection | ✅ v0.5 |
| --pytest auto-record | ✅ v0.5 |
| --blame line-range git attribution | ✅ v0.5 |
| --export-html visualization | ✅ v0.5 |
| --watch file change detection | ✅ v0.5 |
| JS/TS support (--lang js) | ✅ v0.5 |
| CI mode + pre-commit hook | ✅ v0.5 |
| LLM-guided repair suggestions (--suggest reasoning chain) | 🔲 v0.6 |
| Cross-repo world-line sharing | 🔲 v0.6 |
| Java / Go / Rust AST parsers | 🔲 v0.6 |
| VS Code extension | 🔲 v0.7 |
| GitHub Actions official action | 🔲 v0.7 |
| Online dashboard (world-line cloud sync) | 🔲 v0.8 |

---

### Theory

> *World-Line Behavior Space: A Unified Framework for Continual Learning and Spatial Root-Cause Attribution in AI-Driven Autonomous Systems*
> Zhongchang Huang, 2026
> CN Patent Applications 2026103746505 · 2026103756225

---

### License

**Business Source License 1.1 (BSL 1.1)**

- Free for non-commercial use, research, and internal evaluation
- Commercial use in third-party products/services requires a separate license
- Automatically converts to **Apache 2.0** on **2029-01-01**

See [`LICENSE`](LICENSE) for full terms.
Patent protection: CN 2026103746505 · CN 2026103756225

---

### Contact / 联系作者

**Zhongchang Huang (黄中常)**
Email: valhuang@kaiwucl.com
WeChat: val001813

---
---

<a name="中文"></a>

## 中文

**基于世界线行为空间（WLBS）框架的静态+动态行为图扫描工具。**

从你的失败中学习，越用越准。除 Python 3.8+ 外零依赖。

---

### 安装

```bash
pip install -e .
wlbs-scan --help
```

或直接运行（无需安装）：
```bash
python wlbs_scan.py <路径>
```

---

### 命令一览

| 命令 | 功能 |
|---|---|
| `wlbs-scan .` | 扫描并显示风险图谱 |
| `wlbs-scan . --record-failure rbac` | 记录测试失败（训练系统） |
| `wlbs-scan . --record-fix roles` | 记录修复成功（曲率下调） |
| `wlbs-scan . --pytest tests/` | 自动运行 pytest 并将结果写入世界线 |
| `wlbs-scan . --history` | 查看系统已学习的内容 |
| `wlbs-scan . --diff` | 与上次扫描对比曲率变化 |
| `wlbs-scan . --suggest` | 高风险节点的修复建议 |
| `wlbs-scan . --moe` | MoE 专家路由权重图（WLBS 引导） |
| `wlbs-scan . --blame` | 高曲率节点的 git blame（行级归因） |
| `wlbs-scan . --export-html report.html` | 导出 HTML 可视化报告 |
| `wlbs-scan . --badges` | 生成 README 徽章 markdown |
| `wlbs-scan . --ci --fail-above 0.85` | CI 模式，超阈值退出码非零 |
| `wlbs-scan . --init-hook` | 安装为 git pre-commit hook |
| `wlbs-scan . --watch --pytest tests/` | 监听文件变化并自动重跑测试 |
| `wlbs-scan src/ --lang js` | 扫描 JavaScript / TypeScript 项目 |
| `wlbs-scan . --json` | JSON 输出，接入 CI/CD 流水线 |
| `wlbs-scan . --dist roles rbac` | 计算两个节点间的行为距离 |
| `wlbs-scan . --reset` | 清空所有学习历史 |

---

### 曲率 κ 计算方式

每个节点（函数/类/模块）的曲率 κ(n) ∈ [0, 1]：

```
若有世界线历史（failure_count > 0）：
    bonus = 0.40 × history_signal + 0.15 × git_signal
    κ(n)  = static_curvature + bonus     # 加法型：失败只会提升 κ
若仅有 git 历史：
    κ(n)  = 0.45 × static + 0.55 × git
否则：
    κ(n)  = static_curvature

static_curvature = 0.35×(复杂度/最大) + 0.25×(被引入数/最大)
                 + 0.10×(行数/最大) + 0.15×(无异常处理)
```

**Aporia / 曲率反向传播** — 当 `failure_count > 0` 且 κ ≥ 0.5 的节点存在时，
失败信号沿依赖边向上游传播，按指数衰减：

```
Δκ(dep) = κ(seed) × 0.5^depth        （论文 §3.2: Δκ = α·λ^d）
```

这让系统能识别**没有直接失败记录、但被失败节点依赖的根因模块**。

---

### 验证数据（论文声明对照）

所有数据均通过 `python validation/run_validation.py` 真实测量，
完整记录见 [`validation/VALIDATION_RESULTS.md`](validation/VALIDATION_RESULTS.md)。

| 论文章节 | 声明 | 结果 | 实测数据 |
|---|---|---|---|
| §4 实现 | 行为图构建速度 | ✅ | avg 95–100 ms（3 文件 demo 项目） |
| §3.1 定义 2 | 行为距离 d(roles, rbac) = 1 跳 | ✅ | d = 1 |
| §3.2 | rbac κ 在记录失败后上升 | ✅ | 0.820 → 1.000（+0.180） |
| §3.2 | Aporia：roles κ 经反向传播上升（无直接失败） | ✅ | 0.405 → 0.905（+0.500） |
| §3.1 定义 4 | 跨文件失败后检测到奇点 | ✅ | singularities=[rbac] |
| §3.1 定义 4 | roles 被反向传播识别（κ > static） | ✅ | κ=0.905, static=0.405 |
| §3 总体 | 世界线累积：κ 单调不递减 | ✅ | 单调序列已验证 |
| §4 实现 | --pytest 自动记录通过/失败到世界线 | ✅ | 2 个事件已写入 |

> **复现方法：** `python validation/run_validation.py`

---

### Demo 项目（roles.py → rbac.py）

`demo/` 目录复现了论文图 1 的具体失败场景：

```
demo/
  roles.py          # 根因模块 — PERMISSIONS 中缺少 'admin' 键
  rbac.py           # 下游模块 — 导入 roles.get_permissions()，访问 'admin' 时崩溃
  tests/
    test_rbac.py    # 4 通过 / 2 故意失败
```

```bash
cd demo
python ../wlbs_scan.py . --pytest tests/
python ../wlbs_scan.py . --history
python ../wlbs_scan.py . --dist roles rbac
```

---

### 路线图

| 功能 | 状态 |
|---|---|
| Python AST 图 + 曲率计算 | ✅ v0.5 |
| 世界线持久化 | ✅ v0.5 |
| Aporia 反向传播（Δκ = α·λ^d） | ✅ v0.5 |
| 奇点（Singularity）检测 | ✅ v0.5 |
| --pytest 自动记录 | ✅ v0.5 |
| --blame 行级 git 归因 | ✅ v0.5 |
| --export-html 可视化报告 | ✅ v0.5 |
| --watch 文件变化监听 | ✅ v0.5 |
| JS/TS 支持（--lang js） | ✅ v0.5 |
| CI 模式 + pre-commit hook | ✅ v0.5 |
| LLM 引导的修复建议（推理链） | 🔲 v0.6 |
| 跨仓库世界线共享 | 🔲 v0.6 |
| Java / Go / Rust AST 解析器 | 🔲 v0.6 |
| VS Code 扩展 | 🔲 v0.7 |
| GitHub Actions 官方 Action | 🔲 v0.7 |
| 在线 Dashboard（世界线云同步） | 🔲 v0.8 |

---

### 理论基础

> *世界线行为空间：AI 驱动自主系统中持续学习与空间根因归因的统一框架*
> 黄中常，2026
> 中国专利申请 2026103746505 · 2026103756225

---

### 许可证

**Business Source License 1.1 (BSL 1.1)**

- 非商业用途、科研、内部评估免费使用
- 面向第三方的商业产品/服务需向作者申请商业授权
- **2029-01-01** 自动转为 **Apache 2.0**

完整条款见 [`LICENSE`](LICENSE)。
WLBS 方法论受专利保护：CN 2026103746505 · CN 2026103756225

---

### 联系作者

**黄中常 (Zhongchang Huang)**
邮箱：valhuang@kaiwucl.com
微信：val001813