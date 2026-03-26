# wlbs-scan → Agent Learning Harness

## 实施方案 v2：CLI 优先 · 建议语气 · 测试随包发布

> \*\*三条修正原则（本版本对 v1 的核心调整）：\*\*
> 1. \*\*CLI 优先，MCP 可选\*\* — agent 集成的第一形态是纯 CLI 管道，不依赖 MCP 协议支持
> 2. \*\*建议语气，不命令式\*\* — wlbs 对主模型输出的是"我认为……你可以考虑……"，不是"必须先改这里"
> 3. \*\*测试随发布打包\*\* — 每个版本的 `tests/` + `validation/` 是发布产物的一部分，不是可选附件

\---

## 一、现状：已有什么，真正缺什么

```
已有（v0.5 现状）：
  ✓ 节点级持久记忆        .wlbs/world\_lines.json
  ✓ 曲率 + aporia 反向传播  κ 计算 + 上游信号传播
  ✓ 三层上下文装配器        --context（near/mid/far tier）
  ✓ 修复建议输出            --suggest / --suggest-node
  ✓ 测试自动接入            --pytest 自动回写 world-line
  ✓ 9/9 论文声明已验证      validation/VALIDATION\_RESULTS.md

真正缺的（按本方案补齐）：
  ✗ 任务级记忆              只记了节点事件，没记整件事怎么打的
  ✗ CLI 管道集成            现在还是人工跑命令，agent 无法自动消费
  ✗ 对主模型的建议输出      --suggest 的措辞偏命令式，模型会产生阻抗
  ✗ 策略学习闭环            记录了结果，但没有更新决策偏好的机制
  ✗ 测试随包发布            tests/ 在仓库里，但 pypi wheel 没有打包进去
```

\---

## 二、架构目标：CLI 管道模型

本方案不依赖 MCP 协议。集成方式是**标准 Unix 管道**，任何 agent 框架都能用：

```bash
# agent 在任务开始前调用：
wlbs-scan . --advise rbac --json > /tmp/wlbs\_advice.json

# agent 读取 JSON，决定先看哪里
# ... agent 工作 ...

# agent 完成后回写结果：
wlbs-scan . --record-outcome --task-id T001 --symptom rbac \\
            --final-target roles --result pass \\
            --tests-before 4/6 --tests-after 6/6

# 下次同类问题，系统已经更聪明了
```

**MCP 是未来可选项，不是现在的阻塞项。**
当 Claude Code / Cursor 的 MCP 支持稳定后，CLI → MCP 的迁移只需要包一层 server stub，核心逻辑不变。

\---

## 三、Phase 1 — Advisory CLI Output（建议级输出）

**目标：** 让输出变成 agent 可消费的建议，语气是"我认为"而非"必须"
**工期：** 3–5 天
**交付物：** 新 `--advise` 命令 + advisory JSON 格式 + `tests/test\_advisory.py`

\---

### 3.1 为什么要改语气

现在 `--suggest` 的输出是：

```
→ Route repair effort to upstream target: roles
→ Singularity: errors appear downstream but root cause is here.
```

这是命令式的。对于一个建议系统来说，有两个问题：

1. **主模型不一定采纳** — 如果模型有更多上下文，它可能知道 roles 不是真正的问题。命令式措辞会让它产生阻抗，或者产生不必要的"服从"。
2. **建议被拒绝后没有记录** — 如果模型选择了不同的路径，这个"分歧"本身是有价值的学习信号，现在丢失了。

建议语气的输出应该是：

```
"wlbs thinks: roles may be the root cause (confidence: 0.88)"
"Reason: singularity pattern — no direct failures on roles,
          but 3 downstream failures propagated from rbac"
"You might want to look at roles.py first."
"If you disagree, record your choice: wlbs-scan . --record-outcome ..."
```

这样模型有空间说"不"，而这个"不"被记录下来后，是 Phase 3 策略学习的输入。

\---

### 3.2 新命令：`--advise`

```bash
# 基本用法（终端彩色输出）
wlbs-scan . --advise rbac

# JSON 输出（给 agent 脚本消费）
wlbs-scan . --advise rbac --json

# 带置信度过滤（只输出置信度 > 0.7 的建议）
wlbs-scan . --advise rbac --min-confidence 0.7
```

**Advisory JSON 格式（schema: wlbs-advisory-v1）：**

