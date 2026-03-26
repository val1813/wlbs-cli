<div align="center">

<br>

# 🔬 wlbs-scan

### Stop fixing the wrong file.

**wlbs-scan tells Claude exactly where the bug lives —<br>before it wastes 10 attempts on the symptom.**

<br>

[!\[PyPI](https://img.shields.io/pypi/v/wlbs-scan?color=brightgreen\&label=pip%20install%20wlbs-scan\&logo=python\&logoColor=white)](https://pypi.org/project/wlbs-scan/)
[!\[Python](https://img.shields.io/badge/python-3.8%2B-blue?logo=python\&logoColor=white)](https://pypi.org/project/wlbs-scan/)
[!\[License](https://img.shields.io/badge/license-BSL\_1.1-orange)](LICENSE)
[!\[Benchmark](https://img.shields.io/badge/benchmark-5%2F5\_tasks\_%E2%9C%93-brightgreen)](validation/)
[!\[Patent](https://img.shields.io/badge/patent-CN\_2026103746505-blue)](PAPER.md)

<br>

[**English**](#english)  ·  [**中文 Chinese**](#chinese)

<br>

</div>

\---

<a name="english"></a>

## The Problem in One Picture

```
 Test fails in:   rbac.py      ← Claude edits here. Again. Again. Again.
 Bug lives in:    roles.py     ← one import hop upstream. Never touched.
```

```
Without wlbs-scan                    With wlbs-scan
────────────────────────────         ──────────────────────────────────────
\[attempt 1]  edit rbac.py   ✗        wlbs advisory:
\[attempt 2]  edit rbac.py   ✗          📍 symptom    →  rbac.py
\[attempt 3]  edit rbac.py   ✗          ⚡ root cause  →  roles.py  κ=0.876
\[attempt 4]  edit rbac.py   ✗
\[attempt 5]  edit rbac.py   ✗        \[attempt 1]  edit roles.py  ✓  FIXED
```

\---

## 📊 Benchmark — March 2026

> 5 tasks. Heldout filenames had \*\*zero overlap\*\* with training — no memorization possible.

<div align="center">

||Baseline (symptom-first)|**wlbs-scan**|
|-|:-:|:-:|
|Tasks solved|0 / 5|**5 / 5**|
|Success rate|0%|**100%**|
|Avg attempts to fix|2.0|**1.0**|
|First-try root-cause accuracy|33%|**100%**|

</div>

Heldout tasks used fresh filenames (`policy\_grid`, `rule\_sheet`, `calc\_panel`) — never seen in training. Works on cross-file bugs (1 hop upstream) and same-file bugs alike.

<details>
<summary>▶ See a real advisory output</summary>

```
wlbs advisory · heldout\_rule\_widget
────────────────────────────────────────────────────────
  Symptom file   :  widget\_entry.py
  Suggested fix  :  rule\_sheet.py   ← upstream, 1 hop
  Confidence     :  0.876

  Reasoning:
    · symptom in widget\_entry; upstream candidate rule\_sheet 1 hop away
    · rule\_sheet historical lift: 0.660 → 1.000
    · routing policy confidence: 0.750

  Result: ✓ fixed in 1 attempt
          (baseline: 3 attempts, still failed)
────────────────────────────────────────────────────────
```

</details>

\---

## ⚡ Works With Claude — 3 Commands

```bash
# 1. Install
pip install wlbs-scan

# 2. Scan your project
wlbs bug

# 3. Scan → advisory auto-written to .wlbs/current\_advice.md
wlbs bug
```

Claude Code, Cursor, and any AI editor that reads your repo **automatically see which file to fix first.** No copy-paste needed.

\---

## 🚀 How It Works

wlbs-scan builds a **live risk map** from your real failure history, mapped onto the import graph.

```
  your codebase
       │
       ▼
  ┌─────────────────────┐
  │  dependency graph   │  ← import relationships between files
  └──────────┬──────────┘
             │  test failure signal
             │  propagates upstream
             │  Δκ = α · λ^d
             ▼
  ┌─────────────────────────────────────────┐
  │            risk map                     │
  │                                         │
  │   roles.py    κ = 0.876   ⚡ singularity │  ← fix this
  │   rbac.py     κ = 0.312                 │
  │   utils.py    κ = 0.091                 │
  └──────────┬──────────────────────────────┘
             │
             ▼
  ┌─────────────────────┐
  │   wlbs advisory     │  → paste into Claude
  │   "Open roles.py    │
  │    first. κ=0.876"  │
  └─────────────────────┘
```

Every file gets a **curvature score** κ ∈ \[0, 1]. When a test fails, the signal travels *upstream* through the import graph with exponential decay by hop distance. A **singularity** (κ ≥ 0.75, sustained) = structural fragility, not a random fluke. Fix it now.

\---

## 🎯 Features

||Feature||
|:-:|-|-|
|🗺️|**Risk map**|κ score + singularity flag for every file|
|🔍|**Root-cause routing**|Points to the source, not the symptom|
|🤖|**Auto-written advisory**|After every `wlbs bug`, `.wlbs/current\_advice.md` is written automatically — Claude Code / Cursor read it with zero copy-paste|
|📈|**Continual learning**|Gets smarter with every test run|
|🔗|**Dependency-aware backprop**|Failure signals travel the import graph|
|🔥|**Singularity detection**|Early warning on structurally fragile files|
|🌐|**Shared experience** *(Pro)*|Patterns distilled from community bug-fix sessions|
|🚦|**CI gate**|Block merges on singularity detection|
|📊|**Heatmap dashboard** *(Pro)*|Visual risk surface of your whole codebase|

\---

## 💻 Quick Start

### 1\. Install

```bash
pip install wlbs-scan
```

No extra dependencies. Works fully offline. Python 3.8+.

### 2\. Sign up — free, no password, no credit card

```bash
wlbs begin
```

```
Email: you@example.com
✓  Verification code sent
Code: 482910
✓  Account created · tier: free
✓  Credentials saved to \~/.wlbs/config.json
✓  pytest plugin configured automatically

Run: wlbs bug
```

Credentials auto-saved. Run `wlbs begin` again on any new machine to sign back in.

### 3\. Scan your project

```bash
wlbs bug
# or a specific directory:
wlbs bug src/
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  wlbs-scan v0.6.3  ·  312 nodes  ·  1 singularity ⚡
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RISK        κ       FAIL  FIX   NODE
  ───────────────────────────────────────────────────
  HIGH  0.821  ⚡        4    1   auth.RBACManager
  HIGH  0.774  ⚠         2    0   db.Session
  MED   0.631             1    1   api.router
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ = singularity (structural — fix urgently)
κ ≥ 0.75 = HIGH   κ ≥ 0.55 = MED
```

### 4\. Advisory is auto-written — Claude Code reads it instantly

After every `wlbs bug` scan, the advisory is automatically written to `.wlbs/current\_advice.md`:

```bash
wlbs bug
# → .wlbs/current\_advice.md written automatically
```

```
# .wlbs/current\_advice.md
## wlbs advisory — 2026-03-26

  auth.RBACManager  κ=0.821  ⚡ singularity
  → Open auth/permissions.py first (upstream, 1 hop)
  → grant() silently fails when roles=None — KeyError suppressed
  → Related: db.Role, auth.policy
```

Claude Code, Cursor, and any AI editor that reads your project **picks this up automatically** — no copy-paste, no manual context. Run `wlbs fix` any time to print the same advisory to your terminal.

> \*\*Free vs Pro difference:\*\* both tiers write the file. Pro advisories are enriched with cloud crystal data from the shared experience library, making suggestions more precise.

### 5\. Auto-record test results

```bash
wlbs . --pytest tests/
```

Every pass and fail is recorded automatically. The risk map improves with every run.

\---

## 📋 All Commands

|Command|What it does|
|-|-|
|`wlbs begin`|Sign up + auto-configure pytest|
|`wlbs bug`|Scan project, print risk map|
|`wlbs bug src/`|Scan a specific directory|
|`wlbs fix`|Print advisory to terminal (also auto-written to `.wlbs/current\_advice.md` after every scan)|
|`wlbs . --pytest tests/`|Run tests + auto-record results|
|`wlbs . --history`|Show what the system has learned|
|`wlbs . --diff`|Curvature delta since last scan|
|`wlbs . --blame src/foo.py`|Line-level git attribution for risky files|
|`wlbs . --export-html out.html`|Visual HTML risk report|
|`wlbs . --watch`|Re-scan on every file save|
|`wlbs . --lang js`|Scan JS/TS codebase|
|`wlbs . --ci`|Exit 1 on singularity (CI gate)|
|`wlbs . --context src/foo.py`|Resolution-decay context for a file|
|`wlbs . --dashboard`|Heatmap web UI *(Pro)*|
|`wlbs . --status`|Account tier + points balance|
|`wlbs --version`|Print version|

\---

## 🆓 Free vs Pro

|Feature|Free|Pro ($9.9/mo)|
|-|:-:|:-:|
|Local risk scan + singularity detection|✅|✅|
|Auto-write `.wlbs/current\_advice.md`|✅|✅|
|Advisory precision|Local analysis|☁️ + cloud crystals|
|Auto-record pytest results|✅|✅|
|Local world-line history|✅|✅|
|Shared experience library|✗|✅|
|Rule downloads after each session|✗|✅|
|Dashboard (`--dashboard`)|✗|✅|
|Points earn rate|0.3×|0.5×|

**Points:** every trace upload earns points. 100 pts = 1 free Pro key (30 days). Resets Dec 31.

**Upgrade:** email valhuang@kaiwucl.com or WeChat **val001813**

\---

## 🔧 CI Integration

```yaml
# .github/workflows/ci.yml
- name: wlbs risk gate
  run: wlbs . --ci --pytest tests/
  # exits 1 if a singularity is detected — blocks the merge
```

```bash
# .git/hooks/pre-commit
wlbs . --ci
```

\---

## 📄 Research \& License

**Paper:** *World-Line Behavior Space: A Unified Framework for Continual Learning and Spatial Root-Cause Attribution* · arXiv cs.SE/cs.AI · March 2026  
**Patents:** CN 2026103746505 · CN 2026103756225  
**Self-validate:** `python -m wlbs\_scan.validate` — all 15 paper claims pass on clean install.

BSL 1.1 — free for non-commercial use, research, internal evaluation. Auto-converts to Apache 2.0 on 2029-01-01.

\---

## 👤 Author

**Zhongchang Huang (黄中常)**  
valhuang@kaiwucl.com · WeChat: val001813  
[github.com/val1813/wlbs-cli](https://github.com/val1813/wlbs-cli)

<br>
<br>

\---

\---

<br>

<a name="chinese"></a>

<div align="center">

# 🔬 wlbs-scan

### 别再修错文件了。

**wlbs-scan 精确告诉 Claude 该去哪里找 bug ——<br>不再浪费 10 次尝试修症状文件。**

<br>

[!\[PyPI](https://img.shields.io/pypi/v/wlbs-scan?color=brightgreen\&label=pip%20install%20wlbs-scan\&logo=python\&logoColor=white)](https://pypi.org/project/wlbs-scan/)
[!\[Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://pypi.org/project/wlbs-scan/)

</div>

\---

## 一张图说清问题

```
 测试报错位置：   rbac.py     ← Claude 在这里一遍遍改，改不好
 Bug 真正在：    roles.py    ← 上游一跳，从来没人看它
```

```
没有 wlbs-scan                        有 wlbs-scan
─────────────────────────────         ──────────────────────────────────────
\[第1次]  改 rbac.py   ✗               wlbs 建议：
\[第2次]  改 rbac.py   ✗                 📍 症状文件  →  rbac.py
\[第3次]  改 rbac.py   ✗                 ⚡ 根因文件  →  roles.py  κ=0.876
\[第4次]  改 rbac.py   ✗
\[第5次]  改 rbac.py   ✗               \[第1次]  改 roles.py  ✓  修好了
```

\---

## 📊 基准测试 — 2026年3月

> 5个任务，Heldout 文件名与训练集\*\*零重叠\*\* — 不可能靠记忆作弊。

<div align="center">

||对照组（symptom-first）|**wlbs-scan**|
|-|:-:|:-:|
|任务完成数|0 / 5|**5 / 5**|
|成功率|0%|**100%**|
|平均修复尝试次数|2.0|**1.0**|
|首次命中根因准确率|33%|**100%**|

</div>

Heldout 任务全用训练集从未出现的新文件名（`policy\_grid`、`rule\_sheet`、`calc\_panel`）。跨文件 bug（上游1跳）和同文件 bug 均成功。不是背答案，是真正学会了。

<details>
<summary>▶ 查看真实的 advisory 输出</summary>

```
wlbs 建议 · heldout\_rule\_widget 任务
────────────────────────────────────────────────────────
  症状文件   :  widget\_entry.py
  建议检查   :  rule\_sheet.py   ← 上游，距离 1 跳
  置信度     :  0.876

  推理依据：
    · 症状在 widget\_entry，上游候选 rule\_sheet 距离 1 跳
    · rule\_sheet 历史 lift：0.660 → 1.000
    · 路由策略置信度：0.750

  结果：✓ 1 次修复完成
        （对照组：3次，仍未修好）
────────────────────────────────────────────────────────
```

</details>

\---

## ⚡ 配合 Claude 使用 — 三条命令

```bash
# 1. 安装
pip install wlbs-scan

# 2. 扫描项目
wlbs bug

# 3. 扫描 → 建议自动写入 .wlbs/current\_advice.md
wlbs bug
```

Claude Code、Cursor 等 AI 编辑器**自动读取这个文件**，直接知道该先打开哪个文件。不用复制粘贴。

\---

## 🚀 原理

wlbs-scan 把你真实的失败历史映射到依赖图上，建立**实时风险图**。

```
  你的代码库
       │
       ▼
  ┌─────────────────────┐
  │      依赖图         │  ← 文件之间的 import 关系
  └──────────┬──────────┘
             │  测试失败信号
             │  向上游传播
             │  Δκ = α · λ^d
             ▼
  ┌─────────────────────────────────────────┐
  │              风险图                     │
  │                                         │
  │   roles.py    κ = 0.876   ⚡ 奇点        │  ← 修这里
  │   rbac.py     κ = 0.312                 │
  │   utils.py    κ = 0.091                 │
  └──────────┬──────────────────────────────┘
             │
             ▼
  ┌─────────────────────┐
  │    给 Claude 的建议  │  → 直接粘给 Claude
  │   "先打开 roles.py  │
  │    置信度 0.876"    │
  └─────────────────────┘
```

每个文件有一个**曲率** κ ∈ \[0, 1]。测试失败时信号沿 import 图**向上游传播**，按跳数指数衰减（`Δκ = α · λ^d`）。**奇点**（κ ≥ 0.75，持续多轮）= 结构性脆弱，立即修。

\---

## 🎯 核心功能

||功能||
|:-:|-|-|
|🗺️|**风险图**|每个文件的 κ 分值 + 奇点标记|
|🔍|**根因路由**|定位上游根源，不是下游症状|
|🤖|**自动写入建议文件**|每次 `wlbs bug` 扫描后自动生成 `.wlbs/current\_advice.md`，Claude Code / Cursor 零粘贴直接读取|
|📈|**持续学习**|每次测试自动更新，越用越准|
|🔗|**依赖感知传播**|失败信号沿 import 图传播|
|🔥|**奇点检测**|结构性脆弱文件再次崩掉之前预警|
|🌐|**共享经验库** *(Pro)*|社区真实 bug 修复经验提炼的规则|
|🚦|**CI 门控**|检测到奇点时阻断合并|
|📊|**热力图 Dashboard** *(Pro)*|代码库风险面可视化|

\---

## 💻 快速开始

### 1\. 安装

```bash
pip install wlbs-scan
```

无额外依赖。本地扫描完全离线。Python 3.8+。

### 2\. 注册 — 免费，无密码，无信用卡

```bash
wlbs begin
```

```
Email: 你的邮箱@example.com
✓  验证码已发送
Code: 482910
✓  账号已创建 · tier: free
✓  凭证保存至 \~/.wlbs/config.json
✓  pytest 插件已自动配置

运行：wlbs bug
```

凭据自动保存。换新机器再跑一次 `wlbs begin` 即可重新登录。

### 3\. 扫描项目

```bash
wlbs bug
# 或指定目录：
wlbs bug src/
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  wlbs-scan v0.6.3  ·  312 个节点  ·  1 个奇点 ⚡
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  风险         κ      失败  修复  节点
  ───────────────────────────────────────────────────
  HIGH  0.821  ⚡       4    1   auth.RBACManager
  HIGH  0.774  ⚠        2    0   db.Session
  MED   0.631            1    1   api.router
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ = 奇点（结构性，立即修）
κ ≥ 0.75 = HIGH   κ ≥ 0.55 = MED
```

### 4\. 建议自动写入 — Claude Code 直接读取

每次 `wlbs bug` 扫描完成后，建议文件自动写入项目根目录：

```bash
wlbs bug
# → .wlbs/current\_advice.md 自动生成
```

```
# .wlbs/current\_advice.md
## wlbs advisory — 2026-03-26

  auth.RBACManager  κ=0.821  ⚡ 奇点
  → 先打开 auth/permissions.py（上游依赖，距离 1 跳）
  → grant() 在 roles=None 时静默失败，KeyError 被吞
  → 相关节点：db.Role, auth.policy
```

Claude Code、Cursor 等 AI 编辑器**自动感知这个文件** — 不用复制粘贴，不用手动给上下文，扫完直接开修。随时运行 `wlbs fix` 可以把同样的内容打印到终端。

> \*\*免费版 vs Pro 的区别：\*\* 两个版本都会写这个文件。Pro 版的建议额外融合了云端共享晶体数据，定位更精准。

### 5\. 跑测试时自动记录

```bash
wlbs . --pytest tests/
```

每次测试结果自动记录，风险图持续更新，越用越准。

\---

## 📋 全部命令

|命令|功能|
|-|-|
|`wlbs begin`|注册 + 自动配置 pytest|
|`wlbs bug`|扫描 + 风险图|
|`wlbs bug src/`|扫描指定目录|
|`wlbs fix`|打印建议到终端（扫描后也自动写入 `.wlbs/current\_advice.md`）|
|`wlbs . --pytest tests/`|跑测试 + 自动记录|
|`wlbs . --history`|查看学习历史|
|`wlbs . --diff`|曲率变化对比|
|`wlbs . --blame src/foo.py`|行级 git 归因|
|`wlbs . --export-html out.html`|HTML 可视化报告|
|`wlbs . --watch`|文件变化时自动重扫|
|`wlbs . --lang js`|扫描 JS/TS 项目|
|`wlbs . --ci`|奇点时 exit 1（CI 门控）|
|`wlbs . --context src/foo.py`|该文件的分辨率衰减上下文|
|`wlbs . --dashboard`|热力图 Web 界面 *(Pro)*|
|`wlbs . --status`|账户积分余额|
|`wlbs --version`|打印版本号|

\---

## 🆓 免费版 vs Pro

|功能|免费版|Pro（¥70/月）|
|-|:-:|:-:|
|本地风险扫描 + 奇点检测|✅|✅|
|自动写入 `.wlbs/current\_advice.md`|✅|✅|
|建议精准度|本地分析|☁️ + 云端晶体|
|pytest 自动记录|✅|✅|
|本地世界线历史|✅|✅|
|共享经验库|✗|✅|
|规则自动下载|✗|✅|
|热力图 Dashboard|✗|✅|
|积分获取速率|0.3×|0.5×|

**积分：** 每次上传轨迹自动得分，100 分兑换 Pro key（30 天），每年 12 月 31 日清零。

**升级 Pro：** valhuang@kaiwucl.com · 微信 **val001813**

\---

## 🔧 CI 集成

```yaml
# .github/workflows/ci.yml
- name: wlbs 风险门控
  run: wlbs . --ci --pytest tests/
  # 检测到奇点时 exit 1，阻断 PR 合并
```

```bash
# .git/hooks/pre-commit
wlbs . --ci
```

\---

## 📄 研究 \& 协议

**论文：** *World-Line Behavior Space: A Unified Framework for Continual Learning and Spatial Root-Cause Attribution* · arXiv cs.SE/cs.AI · 2026年3月  
**专利：** CN 2026103746505 · CN 2026103756225  
**自验证：** `python -m wlbs\_scan.validate` — 全部 15 条 paper claim 通过。

BSL 1.1：非商业用途免费，2029-01-01 自动转为 Apache 2.0。

\---

## 👤 联系作者

**黄中常 (Zhongchang Huang)**  
valhuang@kaiwucl.com · 微信：val001813  
[github.com/val1813/wlbs-cli](https://github.com/val1813/wlbs-cli)

