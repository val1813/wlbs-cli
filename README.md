# wlbs-scan

**[English](#english) | [中文](#chinese)**

---

<a name="english"></a>

## English

> **A code scanner that learns from your failures. Every bug you fix makes it smarter for everyone.**

[![Python](https://img.shields.io/badge/python-3.8+-brightgreen)]()
[![PyPI](https://img.shields.io/pypi/v/wlbs-scan)](https://pypi.org/project/wlbs-scan/)
[![License](https://img.shields.io/badge/license-BSL_1.1-orange)](LICENSE)
[![Validation](https://img.shields.io/badge/paper_claims-15%2F15_validated-brightgreen)](validation/VALIDATION_RESULTS.md)

---

### What it does

wlbs-scan finds the files in your codebase **most likely to fail next** — before your tests do.

It builds a live risk map from your actual failure history. Every test run teaches it something. Pro users also draw from a shared pool of patterns distilled from real bug-fix sessions across the entire community.

---

### Evidence — live server, March 2026

```
$ curl http://111.231.112.127:8765/health
{"status":"ok","total_crystals":1,"port":8765}

# Upload a trace → points awarded + rule distilled:
{"accepted":true,"rule_generated":true,"points_earned":0.4}

# Pro key pulls the rule back immediately:
{"crystals":[{"rule":"bug_fix (python): resolved in 3 turns.","confidence":1.0}]}
```

Full install-to-scan-to-rule cycle in under 60 seconds on any Python 3.8+ machine.

---

### Install

```bash
pip install wlbs-scan
```

No extra dependencies. Works offline for local scan.

---

### Sign up (free)

```
$ wlbs --register

wlbs-scan · sign up / sign in
==============================
Email: you@example.com
Sending verification code to you@example.com...
Code sent! Check your inbox.
Verification code: 482910
Account created! Signed in as you@example.com (tier: free)
Credentials saved to ~/.wlbs/config.json
You're all set. Run: wlbs . to start scanning.
```

That's it. No password. No credit card. Key is saved automatically.
Run `wlbs --register` again any time to sign back in on a new machine.

---

### Quick start

```bash
# Scan your project — see the risk map
wlbs .

# Run tests + auto-record all results
wlbs . --pytest tests/

# See what the system has learned
wlbs . --history

# Get fix recommendations for hot files
wlbs . --suggest
```

Sample output:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RISK MAP  ·  3 nodes  ·  1 singularity
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ██  rbac         κ=0.847  ⚡ SINGULARITY
  ▓   roles        κ=0.612
  ░   utils        κ=0.201
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

A **singularity** (κ ≥ 0.7, repeated failures) means: *this file keeps breaking for structural reasons — fix it now.*

---

### All commands

| Command | What it does |
|---|---|
| `wlbs .` | Scan project + print risk map |
| `wlbs --register` | Sign up / sign in with email code |
| `wlbs . --pytest tests/` | Run pytest + auto-record all results |
| `wlbs . --history` | Show what the system learned about your codebase |
| `wlbs . --suggest` | Fix recommendations for high-risk files |
| `wlbs . --diff` | Curvature delta since last scan |
| `wlbs . --blame src/foo.py` | Line-level git attribution for risky files |
| `wlbs . --export-html report.html` | Visual HTML risk report |
| `wlbs . --watch` | Re-scan on every file save |
| `wlbs . --lang js` | Scan JS/TS codebase |
| `wlbs . --ci` | Exit 1 if singularity detected (CI gate) |
| `wlbs . --context src/foo.py` | Resolution-decay context for a specific file |
| `wlbs . --dashboard` | Open heatmap web UI *(Pro)* |
| `wlbs . --status` | Show account tier and points balance |
| `wlbs --version` | Print version |

---

### Free vs Pro

| Feature | Free | Pro ($9.9/mo) |
|---|---|---|
| Local risk scan | ✅ | ✅ |
| Sign up with email | ✅ | ✅ |
| Auto-record pytest results | ✅ | ✅ |
| Local world-line history | ✅ | ✅ |
| Singularity detection | ✅ | ✅ |
| Fix suggestions | Local only | Cloud-enhanced |
| Shared experience library | ✗ | ✅ |
| Auto rule downloads after each session | ✗ | ✅ |
| Dashboard (`--dashboard`) | ✗ | ✅ |
| Points earn rate | 0.3× / upload | 0.5× / upload |

**Points system:** every trace you upload earns points. 100 points = 1 free Pro key (30-day). Points reset December 31.

---

### Upgrade to Pro

**Option 1 — Buy directly:**
Contact **valhuang@kaiwucl.com** or WeChat **val001813**.
Receive your key immediately. Valid 30 days from first use.

**Option 2 — Earn points:**
Keep using the free tier. Upload traces, accumulate points.

```bash
# Check your balance
wlbs . --status
```

---

### pytest plugin (optional)

If you run `pytest` directly:

```python
# conftest.py
pytest_plugins = ['wlbs_scan.wlbs_pytest_plugin']
```

```bash
pytest tests/ --wlbs .
```

---

### CI / pre-commit

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

### Self-validate

```bash
python -m wlbs_scan.validate
```

Runs 15 paper claims. All 15 pass on a clean install.

---

### How it works

Every file gets a **curvature** κ ∈ [0, 1] from its failure/fix history and import-graph position. When a test fails, curvature propagates upstream (Aporia backprop: Δκ = α·λ^d). A **singularity** is a node where curvature stays high across multiple failure cycles — structural fragility, not random noise.

Full theory: [PAPER.md](PAPER.md) | Patent: CN 2026103746505 · CN 2026103756225

---

### License

BSL 1.1 — free for non-commercial use, research, internal evaluation.
Commercial use requires a license. Auto-converts to Apache 2.0 on 2029-01-01.

---

### Contact

**Zhongchang Huang (黄中常)**
Email: valhuang@kaiwucl.com | WeChat: val001813
GitHub: [val1813/wlbs-cli](https://github.com/val1813/wlbs-cli)

---

<a name="chinese"></a>

## 中文

> **会从你的 bug 里学习的代码扫描器。你修的每一个 bug，都让它变得更聪明。**

[![Python](https://img.shields.io/badge/python-3.8+-brightgreen)]()
[![PyPI](https://img.shields.io/pypi/v/wlbs-scan)](https://pypi.org/project/wlbs-scan/)

---

### 它是干什么的

wlbs-scan 找出你代码库里**最可能下一个挂掉的文件** —— 在测试挂之前告诉你。

根据你真实的失败历史建立风险图，每次测试都在教它。Pro 用户还能从社区经验库里受益。

---

### 效果证明（2026年3月实测）

```
curl http://111.231.112.127:8765/health
→ {"status":"ok","total_crystals":1,"port":8765}

上传轨迹 → {"accepted":true,"rule_generated":true,"points_earned":0.4}
Pro 下载规则 → {"rule":"bug_fix (python): resolved in 3 turns.","confidence":1.0}
```

---

### 安装

```bash
pip install wlbs-scan
```

---

### 注册（免费）

```
$ wlbs --register

wlbs-scan · sign up / sign in
==============================
Email: 你的邮箱@example.com
发送验证码中...
验证码已发送！请查收邮件。
Verification code: 482910
账号已创建！已登录 你的邮箱@example.com（tier: free）
凭证已保存到 ~/.wlbs/config.json
现在可以运行: wlbs . 开始扫描
```

**无需密码，无需信用卡。** key 自动保存，换新机器再跑一次 `wlbs --register` 即可。

---

### 快速开始

```bash
# 扫描项目，看风险图
wlbs .

# 跑测试，结果自动记录
wlbs . --pytest tests/

# 查看系统学到了什么
wlbs . --history

# 获取高风险文件修复建议
wlbs . --suggest
```

输出示例：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  风险图  ·  3 个节点  ·  1 个奇点
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ██  rbac         κ=0.847  ⚡ 奇点
  ▓   roles        κ=0.612
  ░   utils        κ=0.201
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**奇点** = 反复在同一文件失败，结构性问题，不是随机 bug。

---

### 全部命令

| 命令 | 功能 |
|---|---|
| `wlbs .` | 扫描 + 风险图 |
| `wlbs --register` | 邮箱注册/登录 |
| `wlbs . --pytest tests/` | 跑测试 + 自动记录 |
| `wlbs . --history` | 查看学习历史 |
| `wlbs . --suggest` | 修复建议 |
| `wlbs . --diff` | 曲率变化对比 |
| `wlbs . --blame src/foo.py` | 行级 git 归因 |
| `wlbs . --export-html report.html` | HTML 可视化报告 |
| `wlbs . --watch` | 文件变化监听 |
| `wlbs . --lang js` | 扫描 JS/TS |
| `wlbs . --ci` | CI 门控（奇点时 exit 1）|
| `wlbs . --dashboard` | 热力图 Web 界面 *(Pro)* |
| `wlbs . --status` | 查看账户积分 |

---

### 免费版 vs Pro

| 功能 | 免费版 | Pro（¥70/月）|
|---|---|---|
| 本地风险扫描 | ✅ | ✅ |
| 邮箱注册登录 | ✅ | ✅ |
| pytest 自动记录 | ✅ | ✅ |
| 奇点检测 | ✅ | ✅ |
| 修复建议 | 仅本地 | 云端增强 |
| 共享经验库 | ✗ | ✅ |
| 规则自动下载 | ✗ | ✅ |
| 热力图 Dashboard | ✗ | ✅ |
| 积分获取速率 | 0.3×/次 | 0.5×/次 |

**积分系统：** 每次上传轨迹自动得分，100分兑换一个 Pro key（30天），每年12月清零。

---

### 升级 Pro

**直接购买：** 联系 valhuang@kaiwucl.com 或微信 val001813，收款后立即发 key。

**积攒积分：** 持续用免费版上传，攒够100分自动兑换。

```bash
wlbs . --status  # 查看积分余额
```

---

### CI 集成

```yaml
- name: 风险门控
  run: wlbs . --ci --pytest tests/
```

---

### 原理

每个文件有曲率 κ ∈ [0, 1]，来自失败/修复历史和依赖图结构。测试失败时曲率沿 import 图传播（Aporia 反向传播：Δκ = α·λ^d），修复后衰减。**奇点**是多轮失败后曲率仍居高的节点——结构性脆弱。

完整理论：[PAPER.md](PAPER.md) | 专利：CN 2026103746505 · CN 2026103756225

---

### 许可证

BSL 1.1：非商业免费，商业需授权，2029-01-01 转 Apache 2.0。

---

### 联系作者

**黄中常 (Zhongchang Huang)**
邮箱：valhuang@kaiwucl.com | 微信：val001813
GitHub：[val1813/wlbs-cli](https://github.com/val1813/wlbs-cli)