```json
{
  "schema": "wlbs-advisory-v1",
  "generated\_at": "2026-03-26T09:00:00Z",
  "symptom": "rbac",
  "advisory": {
    "primary\_suggestion": {
      "text": "roles may be worth investigating first",
      "confidence": 0.88,
      "tone": "suggestion",
      "reasoning": \[
        "roles matches singularity definition: no direct failures, but downstream rbac has 3",
        "curvature lifted beyond static risk (0.405 → 0.905) via aporia backpropagation",
        "behavioral distance to symptom: 1 hop"
      ]
    },
    "alternative\_suggestions": \[
      {
        "text": "rbac itself may also have its own defects worth checking",
        "confidence": 0.62,
        "tone": "note",
        "reasoning": \["rbac has 3 direct failure events recorded"]
      }
    ],
    "what\_to\_read\_first": \["roles.py", "rbac.py"],
    "what\_might\_be\_safe\_to\_skip": \[],
    "open\_questions": \[
      "Is the failure pattern consistent across multiple test runs?",
      "Has roles.py been modified recently? (check --blame)"
    ],
    "similar\_past\_tasks": \[]
  },
  "metadata": {
    "nodes\_analyzed": 3,
    "world\_line\_events": 5,
    "scan\_ms": 28
  }
}
```

关键设计点：

* `tone: "suggestion"` 不是 `tone: "directive"`
* `open\_questions` 字段 — 让模型知道 wlbs 也有不确定的地方
* `alternative\_suggestions` — 不只给一个答案，给候选列表
* `similar\_past\_tasks` — Phase 3 之后填充，Phase 1 先留空

\---

### 3.3 `--suggest` 与 `--advise` 的关系

`--suggest` 保持兼容，行为不变（人类开发者用的）。
`--advise` 是新增的 agent 友好接口。

||`--suggest`|`--advise`|
|-|-|-|
|目标用户|人类开发者|agent / 脚本|
|语气|指导式|建议式|
|输出格式|终端彩色文本|JSON（可选彩色）|
|置信度|不显示|显式给出|
|备选方案|无|有|
|开放问题|无|有|

\---

### 3.4 在 Claude Code 里的接入方式

Claude Code 支持 bash 工具调用。不需要 MCP，直接在 system prompt 里加：

```
Before investigating a bug, run:
  wlbs-scan . --advise <symptom\_node> --json

Consider the suggestions in the output.
You don't have to follow them — if you choose a different path, note why,
and record your outcome with:
  wlbs-scan . --record-outcome --symptom <node> --final-target <your-choice> --result <pass|fail>
```

这就是 Phase 1 完成后的最小可用 agent 集成。一条 bash 命令，无依赖，当天可用。

\---

### 3.5 测试（随包发布）

新增 `tests/test\_advisory.py`，覆盖：

```python
def test\_advise\_output\_schema():
    """advisory JSON 必须包含 schema、tone、confidence 字段"""

def test\_advise\_tone\_is\_suggestion():
    """tone 字段必须是 'suggestion' 或 'note'，不能是 'directive'"""

def test\_advise\_confidence\_range():
    """confidence 必须在 \[0, 1] 之间"""

def test\_advise\_routes\_rbac\_to\_roles():
    """--advise rbac 的 primary\_suggestion.text 应包含 roles"""

def test\_advise\_includes\_open\_questions():
    """open\_questions 字段不能为 None"""

def test\_advise\_json\_parseable():
    """--advise --json 的输出必须能被 json.loads 解析"""
```

\---

## 四、Phase 2 — Task Memory（任务级记忆）

**目标：** 把"节点事件"升级为"任务轨迹"，这是策略学习的前提
**工期：** 5–7 天
**交付物：** `--record-outcome` 命令 + 扩展的 world\_lines.json schema + `tests/test\_task\_memory.py`

\---

### 4.1 新命令：`--record-outcome`

```bash
# 完整格式
wlbs-scan . --record-outcome \\
  --task-id      T20260326-001  \\
  --symptom      rbac           \\
  --final-target roles          \\
  --result       pass           \\
  --tests-before 4/6            \\
  --tests-after  6/6            \\
  --detail       "admin key missing in PERMISSIONS"

# 最简格式（task-id 自动生成，其他字段能推断的自动推断）
wlbs-scan . --record-outcome --symptom rbac --final-target roles --result pass

# 失败的任务也要记录（这才是真正的学习信号）
wlbs-scan . --record-outcome --symptom rbac --final-target rbac --result fail
```

**为什么失败的任务更重要：**
当 agent 按 wlbs 建议的方向去修，但修失败了——这是最有价值的学习信号。说明 wlbs 的建议在某些情况下是错的，策略权重需要更新。只记成功，系统只会越来越自信，但未必越来越准。

