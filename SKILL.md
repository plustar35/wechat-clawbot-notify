---
name: wechat-clawbot-notify
description: "Send notification messages to the user's WeChat via ClawBot (iLink API). Use when automation tasks complete and need to notify the user, or when the user asks to send a message to their WeChat. Triggers on: 'notify me on WeChat', 'send to my WeChat', 'push result to WeChat', '发微信通知', '推送到微信', '通知我'."
description_zh: "通过微信 ClawBot 发送通知消息给用户"
description_en: "Send notification messages to user's WeChat via ClawBot"
version: 1.3.0
allowed-tools: Bash,Read
compatibility: macOS / Windows / Linux. Requires Python 3. Reads config from WorkBuddy settings.json.
metadata:
  version: "1.3.0"
  openclaw:
    emoji: "\U0001F4AC"
    requires:
      bins:
        - python
---

# WeChat ClawBot Notify

通过微信 ClawBot iLink API 发送文本消息给用户。

> **平台说明**：统一使用 `python` 执行脚本。macOS/Linux/Bash 使用 `$SKILL_DIR/scripts/...`；Windows PowerShell 使用 `$env:SKILL_DIR\scripts\...`。要求 `python` 指向 Python 3。

## 初始化检查（必须优先执行）

**使用任何命令前，先执行 `status` 检查配置和 token 状态。不要只根据 `.token_cache.json` 是否存在判断技能已就绪；该文件可能只有 `get_updates_buf` 游标，没有可发送消息的 `context_token`。**

### 第 1 步：检查 ClawBot 配置

macOS / Linux / Bash:
```bash
python "$SKILL_DIR/scripts/send_wechat.py" status
```

Windows PowerShell:
```powershell
python "$env:SKILL_DIR\scripts\send_wechat.py" status
```

- **输出 `Ready: True` 且 `Token:` 显示 token 前缀** → 技能已就绪，直接跳到 [发送消息](#发送消息)。
- **输出 `Ready: False` 或 `Token: Not cached`** → 进入第 2 步。
- **报错** → ClawBot 未配置。告诉用户："请先在 WorkBuddy 设置中连接你的微信 ClawBot 通道。" 到此停止。

### 第 2 步：获取 context_token

macOS / Linux / Bash:
```bash
python "$SKILL_DIR/scripts/send_wechat.py" refresh
```

Windows PowerShell:
```powershell
python "$env:SKILL_DIR\scripts\send_wechat.py" refresh
```

- **成功**（输出 "Token refreshed successfully"）→ 进入第 3 步。
- **失败**（输出 "No messages with context_token found"）→ 告诉用户："请打开微信，给你的 ClawBot 发一条消息，然后告诉我继续。" **等待用户确认后**，重试本步骤。

### 第 3 步：配置自动通知

macOS / Linux / Bash:
```bash
python "$SKILL_DIR/scripts/inject_soul.py"
```

Windows PowerShell:
```powershell
python "$env:SKILL_DIR\scripts\inject_soul.py"
```

将自动通知指令写入 `~/.workbuddy/SOUL.md`，后续自动化任务完成后会自动使用本技能通知用户。幂等操作，可重复执行。

### 第 4 步：发送验证消息

macOS / Linux / Bash:
```bash
python "$SKILL_DIR/scripts/send_wechat.py" send "微信 ClawBot 通知技能配置完成！后续自动化任务完成后会自动通知你的微信。"
```

Windows PowerShell:
```powershell
python "$env:SKILL_DIR\scripts\send_wechat.py" send "微信 ClawBot 通知技能配置完成！后续自动化任务完成后会自动通知你的微信。"
```

- **成功** → 告诉用户："配置完成！验证消息已发送到你的微信，后续自动化任务会自动通知你。"
- **失败** → 告诉用户："配置基本完成，但验证消息发送失败。稍后可以尝试执行 refresh 刷新 token。"

---

## 发送消息

macOS / Linux / Bash:
```bash
python "$SKILL_DIR/scripts/send_wechat.py" send "消息内容"
```

Windows PowerShell:
```powershell
python "$env:SKILL_DIR\scripts\send_wechat.py" send "消息内容"
```

## 其他命令

### 查看状态

macOS / Linux / Bash:
```bash
python "$SKILL_DIR/scripts/send_wechat.py" status
```

Windows PowerShell:
```powershell
python "$env:SKILL_DIR\scripts\send_wechat.py" status
```

### 刷新 token

发送失败时，刷新缓存的 token：

macOS / Linux / Bash:
```bash
python "$SKILL_DIR/scripts/send_wechat.py" refresh
```

Windows PowerShell:
```powershell
python "$env:SKILL_DIR\scripts\send_wechat.py" refresh
```

## 故障排查

| 问题 | 解决方法 |
|---|---|
| `.token_cache.json` 不存在 | 按上面的初始化步骤执行 |
| "No cached context_token" | 用户给 ClawBot 发一条消息，然后执行 `refresh` |
| "getupdates returned ret=-14" | 旧缓存 cursor 或旧 ClawBot 配置失效；脚本会自动丢弃 cursor 重试。仍失败时，让用户给 ClawBot 再发一条消息后执行 `refresh` |
| 发送静默失败 | 执行 `refresh` 获取新的 token |
| "HTTP 401" | 检查 WorkBuddy 设置中的 botToken |
| "Token: Cached for a different bot" | WorkBuddy 重新绑定过 ClawBot，缓存的 token 属于旧 bot。让用户给 ClawBot 发一条消息后执行 `refresh` |
| `status` 里的 Bot ID 与 WorkBuddy 设置中当前 ClawBot 不一致 | 脚本读到了旧配置文件。升级到 v1.3.0 以上（已适配 WorkBuddy 5.5 的按用户存放的配置结构） |

## 工作原理

1. **配置**：从 WorkBuddy settings 读取 weixinClawBot 通道配置（botToken、userId、baseUrl）。WorkBuddy 5.5 起配置位于 `claw.users.<用户ID>.channels.weixinClawBot`，旧版位于 `claw.channels.weixinClawBot`，脚本两种都认，优先新版
2. **Token**：调用 `/ilink/bot/getupdates` 从最近的消息中获取 `context_token`，缓存到本地
3. **发送**：使用缓存的 token 向 `/ilink/bot/sendmessage` 发送消息
4. **重试**：发送失败时自动刷新 token 并重试一次
5. **日志**：所有操作记录到 `logs/send_wechat.log`
