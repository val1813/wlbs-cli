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

It builds a live risk map from your actual failure history, not generic heuristics. Run one command, see exactly which files are hot. The more you use it, the more accurate it gets. Pro users also draw from a shared experience pool: patterns distilled from real bug-fix sessions across the entire community.

**Key capabilities:**

- Instant risk map with curvature scores per file
- Auto-records every `pytest` run — zero manual steps
- Learns from failures *and* fixes (negative + positive signal)
- Singularity detection: flags files that keep breaking structurally
- Pro: shared experience library, updated in real time
- Pro: LLM-guided fix suggestions with reasoning chain
- Python and JS/TS support
- Zero extra runtime dependencies (stdlib only)

---

### Evidence — live server, March 2026

End-to-end flow verified on `111.231.112.127:8765`:

```
$ curl http://111.231.112.127:8765/health
{"status":"ok","total_crystals":1,"port":8765}

$ curl http://111.231.112.127:8765/stats
{"active_keys":2,"shared_crystals":1,"version":"0.6.0"}

# Upload a trace → system awards points + distils a reusable rule:
{"accepted":true,"rule_generated":true,"points_earned":0.4}

# Pro key pulls the rule back immediately:
{"crystals":[{"rule":"bug_fix (python): resolved in 3 turns.",
              "confidence":1.0,"contributed_at":"2026-03-26T08:01:21Z"}]}
```

Full install-to-scan-to-rule cycle runs in under 60 seconds on any Python 3.8+ machine.

---

### Install

```bash
pip install wlbs-scan
```

No C extensions. No native deps. Works offline for local scan.

---

### Quick start (free, no account needed)

```bash
# See which files are most likely to break
wlbs-scan .

# Run your tests — all results recorded automatically
wlbs-scan . --pytest tests/

# See what the system has learned
wlbs-scan . --history

# Get fix recommendations for high-risk files
wlbs-scan . --suggest
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

A **singularity** (κ ≥ 0.7, repeated failures) is the system telling you: *this file keeps breaking for structural reasons — fix it now, not after the next incident.*

---

### Command reference

| Command | What it does |
|---|---|
| `wlbs-scan .` | Scan + print risk map |
| `wlbs-scan . --pytest tests/` | Run pytest + auto-record all results |
| `wlbs-scan . --history` | Show what the system has learned |
| `wlbs-scan . --suggest` | Fix recommendations for hot files |
| `wlbs-scan . --diff` | Curvature delta since last scan |
| `wlbs-scan . --blame src/foo.py` | Line-level git attribution for risky files |
| `wlbs-scan . --export-html report.html` | Visual HTML risk report |
| `wlbs-scan . --watch` | Re-scan on every file save |
| `wlbs-scan . --lang js` | Scan JS/TS codebase |
| `wlbs-scan . --ci` | Exit 1 if singularity detected (for CI gates) |
| `wlbs-scan . --context src/rbac.py` | Resolution-decay context assembly |
| `wlbs-scan . --dashboard` | Open heatmap web UI *(Pro)* |

---

### Free vs Pro

| Feature | Free | Pro ($9.9/mo) |
|---|---|---|
| Local risk scan | ✅ | ✅ |
| Auto-record pytest results | ✅ | ✅ |
| Local world-line history | ✅ | ✅ |
| Singularity detection | ✅ | ✅ |
| Fix suggestions (`--suggest`) | Local only | Cloud-enhanced |
| Shared experience library | ✗ | ✅ unlimited* |
| Automatic rule downloads | ✗ | ✅ after each session |
| Dashboard (`--dashboard`) | ✗ | ✅ |
| Points earn rate | 0.3× / upload | 0.5× / upload |

*Rate-limited to protect server stability.

**Pro pays for itself** the first time it surfaces a pattern from another codebase that saves you an hour of debugging.

---

### Get a Pro key

**Option 1 — Buy directly:**
Contact **valhuang@kaiwucl.com** or WeChat **val001813**.
You receive an API key immediately. Valid for 30 days from first use.

**Option 2 — Earn through contributions:**
Every trace you upload earns points. 100 points = 1 free Pro key.
Free users earn at 0.3× per upload; Pro users at 0.5×.

```bash
# Check your balance
wlbs-scan . --api-key <your-key> --status
```

---

### Activate your key

```bash
# Store once — saved to ~/.wlbs/config.json
wlbs-scan --set-key wlbs_pro_xxxxxxxxxxxxxxxxxxxx

# Or pass per-command
wlbs-scan . --api-key wlbs_pro_xxxxxxxxxxxxxxxxxxxx

# Or via env var
export WLBS_API_KEY=wlbs_pro_xxxxxxxxxxxxxxxxxxxx
```

---

### pytest plugin (optional)

If you run `pytest` directly without `wlbs-scan . --pytest`:

```python
# conftest.py
pytest_plugins = ['wlbs_scan.wlbs_pytest_plugin']
```

```bash
pytest tests/ --wlbs .
```

Results are silently recorded locally. Nothing is uploaded without a Pro key.

---

### CI / pre-commit

```yaml
# .github/workflows/ci.yml
- name: Risk gate
  run: wlbs-scan . --ci --pytest tests/
  # Exits 1 if a singularity is detected