\---

### 4.2 扩展 Schema（向后兼容）

新字段加在 `world\_lines.json` 的顶层，不修改现有 `world\_lines` 结构：

```json
{
  "version": "0.6.0",
  "world\_lines": {
    "rbac": { "events": \[...] }
  },

  "task\_memory": {
    "T20260326-001": {
      "task\_id": "T20260326-001",
      "ts": "2026-03-26T09:00:00Z",
      "symptom": "rbac",
      "wlbs\_suggested\_target": "roles",
      "final\_target": "roles",
      "suggestion\_was\_followed": true,
      "result": "pass",
      "tests\_before": {"pass": 4, "fail": 2, "total": 6},
      "tests\_after":  {"pass": 6, "fail": 0, "total": 6},
      "detail": "admin key missing in PERMISSIONS",
      "symptom\_feature\_vector": \[0.59, 0.3, 0.6, 0.0, 0.2]
    }
  },

  "routing\_stats": {
    "total\_tasks": 1,
    "suggestion\_follow\_rate": 1.0,
    "suggestion\_accuracy": 1.0
  }
}
```

\---

### 4.3 `--history` 升级后的输出

```
wlbs-scan . --history

  World-line events: 5 (node-level)
  Task memory: 1 task recorded

  Recent tasks:
    T20260326-001  rbac → roles   PASS  +2 tests
                   wlbs suggestion: roles  (followed ✓)

  Routing accuracy:  1/1 (100%)
  Follow rate:       1/1 (100%)
  Avg test improvement: +2.0 per task
```

\---

### 4.4 测试（随包发布）

新增 `tests/test\_task\_memory.py`：

```python
def test\_record\_outcome\_writes\_task\_memory():
    """--record-outcome 后 world\_lines.json 包含 task\_memory 字段"""

def test\_task\_memory\_schema\_complete():
    """task 记录包含所有必要字段"""

def test\_suggestion\_was\_followed\_detection():
    """当 wlbs\_suggested\_target == final\_target 时，suggestion\_was\_followed = True"""

def test\_routing\_stats\_update():
    """每次 record-outcome 后 routing\_stats 正确更新"""

def test\_task\_id\_auto\_generated():
    """不传 --task-id 时自动生成唯一 ID"""

def test\_backward\_compatible\_no\_task\_memory():
    """没有 task\_memory 字段的旧 world\_lines.json 能正常加载"""
```

\---

## 五、Phase 3 — Policy Learning（策略学习）

**目标：** 让建议随任务结果自动变准，实现"不是死记硬背"的技术承诺
**工期：** 7–10 天
**交付物：** `RoutingPolicy` 类 + 相似任务匹配器 + `tests/test\_policy.py`

\---

### 5.1 策略更新：指数移动平均

不用梯度下降，用 EMA。原因：任务数量小（几十条），神经网络会过拟合，EMA 简单、可解释、可逆。

```python
OUTCOME\_REWARD = {
    "pass\_followed":  +1.0,   # 建议被采纳且成功 → 强化
    "pass\_ignored":   -0.2,   # 建议被忽略但成功 → 轻微惩罚（建议可能多余）
    "fail\_followed":  -1.0,   # 建议被采纳但失败 → 强烈惩罚（建议是错的）
    "fail\_ignored":    0.0,   # 建议被忽略且失败 → 中性（信息不足）
}

def update\_routing\_confidence(current: float, outcome: str, alpha=0.3) -> float:
    reward = OUTCOME\_REWARD\[outcome]
    return max(0.0, min(1.0, current \* (1 - alpha) + reward \* alpha))
```

\---

### 5.2 相似任务匹配（跨任务泛化的关键）

新问题借用旧经验，靠**结构特征向量**，不靠节点名字：

