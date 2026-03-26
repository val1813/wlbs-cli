

<a name="chinese"></a>

<div align="center">

# 🔬 wlbs-scan

### 别再修错文件了。毫秒级定位BUG文件位置，

**wlbs-scan 精确告诉 Claude 该去哪里找 bug ——<br>不再浪费 10 次尝试修症状文件。**

<br>

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