```

```bash
# .git/hooks/pre-commit
wlbs-scan . --ci
```

---

### Self-validate

```bash
python -m wlbs_scan.validate
```

Runs 15 paper claims against live code. All 15 pass on a clean install.

---

### How it works (short version)

Every file gets a **curvature** κ ∈ [0, 1] derived from its failure/fix history and import-graph position. When a test fails, curvature propagates upstream through the dependency tree. When you fix it, curvature decays. A **singularity** is a node where curvature has stayed high across multiple failure cycles — structural fragility, not random noise.

Full theory: [PAPER.md](PAPER.md) | Patent: CN 2026103746505 · CN 2026103756225

---

### License

BSL 1.1 — free for non-commercial use, research, and internal evaluation.
Commercial use in products or services requires a license from the author.
Auto-converts to Apache 2.0 on 2029-01-01.

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

它根据你真实的失败历史建立风险图，不靠泛化规则。用得越多，越准。Pro 用户还能从社区共享的经验库里受益：来自数千个真实 bug 修复会话提炼出的规律，实时更新。

---

### 效果证明 — 2026年3月实测

```bash
# 健康检查（服务器实时运行）
curl http://111.231.112.127:8765/health
# → {"status":"ok","total_crystals":1,"port":8765}

# 上传轨迹 → 服务端自动提炼规则并发放积分
# → {"accepted":true,"rule_generated":true,"points_earned":0.4}

# Pro 用户立刻拿到这条规则
# → {"rule":"bug_fix (python): resolved in 3 turns.","confidence":1.0}
```

从安装到跑通完整流程不到 60 秒。

---

### 安装

```bash
pip install wlbs-scan
```

无任何额外依赖，纯 Python 3.8+，离线扫描完全可用。

---

### 快速开始（免费，无需账号）

```bash
# 扫描项目，看风险图
wlbs-scan .

# 跑测试，失败自动记录，零手动操作
wlbs-scan . --pytest tests/

# 查看系统学到了什么
wlbs-scan . --history

# 获取高风险文件的修复建议
wlbs-scan . --suggest
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

**奇点**（κ ≥ 0.7，反复失败）= 系统在告诉你：这个文件有结构性问题，不是随机 bug，现在就修。

---

### 免费版 vs Pro 版

| 功能 | 免费版 | Pro（¥70/月 或 $9.9/月）|
|---|---|---|
| 本地风险扫描 | ✅ | ✅ |
| pytest 自动记录 | ✅ | ✅ |
| 本地世界线历史 | ✅ | ✅ |
| 奇点检测 | ✅ | ✅ |
| 修复建议（--suggest） | 仅本地 | 云端增强 |
| 共享经验库 | ✗ | ✅ 不限量* |
| 规则自动下载 | ✗ | ✅ 每次会话后 |
| 热力图 Dashboard | ✗ | ✅ |
| 积分获取速率 | 0.3×/次 | 0.5×/次 |

*有频率限制保护服务器稳定。

---

### 获取 Pro Key

**方式一 — 直接购买：**
联系 **valhuang@kaiwucl.com** 或微信 **val001813**，收款后立即发 key。
Key 从首次使用起算 30 天有效。

**方式二 — 贡献积分换取：**
每次上传轨迹自动得分。积满 100 分可兑换一个免费 Pro key。
免费用户 0.3×/次，Pro 用户 0.5×/次（约 1.7 个月攒够）。

```bash
# 查询积分余额
wlbs-scan . --api-key <你的key> --status
```

---

### 激活 Key

```bash
# 存储一次，写入 ~/.wlbs/config.json
wlbs-scan --set-key wlbs_pro_xxxxxxxxxxxxxxxxxxxx

# 或每次传入
wlbs-scan . --api-key wlbs_pro_xxxxxxxxxxxxxxxxxxxx

# 或环境变量
export WLBS_API_KEY=wlbs_pro_xxxxxxxxxxxxxxxxxxxx
```

---

### CI / pre-commit 集成

```yaml
# .github/workflows/ci.yml
- name: 风险门控
  run: wlbs-scan . --ci --pytest tests/
  # 检测到奇点时 exit 1
```

---

### 原理（一段话）

每个文件有一个**曲率** κ ∈ [0, 1]，来自真实失败/修复历史和依赖图结构。测试失败时，曲率沿 import 图向上传播（Aporia 反向传播：Δκ = α·λ^d）。修复后曲率衰减。**奇点**是曲率在多轮失败周期后仍居高不下的节点 —— 结构性脆弱，不是随机噪声。

完整理论：[PAPER.md](PAPER.md) | 专利：CN 2026103746505 · CN 2026103756225

---

### 许可证

BSL 1.1：非商业用途、科研、内部评估免费。
面向第三方的商业产品/服务需向作者申请授权。
2029-01-01 自动转为 Apache 2.0。

---

### 联系作者

**黄中常 (Zhongchang Huang)**
邮箱：valhuang@kaiwucl.com | 微信：val001813
GitHub：[val1813/wlbs-cli](https://github.com/val1813/wlbs-cli)