```python
def node\_feature\_vector(node, graph) -> list\[float]:
    """5 维特征，全归一化到 \[0, 1]"""
    return \[
        node.static\_curvature,
        min(node.failure\_count / 10, 1.0),
        min(\_downstream\_failure\_count(graph, node.id) / 5, 1.0),
        1.0 if node.id in {s.id for s in find\_singularities(graph)} else 0.0,
        min(node.is\_imported\_by\_count / 5, 1.0),
    ]

def cosine\_sim(a: list, b: list) -> float:
    dot   = sum(x \* y for x, y in zip(a, b))
    norm  = lambda v: sum(x\*\*2 for x in v) \*\* 0.5
    return dot / (norm(a) \* norm(b) + 1e-9)

def find\_similar\_past\_tasks(symptom, graph, task\_memory) -> list:
    current\_vec = node\_feature\_vector(graph.nodes\[symptom], graph)
    candidates = \[]
    for task in task\_memory.values():
        hist\_vec = task.get("symptom\_feature\_vector")
        if hist\_vec and cosine\_sim(current\_vec, hist\_vec) > 0.75:
            candidates.append({
                "task\_id":     task\["task\_id"],
                "similarity":  round(cosine\_sim(current\_vec, hist\_vec), 3),
                "symptom":     task\["symptom"],
                "final\_target": task\["final\_target"],
                "result":      task\["result"],
                "detail":      task.get("detail", ""),
            })
    return sorted(candidates, key=lambda x: x\["similarity"], reverse=True)\[:3]
```

**核心价值：** `payment\_handler` 出问题，历史上 `rbac` 结构特征相似（都是"下游节点 + 上游 singularity + 3 次未修复失败"），系统把 `rbac` 那次的修复经验迁移过来。

匹配的是**结构**，不是**名字**。这就是"不是死记硬背"的技术实现。

\---

### 5.3 `--advise` 升级后的输出（Phase 3 完成后）

```json
{
  "advisory": {
    "primary\_suggestion": {
      "text": "roles may be worth investigating first",
      "confidence": 0.91,
      "tone": "suggestion"
    },
    "similar\_past\_tasks": \[
      {
        "similarity": 0.89,
        "symptom": "payment\_handler",
        "final\_target": "permission\_registry",
        "result": "pass",
        "detail": "missing key in registry — structurally similar to current issue"
      }
    ]
  }
}
```

模型看到这个，会知道："上次结构相似的问题，最终是在注册表里加了缺失的 key 解决的。"
这是建议，不是指令。模型可以参考，也可以忽略，忽略了就回写。

\---

### 5.4 测试（随包发布）

新增 `tests/test\_policy.py`：

```python
def test\_routing\_confidence\_increases\_on\_pass\_followed():
    """pass\_followed 后 confidence 提升"""

def test\_routing\_confidence\_decreases\_on\_fail\_followed():
    """fail\_followed 后 confidence 下降，且降幅大于 pass\_followed 升幅"""

def test\_cosine\_sim\_identical\_vectors():
    """相同向量的余弦相似度 = 1.0"""

def test\_similar\_task\_matching\_by\_structure\_not\_name():
    """结构相似但名字不同的节点能被匹配到"""

def test\_dissimilar\_task\_not\_matched():
    """结构差异大的任务不出现在相似结果里"""

def test\_similar\_tasks\_appear\_in\_advise\_json():
    """有历史任务时，--advise --json 的 similar\_past\_tasks 不为空"""
```

\---

## 六、Phase 4 — Test Bundling（测试随包发布）

**目标：** 每次发布，tests/ 和 validation/ 是产物的一部分，用户能直接验证
**工期：** 2–3 天
**交付物：** 修改后的 `pyproject.toml` + `python -m wlbs\_scan.validate` 命令 + Release Checklist

\---

### 6.1 为什么测试必须随包发布

**现状问题：**
`tests/` 和 `validation/` 在 GitHub 仓库里，但 `pip install wlbs-scan` 安装的 wheel 里没有这些文件。用户无法验证"9/9 claims validated"在他们的环境里也成立。

**后果：**

* 用户只能相信 README 里的数据，不能自己复现
* 论文审稿人会质疑可重现性
* "9/9 validated"的徽章显得是 marketing 而非 evidence

**修正后的期望：**

```bash
pip install wlbs-scan
python -m wlbs\_scan.validate
# → VALIDATION RESULTS: 9/9 PASS
```

\---

### 6.2 `pyproject.toml` 修改

```toml
\[tool.setuptools.package-data]
"\*" = \[
    "tests/\*.py",
    "validation/\*.py",
    "validation/\*.md",
    "demo/\*\*/\*.py",
    "demo/tests/\*.py",
]
```

同时在 `MANIFEST.in` 确保源码包包含测试：

```
include tests/\*.py
include validation/\*.py
include validation/\*.md
recursive-include demo \*.py
```

\---

### 6.3 `python -m wlbs\_scan.validate` 命令

```bash
python -m wlbs\_scan.validate          # 跑全部 9 个 claim（默认）
python -m wlbs\_scan.validate --quick  # 只跑 claim 1-3，< 5 秒，适合初装验证
python -m wlbs\_scan.validate --json   # 机器可读输出
```

**终端输出示例：**

