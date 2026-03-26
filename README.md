<div align="center">

<!-- Language switcher -->
**[English](#english)** · **[中文](#chinese)**

<br>

<img src="https://img.shields.io/badge/python-3.8+-brightgreen" alt="Python">
<img src="https://img.shields.io/pypi/v/wlbs-scan" alt="PyPI">
<img src="https://img.shields.io/badge/license-BSL_1.1-orange" alt="License">
<img src="https://img.shields.io/badge/paper_claims-15%2F15_validated-brightgreen" alt="Validated">
<img src="https://img.shields.io/badge/patent-CN_2026103746505-blue" alt="Patent">

</div>

---

<a name="english"></a>

# wlbs-scan

> **A code scanner that learns from your failures. Every bug you fix makes it smarter.**

wlbs-scan finds the files in your codebase **most likely to fail next** — before your tests do. It maps real failure history onto your dependency graph, so it knows not just *that* a file failed, but *where* in the call chain the root cause actually lives.

---

## Evidence — Benchmark Results (March 2026)

The core problem: most AI repair agents keep fixing the wrong file.

```
Test failure lands in:   rbac.py
Actual bug lives in:     roles.py  ← one import hop upstream
```

Standard agents edit `rbac.py` repeatedly. wlbs-scan looks upstream.

```
┌─────────────────────────────────────────────────────┐
│           Benchmark · 5 tasks · March 26, 2026      │
├──────────────────────┬──────────────┬───────────────┤
│ Mode                 │ Success rate │ Avg attempts  │
├──────────────────────┼──────────────┼───────────────┤
│ symptom_first (base) │     0 / 5    │      2.0      │
│ wlbs-scan            │     5 / 5    │      1.0      │
└──────────────────────┴──────────────┴───────────────┘
```

**wlbs-scan: 100% success · symptom_first: 0% success**

The heldout tasks used entirely fresh filenames (`policy_grid`, `rule_sheet`, `calc_panel`) with zero overlap against the training set — ruling out memorization. The tool generalized across both `missing_acl_key` (cross-file, 1 hop) and `direct_local_math` (same-file) bug families.

```
wlbs advisory on heldout_rule_widget
─────────────────────────────────────────────────────
Symptom file  : widget_entry.py
Suggested fix : rule_sheet.py  ← upstream, 1 hop away
Confidence    : 0.876
Reasoning     : historical lift 0.660 → 1.000
                routing policy confidence: 0.750
Result        : ✓ fixed in 1 attempt
```

Live server (March 2026):

```bash
$ curl http://111.231.112.127:8765/health
{"status":"ok","total_crystals":1,"port":8765}

# Upload a trace → points awarded + rule distilled:
{"accepted":true,"rule_generated":true,"points_earned":0.4}

# Pro key pulls the rule back immediately:
{"crystals":[{"rule":"bug_fix (python): resolved in 3 turns.","confidence":1.0}]}
```

---

## How it works

### The core insight

```
              Traditional approach              wlbs-scan
              ──────────────────────           ──────────────────────

  Failure     rbac.py ← agent edits here       rbac.py   κ=0.31
  history     rbac.py ← edits again            roles.py  κ=0.85 ⚡ ← fix here
  stored as   rbac.py ← edits again
              text summaries                   curvature on the dependency graph
```

Every file gets a **curvature** κ ∈ [0, 1] computed from its failure/fix history *and* its position in the import graph. When a test fails, curvature propagates upstream through dependencies (Aporia backprop: `Δκ = α · λ^d`, exponential decay by hop distance). A **singularity** (κ ≥ 0.7, sustained across multiple failure cycles) signals structural fragility — not a random fluke.

### Architecture

```
  your codebase
       │
       ▼
  ┌────────────┐     import graph     ┌──────────────────┐
  │  scanner   │ ──────────────────▶  │  dependency map  │
  └────────────┘                      └──────────────────┘
       │                                       │
       │  test results                         │ Aporia backprop
       ▼                                       ▼
  ┌────────────┐                      ┌──────────────────┐
  │  world-    │  curvature history   │   risk map       │
  │  line log  │ ──────────────────▶  │  κ per node      │
  └────────────┘                      └──────────────────┘
       │                                       │
       │  (Pro) upload                         │  wlbs advisory
       ▼                                       ▼
  ┌────────────┐                      ┌──────────────────┐
  │  shared    │  rule download       │  fix suggestion  │
  │  crystal   │ ◀────────────────    │  + root-cause    │
  │  library   │                      │  file path       │
  └────────────┘                      └──────────────────┘
```

Full theory: [PAPER.md](PAPER.md) · Patent: CN 2026103746505 · CN 2026103756225 · arXiv cs.SE/cs.AI March 2026

---

## Features

| Feature | What it does |
|---|---|
| **Risk map** | κ score for every file; highlights singularities |
| **Root-cause routing** | Points to upstream source, not downstream symptom |
| **Continual learning** | Curvature updates after every test run |
| **Aporia backprop** | Failure signal decays with hop distance |
| **Shared experience** *(Pro)* | Distilled rules from community bug-fix sessions |
| **Resolution-decay context** | Foveal history assembly — denser near the problem |
| **Git blame integration** | Line-level attribution for high-κ nodes |
| **CI gate** | Exit 1 on singularity — block the merge |
| **Dashboard** *(Pro)* | Heatmap web UI |

---

## Install

```bash
pip install wlbs-scan
```

No extra dependencies. Works fully offline for local scan. Python 3.8+.

---

## Quick start

### Step 1 — Sign up (once)

```bash
wlbs begin
```

```
wlbs begin — onboarding
Step 1/2  Register
Email: you@example.com
Verification code: 482910
Account created! Signed in as you@example.com (tier: free)
Credentials saved to ~/.wlbs/config.json
```

No password. No credit card. Credentials auto-saved; run `wlbs begin` again on any new machine.

### Step 2 — Scan your project

```bash
wlbs bug
# or specify a subdirectory:
wlbs bug src/
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  wlbs-scan v0.6.3 · 312 nodes · 1 singularity
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RISK       κ      FAIL  FIX   NODE
  ─────────────────────────────────────────────────
  HIGH  0.821  ⚡      4    1   auth.RBACManager.grant
  HIGH  0.774  ⚠       2    0   db.Session.commit
  MED   0.631           1    1   api.router.create_user
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

`⚡` = singularity (structural, fix urgently). `κ ≥ 0.75` = HIGH. `κ ≥ 0.55` = MED.

### Step 3 — Get fix suggestions

```bash
wlbs fix
```

```
  auth.RBACManager.grant  κ=0.821
  → 4 failures, 1 fix recorded
  → Related nodes: auth.permissions, db.Role
  → Suggestion: check grant() null boundary — roles=None triggers NoneType
```

### Run tests with auto-recording

```bash
wlbs . --pytest tests/
```

Every test result is automatically recorded. wlbs gets smarter with each run.

---

## All commands

| Command | What it does |
|---|---|
| `wlbs begin` | Sign up / sign in + configure pytest |
| `wlbs bug` | Scan + print risk map |
| `wlbs bug src/` | Scan a specific directory |
| `wlbs fix` | Fix suggestions for high-κ nodes |
| `wlbs . --pytest tests/` | Run pytest + auto-record results |
| `wlbs . --history` | Show what the system has learned |
| `wlbs . --diff` | Curvature delta since last scan |
| `wlbs . --blame src/foo.py` | Line-level git attribution |
| `wlbs . --export-html report.html` | HTML visual report |
| `wlbs . --watch` | Re-scan on every file save |
| `wlbs . --lang js` | Scan JS/TS codebase |
| `wlbs . --ci` | Exit 1 if singularity detected |
| `wlbs . --context src/foo.py` | Resolution-decay context for a file |
| `wlbs . --dashboard` | Heatmap web UI *(Pro)* |
| `wlbs . --status` | Account tier and points balance |

---

## Free vs Pro

| Feature | Free | Pro ($9.9/mo) |
|---|---|---|
| Local risk scan | ✅ | ✅ |
| Email sign-up | ✅ | ✅ |
| Auto-record pytest results | ✅ | ✅ |
| Local world-line history | ✅ | ✅ |
| Singularity detection | ✅ | ✅ |
| Fix suggestions | Local only | Cloud-enhanced |
| Shared experience library | ✗ | ✅ |
| Rule downloads after each session | ✗ | ✅ |
| Dashboard (`--dashboard`) | ✗ | ✅ |
| Points earn rate | 0.3× / upload | 0.5× / upload |

**Points:** every trace upload earns points. 100 points = 1 free Pro key (30 days). Points reset December 31.

**Upgrade:** contact valhuang@kaiwucl.com or WeChat val001813.

---

## CI integration

```yaml
# .github/workflows/ci.yml
- name: Risk gate
  run: wlbs . --ci --pytest tests/
```

```bash
# .git/hooks/pre-commit
wlbs . --ci
```

---

## Self-validate

```bash
python -m wlbs_scan.validate
```

Runs all 15 paper claims. All 15 pass on a clean install.

---

## License

BSL 1.1 — free for non-commercial use, research, internal evaluation. Commercial use requires a license. Auto-converts to Apache 2.0 on 2029-01-01.

---

## Contact

**Zhongchang Huang (黄中常)**  
Email: valhuang@kaiwucl.com · WeChat: val001813  
GitHub: [val1813/wlbs-cli](https://github.com/val1813/wlbs-cli)

---
---

<a name="chinese"></a>

# wlbs-scan（中文）

> **会从你的 bug 里学习的代码扫描器。你修的每一个 bug，都让它变得更聪明。**

wlbs-scan 找出你代码库里**最可能下一个挂掉的文件** —— 在测试挂之前告诉你。它把失败历史映射到依赖图上，不只告诉你哪个文件失败了，还能追溯根因到底在调用链的哪一层。

---

## 效果数据（2026年3月实测）

核心问题：大多数 AI 修 bug 的工具总在修错文件。

```
测试报错位置：  rbac.py    ← 工具疯狂在这里改
真正的 bug：   roles.py   ← 上游一跳，这里才是根因
```

标准方案在 `rbac.py` 反复修改，永远修不好。wlbs-scan 往上找。

```
┌─────────────────────────────────────────────────────┐
│           基准测试 · 5 个任务 · 2026年3月26日       │
├──────────────────────┬──────────────┬───────────────┤
│ 模式                 │  成功率      │  平均尝试次数 │
├──────────────────────┼──────────────┼───────────────┤
│ symptom_first（对照）│    0 / 5     │      2.0      │
│ wlbs-scan            │    5 / 5     │      1.0      │
└──────────────────────┴──────────────┴───────────────┘
```

**wlbs-scan：100% · 对照组：0%**

Heldout 任务全部使用训练集从未出现的新文件名（`policy_grid`、`rule_sheet`、`calc_panel`），与训练集零重叠，排除了记忆作弊的可能。工具在跨文件（cross-file, 1 hop）和同文件（direct_local_math）两种 bug 类型上均成功泛化。

```
wlbs 建议（heldout_rule_widget 任务）
─────────────────────────────────────────────────────
报错文件   : widget_entry.py
建议检查   : rule_sheet.py  ← 上游一跳
置信度     : 0.876
推理依据   : 历史 lift 0.660 → 1.000
             路由策略置信度: 0.750
结果       : ✓ 1 次尝试修复完成
```

实时服务器（2026年3月）：

```bash
curl http://111.231.112.127:8765/health
→ {"status":"ok","total_crystals":1,"port":8765}

上传轨迹 → {"accepted":true,"rule_generated":true,"points_earned":0.4}
Pro 下载规则 → {"rule":"bug_fix (python): resolved in 3 turns.","confidence":1.0}
```

---

## 原理

### 核心思路

```
              传统方案                          wlbs-scan
              ──────────────────────           ──────────────────────

  失败        rbac.py ← 改这里                 rbac.py   κ=0.31
  历史        rbac.py ← 再改                   roles.py  κ=0.85 ⚡ ← 改这里
  存成         rbac.py ← 又改
              自然语言摘要                      依赖图上的曲率值
```

每个文件有一个**曲率** κ ∈ [0, 1]，由失败/修复历史和 import 图位置共同决定。测试失败时，曲率沿依赖图向上传播（Aporia 反向传播：`Δκ = α · λ^d`，按跳数指数衰减）。**奇点**（κ ≥ 0.7，多轮失败后仍居高）代表结构性脆弱，不是随机噪声。

### 架构图

```
  你的代码库
       │
       ▼
  ┌────────────┐   import 图    ┌──────────────────┐
  │   扫描器   │ ─────────────▶ │   依赖关系图     │
  └────────────┘                └──────────────────┘
       │                                │
       │  测试结果                      │ Aporia 反向传播
       ▼                                ▼
  ┌────────────┐                ┌──────────────────┐
  │  世界线    │  曲率历史      │   风险图         │
  │  日志      │ ─────────────▶ │  每节点 κ 值     │
  └────────────┘                └──────────────────┘
       │                                │
       │  (Pro) 上传                    │  wlbs 建议
       ▼                                ▼
  ┌────────────┐                ┌──────────────────┐
  │  共享经验  │  规则下载      │  修复建议        │
  │  晶体库    │ ◀────────────  │  + 根因文件路径  │
  └────────────┘                └──────────────────┘
```

完整理论：[PAPER.md](PAPER.md) · 专利：CN 2026103746505 · CN 2026103756225 · arXiv cs.SE/cs.AI 2026年3月

---

## 功能一览

| 功能 | 说明 |
|---|---|
| **风险图** | 每个文件的 κ 分值，高亮奇点节点 |
| **根因路由** | 定位上游根因，而非下游报错位置 |
| **持续学习** | 每次测试后自动更新曲率 |
| **Aporia 反向传播** | 失败信号按跳数指数衰减传播 |
| **共享经验库** *(Pro)* | 社区 bug 修复会话提炼的规则 |
| **分辨率衰减上下文** | 仿生视网膜中央凹，越近越密集 |
| **Git blame 集成** | 高风险节点的行级 git 归因 |
| **CI 门控** | 奇点时 exit 1，阻断合并 |
| **热力图 Dashboard** *(Pro)* | Web 可视化界面 |

---

## 安装

```bash
pip install wlbs-scan
```

无额外依赖。本地扫描完全离线可用。需要 Python 3.8+。

---

## 快速开始

### 第一步：注册（只需做一次）

```bash
wlbs begin
```

```
wlbs begin — onboarding
Step 1/2  Register
Email: 你的邮箱@example.com
验证码已发送，请查收邮件。
Verification code: 482910
账号已创建！已登录 你的邮箱@example.com（tier: free）
凭证保存至 ~/.wlbs/config.json
```

无需密码，无需信用卡。凭据自动保存，换新机器再跑一次 `wlbs begin` 即可。

`wlbs begin` 还会自动检测并配置 pytest 插件，之后每次 `pytest` 运行都自动上报结果，越用越准。

### 第二步：扫描项目

```bash
wlbs bug
# 或指定目录：
wlbs bug src/
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  wlbs-scan v0.6.3 · 312 个节点 · 1 个奇点
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  风险        κ      失败  修复  节点
  ─────────────────────────────────────────────────
  HIGH  0.821  ⚡      4    1   auth.RBACManager.grant
  HIGH  0.774  ⚠       2    0   db.Session.commit
  MED   0.631           1    1   api.router.create_user
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

`⚡` = 奇点（结构性问题，立即修）。`κ ≥ 0.75` = HIGH。`κ ≥ 0.55` = MED。

### 第三步：获取修复建议

```bash
wlbs fix
```

```
  auth.RBACManager.grant  κ=0.821
  → 历史上 4 次失败，1 次修复
  → 相关节点: auth.permissions, db.Role
  → 建议: 检查 grant() 的空值边界，roles 为 None 时会触发 NoneType 错误
```

### 跑测试时自动记录

```bash
wlbs . --pytest tests/
```

每次测试结果自动记录，wlbs 越用越准。

---

## 全部命令

| 命令 | 功能 |
|---|---|
| `wlbs begin` | 注册 + 自动配置 pytest |
| `wlbs bug` | 扫描 + 风险图 |
| `wlbs bug src/` | 扫描指定目录 |
| `wlbs fix` | 高风险节点修复建议 |
| `wlbs . --pytest tests/` | 跑测试 + 自动记录 |
| `wlbs . --history` | 查看学习历史 |
| `wlbs . --diff` | 曲率变化对比 |
| `wlbs . --blame src/foo.py` | 行级 git 归因 |
| `wlbs . --export-html report.html` | HTML 可视化报告 |
| `wlbs . --watch` | 文件变化监听，自动重扫 |
| `wlbs . --lang js` | 扫描 JS/TS 项目 |
| `wlbs . --ci` | 奇点时 exit 1（CI 门控）|
| `wlbs . --context src/foo.py` | 该文件的分辨率衰减上下文 |
| `wlbs . --dashboard` | 热力图 Web 界面 *(Pro)* |
| `wlbs . --status` | 查看账户积分 |

---

## 免费版 vs Pro

| 功能 | 免费版 | Pro（¥70/月）|
|---|---|---|
| 本地风险扫描 | ✅ | ✅ |
| 邮箱注册登录 | ✅ | ✅ |
| pytest 自动记录 | ✅ | ✅ |
| 本地世界线历史 | ✅ | ✅ |
| 奇点检测 | ✅ | ✅ |
| 修复建议 | 仅本地 | 云端增强 |
| 共享经验库 | ✗ | ✅ |
| 规则自动下载 | ✗ | ✅ |
| 热力图 Dashboard | ✗ | ✅ |
| 积分获取速率 | 0.3× / 次 | 0.5× / 次 |

**积分系统：** 每次上传轨迹自动得分，100 分兑换一个 Pro key（30 天），每年 12 月 31 日清零。

**升级 Pro：** 联系 valhuang@kaiwucl.com 或微信 val001813，收款后立即发 key。

---

## CI 集成

```yaml
# .github/workflows/ci.yml
- name: 风险门控
  run: wlbs . --ci --pytest tests/
```

```bash
# .git/hooks/pre-commit
wlbs . --ci
```

---

## 自验证

```bash
python -m wlbs_scan.validate
```

运行全部 15 条 paper claim，全部通过。

---

## 许可证

BSL 1.1：非商业用途、研究、内部评估免费；商业使用需授权；2029-01-01 自动转为 Apache 2.0。

---

## 联系作者

**黄中常 (Zhongchang Huang)**  
邮箱：valhuang@kaiwucl.com · 微信：val001813  
GitHub：[val1813/wlbs-cli](https://github.com/val1813/wlbs-cli)
