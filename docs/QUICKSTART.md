# wlbs-scan 新手教程

> 版本 v0.6.3 · 适用于 Python 项目

---

## 安装

```bash
pip install wlbs-scan
```

安装后有两个等价的命令入口：`wlbs` 和 `wlbs-scan`，以下统一用 `wlbs`。

---

## 第一步：注册 + 配置（只需做一次）

```bash
cd 你的项目根目录
wlbs begin
```

`wlbs begin` 会依次完成两件事：

**1. 注册账号（必须）**

```
wlbs begin — onboarding
Step 1/2  Register
Email: you@example.com
Sending verification code to you@example.com...
Code sent! Check your inbox.
Verification code: xxxxxx
Account created! Signed in as you@example.com (tier: free)
Credentials saved to C:\Users\你的用户名\.wlbs\config.json
```

- 无需密码，邮箱 + 验证码即可
- 凭据保存在 `~/.wlbs/config.json`，后续无需重复登录

**2. 自动配置 pytest 插件**

脚本会按优先级检测以下文件，自动写入 `--wlbs` 参数：

| 检测顺序 | 文件 | 写入内容 |
|---|---|---|
| 1 | `pyproject.toml` | `[tool.pytest.ini_options] addopts = ['--wlbs']` |
| 2 | `setup.cfg` | `[tool:pytest] addopts = --wlbs` |
| 3 | `pytest.ini` | `addopts = --wlbs` |
| 4 | `conftest.py` | 追加注释行 |

配置后，每次 `pytest` 运行都会自动上报结果，wlbs 越用越准。

---

## 第二步：扫描项目，找问题文件

```bash
wlbs bug
```

等价于：`wlbs-scan .`（扫描当前目录）

也可以指定路径：

```bash
wlbs bug src/
```

**输出示例：**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  wlbs-scan v0.6.3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Nodes: 312  │  3 high  18 med  291 low

  RISK          κ     FAIL  FIX   ID
  ──────────────────────────────────────────────────────
  HIGH    0.821  ⚠      4    1   auth.RBACManager.grant
  HIGH    0.774  ⚠      2    0   db.Session.commit
  MED     0.631         1    1   api.router.create_user
```

- **κ（曲率）**：越高越危险，0.55 以上为 MED，0.75 以上为 HIGH
- **FAIL / FIX**：你历史上在这个节点失败/修复的次数
- **⚠**：奇点节点，高度关注

---

## 第三步：获取修复建议

```bash
wlbs fix
```

等价于：`wlbs-scan . --suggest`

也可以指定路径：

```bash
wlbs fix src/
```

**输出示例：**

```
  Repair suggestions for high-κ nodes:
  ─────────────────────────────────────────────────────
  auth.RBACManager.grant  κ=0.821
    → 历史上 4 次失败，1 次修复
    → 相关节点: auth.permissions, db.Role
    → 建议: 检查 grant() 的空值边界，roles 参数为 None 时会触发 NoneType 错误
```

---

## 常用命令速查

| 命令 | 作用 |
|---|---|
| `wlbs begin` | 注册 + 自动配置 pytest（首次必做） |
| `wlbs bug` | 扫描当前目录，显示高风险节点 |
| `wlbs bug src/` | 扫描指定目录 |
| `wlbs fix` | 给高风险节点提供修复建议 |
| `wlbs fix src/` | 指定目录的修复建议 |
| `wlbs-scan . --history` | 查看学习历史 |
| `wlbs-scan . --record-failure rbac` | 手动记录某节点失败 |
| `wlbs-scan . --record-fix rbac` | 手动记录某节点修复成功 |
| `wlbs-scan . --reset` | 清空本地记忆，重新开始 |

---

## 进阶：手动教它学习

如果没有配置 pytest 自动上报，可以手动告诉 wlbs 哪里出了问题：

```bash
# 测试在 rbac 模块失败了
wlbs-scan . --record-failure rbac

# 你修好了
wlbs-scan . --record-fix rbac

# 带详细信息
wlbs-scan . --record-failure auth.RBACManager.grant --detail "NoneType in grant()"
```

---

## 数据存储位置

| 内容 | 路径 |
|---|---|
| 账号凭据 | `~/.wlbs/config.json` |
| 项目记忆（曲率历史） | `<项目根目录>/.wlbs/` |
| 云端同步服务 | `http://111.231.112.127:8765` |

---

## 常见问题

**Q: `wlbs begin` 注册时收不到验证码？**
检查垃圾邮件，或稍等 1-2 分钟重试。

**Q: 扫描很慢？**
大项目（数万个节点）首次扫描需要几十秒，后续会缓存。可用 `wlbs bug src/` 缩小范围。

**Q: 已有 `pyproject.toml`，`wlbs begin` 会不会破坏它？**
不会。脚本只在文件末尾追加 `[tool.pytest.ini_options]` 块，且如果已有 `wlbs` 字样则跳过。

**Q: 不想用云端，只想本地用？**
跳过 `wlbs begin` 的注册步骤，直接用 `wlbs bug` / `wlbs fix`，本地记忆照常工作。