```
wlbs-scan v0.6.0 — Self-Validation
====================================
Python 3.12.9 on linux

Running 9 validation claims...

  ✓ Claim 1   Core scan latency < 50ms       \[avg=28ms]
  ✓ Claim 1b  Scaling to 60 files            \[avg=40ms]
  ✓ Claim 2   Behavioral distance = 1 hop    \[d=1]
  ✓ Claim 3   Upstream singularity detection \[roles κ=1.000]
  ✓ Claim 4   κ monotone accumulation        \[0.087 → 0.423]
  ✓ Claim 5   --pytest auto-record           \[4 pass, 2 fail]
  ✓ Claim 6   JS/TS import graph             \[d=1]
  ✓ Claim 7   HTML export                    \[10621 bytes]
  ✓ Claim 8   Demo defect reproducible       \[2 fail, 4 pass]

RESULT: 9/9 PASS  (took 1.23s)

Reproduce anytime: python -m wlbs\_scan.validate
```

\---

### 6.4 Release Checklist（写入 CONTRIBUTING.md）

每次发版前必须通过以下全部检查：

```markdown
## Release Checklist（每次发版必须全过）

### 核心测试
- \[ ] `pytest tests/ -v`                     → 全部 PASS
- \[ ] `python -m wlbs\_scan.validate`          → 9/9 PASS
- \[ ] `python -m wlbs\_scan.validate --json`   → JSON 格式正确

### 新功能测试
- \[ ] `wlbs-scan . --advise <node> --json`    → schema 字段完整，tone = suggestion
- \[ ] `wlbs-scan . --record-outcome ...`      → task\_memory 字段正确写入
- \[ ] `wlbs-scan . --history`                 → 显示任务记录

### 打包验证
- \[ ] `pip install dist/wlbs\_scan-X.Y.Z-py3-none-any.whl`（干净虚拟环境）
- \[ ] 安装后 `python -m wlbs\_scan.validate` 能跑通（tests 在 wheel 里）
- \[ ] `pip show -f wlbs-scan | grep tests`    → 能看到 tests 文件

### 文档同步
- \[ ] `validation/VALIDATION\_RESULTS.md` 更新为最新实测数据
- \[ ] `CHANGELOG.md` 写好本版新增
- \[ ] README 徽章数据与实测数据吻合
- \[ ] `--advise` 命令在 README 命令一览表里有记录
```

\---

## 七、整体时间线

```
Week 1        Phase 1: Advisory CLI Output
              ✓ --advise 命令上线
              ✓ advisory JSON schema 确定（wlbs-advisory-v1）
              ✓ tests/test\_advisory.py（6 个测试，随包）
              → 结果：Claude Code 可用一行命令接入 wlbs 建议，
                      语气是"你可以考虑"，不是"必须"

Week 2        Phase 2: Task Memory
              ✓ --record-outcome 命令上线
              ✓ world\_lines.json schema 扩展（向后兼容）
              ✓ --history 显示任务记录 + routing\_stats
              ✓ tests/test\_task\_memory.py（6 个测试，随包）
              → 结果：任务轨迹开始积累，学习闭环基础就位

Week 3–4      Phase 3: Policy Learning
              ✓ RoutingPolicy 指数更新（alpha=0.3 EMA）
              ✓ 结构特征余弦相似度匹配器
              ✓ similar\_past\_tasks 填充进 --advise JSON
              ✓ tests/test\_policy.py（6 个测试，随包）
              → 结果：第 5 次同类任务，建议比第 1 次更准；
                      跨节点泛化而非死记名字

Week 5        Phase 4: Test Bundling
              ✓ pyproject.toml + MANIFEST.in 修改
              ✓ python -m wlbs\_scan.validate 命令
              ✓ Release Checklist 写入 CONTRIBUTING.md
              → 结果：pip install 后用户能自己验证 9/9

v0.6 发布     上述全部，validation/VALIDATION\_RESULTS.md 同步更新
```

\---

## 八、MVP：最短路径到可演示状态

**只做 Phase 1（`--advise` 命令），就可以演示核心交互。**

```bash
# 演示脚本（30 秒内可展示给任何人）
cd your\_project
wlbs-scan . --pytest tests/          # 跑测试，写入记忆
wlbs-scan . --advise rbac --json     # 输出结构化建议
```

输出：

```json
{
  "advisory": {
    "primary\_suggestion": {
      "text": "roles may be worth investigating first",
      "confidence": 0.88,
      "tone": "suggestion",
      "reasoning": \["singularity pattern", "κ lift via aporia backpropagation"]
    },
    "open\_questions": \[
      "Has roles.py been modified recently?"
    ]
  }
}
```

