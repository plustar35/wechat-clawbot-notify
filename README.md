# WeChat ClawBot Notify

一个  Workbuddy AI Agent Skill，让你的 AI 助手能够通过微信 ClawBot 给你发送通知消息。

当 AI 完成自动化任务后，会自动通过微信通知你结果，即使你不在电脑前也不会错过重要信息。

## 工作原理

```
AI 助手 → ClawBot iLink API → 微信 ClawBot → 你的微信
```

1. **读取配置**：从 WorkBuddy 的 settings.json 中读取 ClawBot 通道配置（botToken、userId、baseUrl）
2. **获取 Token**：调用 iLink API 的 `/ilink/bot/getupdates` 接口，从最近的消息中提取 `context_token` 并缓存到本地
3. **发送消息**：使用缓存的 token，通过 `/ilink/bot/sendmessage` 接口发送消息到你的微信
4. **自动重试**：发送失败时自动刷新 token 并重试一次

配置读取会优先使用新的 WorkBuddy 配置文件位置（macOS/Linux: `~/.workbuddy/settings.json`，Windows: `%USERPROFILE%\.workbuddy\settings.json`），再回退到旧版应用配置目录。WorkBuddy 5.5 起 ClawBot 配置改为按用户存放在 `claw.users.<用户ID>.channels.weixinClawBot`，v1.3.0 起脚本同时兼容新旧两种结构，并优先读取新结构。

## 前置条件

- 支持 macOS / Windows / Linux
- 已安装 Python 3，并确保 `python` 命令可用且指向 Python 3
- 已安装 [WorkBuddy](https://workbuddy.ai) 并在设置中开启了微信 ClawBot 通道

## 使用指南

### 第一步：安装 Skill

将本项目克隆到 WorkBuddy 的 Skill 目录下（WorkBuddy 从 `~/.workbuddy/skills/` 加载技能）：

macOS / Linux:

```bash
git clone https://github.com/plustar35/wechat-clawbot-notify.git ~/.workbuddy/skills/wechat-clawbot-notify
```

Windows PowerShell:

```powershell
git clone https://github.com/plustar35/wechat-clawbot-notify.git "$env:USERPROFILE\.workbuddy\skills\wechat-clawbot-notify"
```

已安装过的用户升级：进入上述目录执行 `git pull`，然后运行 `status` 检查。

### 第二步：初始化配置

安装完成后，在 AI 助手中输入以下指令触发初始化：

```
/wechat-clawbot-notify 帮我初始化微信通知
```

AI 助手会自动执行以下操作：

1. 检查 WorkBuddy 中的 ClawBot 配置是否正确
2. 尝试获取 `context_token`（这一步可能需要等待几秒钟）

如果提示 "No messages with context_token found"，说明需要进入第三步。

注意：`.token_cache.json` 文件存在不代表已经可以发送消息。该文件可能只保存 `get_updates_buf` 游标；只有 `status` 输出 `Ready: True` 且显示 `Token:` 前缀时，才表示已经缓存了可用于发送的 `context_token`。

### 第三步：给微信 ClawBot 发送一条消息完成链接

打开微信，找到你的 **ClawBot**，随便发送一条消息（比如 "你好"）。

然后回到 AI 助手，告诉它：

```
已经发了，继续
```

AI 助手会重新获取 token，并发送一条验证消息到你的微信：

> 微信 ClawBot 通知技能配置完成！后续自动化任务完成后会自动通知你的微信。

**收到这条验证消息，就说明配置成功了！**

## 日常使用

配置完成后，无需手动操作。当你使用 AI 助手执行自动化任务时，任务完成后会自动通过微信通知你。

你也可以主动触发通知，对 AI 助手说：

```
明天上午 10 点微信提醒我有会议
```

## 命令参考


| 命令            | 说明               |
| ------------- | ---------------- |
| `send "消息内容"` | 发送文本消息到微信        |
| `refresh`     | 刷新 context_token |
| `status`      | 查看当前配置和 token 状态 |


手动调用示例：

```bash
# 发送消息
python scripts/send_wechat.py send "任务完成：报告已生成"

# 刷新 token
python scripts/send_wechat.py refresh

# 查看状态
python scripts/send_wechat.py status
```

## 故障排查


| 问题                                        | 解决方法                               |
| ----------------------------------------- | ---------------------------------- |
| 提示 "ClawBot channel is not enabled"       | 打开 WorkBuddy 设置，确认已开启微信 ClawBot 通道 |
| 提示 "No messages with context_token found" | 打开微信给 ClawBot 发一条消息，然后执行 `refresh` |
| 消息发送失败                                    | 执行 `refresh` 获取新的 token 后重试        |
| 提示 "HTTP 401"                             | 检查 WorkBuddy 设置中的 botToken 是否正确    |
| 提示 "Cannot read WorkBuddy settings"       | 确认已安装 WorkBuddy 且配置文件存在。WorkBuddy 找配置目录的规则是：环境变量 `WORKBUDDY_CONFIG_DIR` 优先，否则用用户主目录下的 `.workbuddy`（Windows 即 `C:\Users\<用户名>\.workbuddy`），脚本按同样规则查找 |
| `status` 里的 Bot ID 和 WorkBuddy 设置里的不一致，`refresh` 一直找不到消息 | 脚本读到了旧配置文件，升级到 v1.3.0 以上 |
| 提示 "Token: Cached for a different bot"   | WorkBuddy 重新绑定过 ClawBot，给 ClawBot 发一条消息后执行 `refresh` |


## 项目结构

```
wechat-clawbot-notify/
  SKILL.md                  # Skill 描述文件（AI 助手读取此文件了解如何使用）
  scripts/
    send_wechat.py          # 核心脚本：发送消息、刷新 token、查看状态
    inject_soul.py          # 将自动通知指令写入 SOUL.md（跨平台）
  .gitignore
  README.md
```

## License

MIT