这个演示清晰展示了：

* wlbs 对主模型**提建议**，不发命令
* 建议有**置信度**，有**推理链**，有**开放问题**
* 全部通过 CLI，无需 MCP，无需配置

\---

## 九、关于 MCP 的定位

**现阶段：CLI → JSON 管道**（今天可用，零依赖）

**未来 v0.7+：CLI + MCP server stub（可选）**

```python
# wlbs\_mcp\_server.py（未来，约 80 行）
# 把 get\_advise() / record\_outcome() 包成 MCP tool
# 核心逻辑还是调 wlbs\_scan.py，不重新实现
# 当 Claude Code / Cursor MCP 生态稳定后上线
```

迁移成本极低，因为 Phase 1-3 的接口设计已经为这个封装准备好了。
MCP 只是 CLI 接口的一个包装层，不是重新实现。

\---

## 十、一句话总结

|Phase|做什么|完成后能展示什么|测试文件（随包）|
|-|-|-|-|
|1|`--advise` + advisory JSON|"wlbs 对主模型提建议，语气是建议不是命令"|`test\_advisory.py`|
|2|`--record-outcome` + task memory|"系统记住了整件事怎么打的"|`test\_task\_memory.py`|
|3|EMA 策略更新 + 结构相似度匹配|"越跑越准，靠结构泛化不靠死记名字"|`test\_policy.py`|
|4|tests 进 wheel + validate 命令|"用户自己可以验证，不只是信 README"|`wlbs\_scan/validate.py`|

\---

> 文档版本：v2.0 · 2026-03-26
> 对应代码版本：wlbs-scan v0.5（方案针对 v0.6 实施）
> 核心修正：CLI 优先 · 建议语气 · 测试随包发布









补充：

**wlbs-scan IDE 全面兼容** 





1\. 新建 .vscode/extensions.json

告诉 VSCode 推荐安装哪些插件（打开项目时自动弹出提示）。

json{

&#x20; "recommendations": \[

&#x20;   "ms-python.python",

&#x20;   "ms-python.pylint",

&#x20;   "ms-python.black-formatter",

&#x20;   "tamasfe.even-better-toml",

&#x20;   "ms-vscode.test-adapter-converter"

&#x20; ]

}



2\. 新建 .vscode/settings.json

VSCode 打开项目后自动生效的设置。

json{

&#x20; "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",

&#x20; "python.testing.pytestEnabled": true,

&#x20; "python.testing.pytestArgs": \["tests"],

&#x20; "python.testing.unittestEnabled": false,

&#x20; "python.testing.autoTestDiscoverOnSaveEnabled": true,

&#x20; "editor.formatOnSave": true,

&#x20; "\[python]": {

&#x20;   "editor.defaultFormatter": "ms-python.black-formatter"

&#x20; },

&#x20; "python.analysis.extraPaths": \["${workspaceFolder}"],

&#x20; "files.exclude": {

&#x20;   "\*\*/\_\_pycache\_\_": true,

&#x20;   "\*\*/\*.pyc": true,

&#x20;   "\*\*/.wlbs": false,

&#x20;   "\*\*/dist": true,

&#x20;   "\*\*/\*.egg-info": true

&#x20; },

&#x20; "search.exclude": {

&#x20;   "\*\*/\_\_pycache\_\_": true,

&#x20;   "\*\*/dist": true,

&#x20;   "\*\*/\*.egg-info": true

&#x20; }

}

注意 .wlbs 设为 false（不排除），方便在 VSCode 里直接查看 world\_lines.json。



3\. 新建 .vscode/launch.json

在 VSCode 里按 F5 直接调试 wlbs-scan，不用命令行。

json{

&#x20; "version": "0.2.0",

&#x20; "configurations": \[

&#x20;   {

&#x20;     "name": "wlbs-scan: scan current project",

&#x20;     "type": "debugpy",

&#x20;     "request": "launch",

&#x20;     "module": "wlbs\_scan",

&#x20;     "args": \["."],

&#x20;     "cwd": "${workspaceFolder}",

&#x20;     "console": "integratedTerminal"

&#x20;   },

&#x20;   {

&#x20;     "name": "wlbs-scan: suggest (focus node)",

&#x20;     "type": "debugpy",

&#x20;     "request": "launch",

&#x20;     "module": "wlbs\_scan",

&#x20;     "args": \[".", "--suggest"],

&#x20;     "cwd": "${workspaceFolder}",

&#x20;     "console": "integratedTerminal"

&#x20;   },

&#x20;   {

&#x20;     "name": "wlbs-scan: run pytest + record",

&#x20;     "type": "debugpy",

&#x20;     "request": "launch",

&#x20;     "module": "wlbs\_scan",

&#x20;     "args": \[".", "--pytest", "tests/"],

&#x20;     "cwd": "${workspaceFolder}",

&#x20;     "console": "integratedTerminal"

&#x20;   },

&#x20;   {

&#x20;     "name": "wlbs-scan: context (node=rbac)",

&#x20;     "type": "debugpy",

&#x20;     "request": "launch",

&#x20;     "module": "wlbs\_scan",

&#x20;     "args": \[".", "--context", "rbac"],

&#x20;     "cwd": "${workspaceFolder}",

&#x20;     "console": "integratedTerminal"

&#x20;   },

&#x20;   {

&#x20;     "name": "wlbs-scan: export HTML report",

&#x20;     "type": "debugpy",

&#x20;     "request": "launch",

&#x20;     "module": "wlbs\_scan",

&#x20;     "args": \[".", "--export-html", "report.html"],

&#x20;     "cwd": "${workspaceFolder}",

&#x20;     "console": "integratedTerminal"

&#x20;   },

&#x20;   {

&#x20;     "name": "wlbs-scan: JSON output (pipe-friendly)",

&#x20;     "type": "debugpy",

&#x20;     "request": "launch",

&#x20;     "module": "wlbs\_scan",

&#x20;     "args": \[".", "--json"],

&#x20;     "cwd": "${workspaceFolder}",

&#x20;     "console": "integratedTerminal"

&#x20;   },

&#x20;   {

&#x20;     "name": "Run all tests (pytest)",

&#x20;     "type": "debugpy",

&#x20;     "request": "launch",

&#x20;     "module": "pytest",

&#x20;     "args": \["tests/", "-v"],

&#x20;     "cwd": "${workspaceFolder}",

&#x20;     "console": "integratedTerminal"

&#x20;   },

&#x20;   {

&#x20;     "name": "Run validation suite",

&#x20;     "type": "debugpy",

&#x20;     "request": "launch",

&#x20;     "program": "${workspaceFolder}/validation/run\_validation.py",

&#x20;     "cwd": "${workspaceFolder}",

&#x20;     "console": "integratedTerminal"

&#x20;   }

&#x20; ]

}



4\. 新建 .vscode/tasks.json

Ctrl+Shift+B 可以直接运行常用任务，不用记命令。

json{

&#x20; "version": "2.0.0",

&#x20; "tasks": \[

&#x20;   {

&#x20;     "label": "wlbs: scan project",

&#x20;     "type": "shell",

&#x20;     "command": "python wlbs\_scan.py .",

&#x20;     "group": "build",

&#x20;     "presentation": {

&#x20;       "reveal": "always",

&#x20;       "panel": "shared"

&#x20;     },

&#x20;     "problemMatcher": \[]

&#x20;   },

&#x20;   {

&#x20;     "label": "wlbs: pytest + record",

&#x20;     "type": "shell",

&#x20;     "command": "python wlbs\_scan.py . --pytest tests/",

&#x20;     "group": "test",

&#x20;     "presentation": {

&#x20;       "reveal": "always",

&#x20;       "panel": "shared"

&#x20;     },

&#x20;     "problemMatcher": \[]

&#x20;   },

&#x20;   {

&#x20;     "label": "wlbs: suggest fixes",

&#x20;     "type": "shell",

&#x20;     "command": "python wlbs\_scan.py . --suggest",

&#x20;     "group": "build",

&#x20;     "presentation": {

&#x20;       "reveal": "always",

&#x20;       "panel": "shared"

&#x20;     },

&#x20;     "problemMatcher": \[]

&#x20;   },

&#x20;   {

&#x20;     "label": "wlbs: show history",

&#x20;     "type": "shell",

&#x20;     "command": "python wlbs\_scan.py . --history",

&#x20;     "group": "build",

&#x20;     "presentation": {

&#x20;       "reveal": "always",

&#x20;       "panel": "shared"

&#x20;     },

&#x20;     "problemMatcher": \[]

&#x20;   },

&#x20;   {

&#x20;     "label": "wlbs: export HTML report",

&#x20;     "type": "shell",

&#x20;     "command": "python wlbs\_scan.py . --export-html report.html \&\& echo 'Report: report.html'",

&#x20;     "group": "build",

&#x20;     "presentation": {

&#x20;       "reveal": "always",

&#x20;       "panel": "shared"

&#x20;     },

&#x20;     "problemMatcher": \[]

&#x20;   },

&#x20;   {

&#x20;     "label": "wlbs: run validation suite",

&#x20;     "type": "shell",

&#x20;     "command": "python validation/run\_validation.py",

&#x20;     "group": "test",

&#x20;     "presentation": {

&#x20;       "reveal": "always",

&#x20;       "panel": "shared"

&#x20;     },

&#x20;     "problemMatcher": \[]

&#x20;   },

&#x20;   {

&#x20;     "label": "pytest: run all tests",

&#x20;     "type": "shell",

&#x20;     "command": "python -m pytest tests/ -v",

&#x20;     "group": {

&#x20;       "kind": "test",

&#x20;       "isDefault": true

&#x20;     },

&#x20;     "presentation": {

&#x20;       "reveal": "always",

&#x20;       "panel": "shared"

&#x20;     },

&#x20;     "problemMatcher": \[]

&#x20;   }

&#x20; ]

}



5\. 修改 pyproject.toml

在现有内容末尾追加以下内容（不改现有字段）：

toml\[tool.pytest.ini\_options]

testpaths = \["tests"]

python\_files = \["test\_\*.py"]

python\_functions = \["test\_\*"]

addopts = "-v --tb=short"



\[tool.black]

line-length = 100

target-version = \["py38", "py39", "py310", "py311", "py312"]



\[tool.pylint.main]

disable = \["C0114", "C0115", "C0116", "R0903", "W0212"]

max-line-length = 100



\[tool.mypy]

python\_version = "3.8"

ignore\_missing\_imports = true

warn\_unused\_configs = true



6\. 新建 pyrightconfig.json（根目录）

Pylance（VSCode 默认 Python 语言服务器）的配置，让代码补全和类型检查正常工作。

json{

&#x20; "pythonVersion": "3.8",

&#x20; "pythonPlatform": "All",

&#x20; "typeCheckingMode": "basic",

&#x20; "include": \[

&#x20;   "wlbs\_scan.py",

&#x20;   "tests",

&#x20;   "validation",

&#x20;   "demo"

&#x20; ],

&#x20; "exclude": \[

&#x20;   "\*\*/\_\_pycache\_\_",

&#x20;   "dist",

&#x20;   "\*.egg-info"

&#x20; ],

&#x20; "reportMissingImports": "warning",

&#x20; "reportMissingModuleSource": "none"

}



7\. 修改 .gitignore

在现有内容末尾追加（现有内容不动）：

\# IDE

.vscode/

!.vscode/extensions.json

!.vscode/settings.json

!.vscode/launch.json

!.vscode/tasks.json

.idea/

\*.iml



\# Type checking

.mypy\_cache/

pyrightconfig.json



\# Virtual env

.venv/

venv/

env/

注意：.vscode/ 整体 gitignore，但用 ! 把四个配置文件强制保留进仓库，这样其他贡献者 clone 后 VSCode 直接可用。



8\. 新建 .editorconfig（根目录）

让所有 IDE（VSCode、Cursor、JetBrains）的缩进/编码设置统一。

iniroot = true



\[\*]

charset = utf-8

end\_of\_line = lf

insert\_final\_newline = true

trim\_trailing\_whitespace = true



\[\*.py]

indent\_style = space

indent\_size = 4



\[\*.{json,toml,yaml,yml}]

indent\_style = space

indent\_size = 2



\[\*.md]

trim\_trailing\_whitespace = false



文件清单（需要新建/修改的）

操作文件新建目录 + 文件.vscode/extensions.json新建.vscode/settings.json新建.vscode/launch.json新建.vscode/tasks.json新建pyrightconfig.json新建.editorconfig追加末尾pyproject.toml追加末尾.gitignore

现有代码 wlbs\_scan.py 一行不动。



完成后 VSCode 里能做的事

操作方式扫描项目看风险图F5 → 选 "wlbs-scan: scan current project"跑测试并写入世界线Ctrl+Shift+B → 选 "wlbs: pytest + record"看修复建议F5 → 选 "wlbs-scan: suggest fixes"跑全部单元测试Ctrl+Shift+P → "Run Test Task"在测试面板里点单个测试左侧烧杯图标 → tests/ 下每个用例旁边有绿色播放键断点调试 wlbs\_scan.py任意行设断点 → F5导出 HTML 报告Task: "wlbs: export HTML report"跑 validation suiteTask: "wlbs: run validation suite"

