<div align="center">

# 🎬 AstrBot Bilibili 视频总结插件

[English](#-features) | [中文](#功能特性)

<!-- 简介横幅 -->
![](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square)
![](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![](https://img.shields.io/badge/Version-1.2.0-orange?style=flat-square)

一款为 **AstrBot** 精心设计的高性能 Bilibili 视频总结插件。能够自动识别和处理 B 站视频链接，智能提取字幕内容，并邀请大语言模型生成结构化的核心总结与关键要点。

[⬇️ 快速安装](#-安装指南) • [⚙️ 配置说明](#-配置说明) • [📖 使用示例](#-使用方法) • [🚀 高级功能](#-高级功能)

</div>

---

## 📋 目录

- [功能特性](#功能特性)
- [系统要求](#系统要求)
- [安装指南](#-安装指南)
- [配置说明](#-配置说明)
- [使用方法](#-使用方法)
- [高级功能](#-高级功能)
- [常见问题](#-常见问题)
- [故障排除](#-故障排除)
- [开发贡献](#-开发贡献)

---

## 功能特性

### ✨ 核心功能

| 功能 | 描述 |
|------|------|
| 🔗 **多格式链接识别** | 支持完整URL、短链接、BV号、av号等多种输入格式 |
| 📝 **智能字幕提取** | 自动获取视频 CC 字幕，支持多语言识别 |
| 🧠 **AI 智能总结** | 集成大语言模型，生成结构化的核心内容和关键要点 |
| 📺 **多P视频支持** | 完美处理分P视频，自动识别并标记分P信息 |
| 🔐 **登录字幕支持** | 支持使用 B站账号登录，获取需登录才能查看的字幕 |
| ⚙️ **高度可配置** | 灵活的提示词定制，支持多个 LLM 提供商 |
| ⚡ **异步处理** | 基于 asyncio 的异步架构，高性能无阻塞处理 |

### 🎯 支持的输入格式

```
✅ https://www.bilibili.com/video/BV1fb411s7oZ/
✅ https://m.bilibili.com/video/BV1fb411s7oZ/
✅ https://b23.tv/BV1fb411s7oZ
✅ BV1fb411s7oZ
✅ av12345678
✅ https://www.bilibili.com/video/BV1fb411s7oZ/?p=2  (支持分P)
```

---

## 系统要求

- **Python** >= 3.9
- **AstrBot** >= 0.1.0
- **网络连接** 用于访问 B 站 API 和 LLM 服务
- **LLM 服务** 用于生成总结（可以是 DeepSeek、GPT、Claude 等）

---

## 📦 安装指南

### 方法一：通过 AstrBot 插件市场（推荐）

1. 打开 AstrBot 后台管理界面
2. 进入 **插件管理** 或 **插件市场**
3. 搜索 `astrbot_plugin_bsum`
4. 点击 **安装** 按钮
5. 重启 AstrBot 使插件生效

### 方法二：手动安装

1. 克隆或下载本项目到本地
   ```bash
   git clone https://github.com/loong486/astrbot_plugin_bsum.git
   ```

2. 将项目文件夹复制到 AstrBot 的 `plugins` 目录
   ```bash
   cp -r astrbot_plugin_bsum /path/to/astrbot/plugins/
   ```

3. 安装依赖（如未自动安装）
   ```bash
   pip install -r requirements.txt
   ```

4. 重启 AstrBot
   ```bash
   systemctl restart astrbot  # 或根据您的运行方式重启
   ```

### 验证安装

启动 AstrBot 后，如果在日志中看到类似下列信息，说明插件加载成功：
```
[INFO] Loading plugin: bilibili_summary...
[INFO] Plugin bilibili_summary (v1.2.0) loaded successfully
```

---

## ⚙️ 配置说明

### 基本配置

在 AstrBot 的插件配置页面，填写以下配置项：

| 配置项 | 类型 | 必填 | 默认值 | 说明 |
|-------|------|------|-------|------|
| `bilibili_sessdata` | string | ❌ | 空 | B 站登录凭证，用于获取不公开的字幕 |
| `bilibili_jct` | string | ❌ | 空 | B 站 CSRF Token，与 SESSDATA 配套使用 |
| `llm_provider` | string | ❌ | 当前会话 | 选择用于总结的 LLM 提供商 |
| `prompt_template` | string | ❌ | 内置模板 | 自定义系统提示词模板 |

### 获取 SESSDATA 和 bili_jct 的步骤

> 如果你只想总结公开视频的字幕，**可以跳过此步骤**。

1. 在浏览器中登录 [B 站官网](https://www.bilibili.com)
2. 按下 `F12` 打开开发者工具
3. 导航到 **Application** 选项卡
4. 在左侧找到 **Cookies** → `https://www.bilibili.com`
5. 搜索并复制以下两个值：
   - `SESSDATA` - 会话数据凭证
   - `bili_jct` - CSRF 防护令牌

**⚠️ 安全提示：**
- 这些凭证等同于你的登录状态，**不要分享给他人**
- 不要在公开的代码库或日志中暴露这些值
- 如果泄露，请立即在 B 站登出所有设备

### 自定义提示词

默认提示词旨在生成结构化的 JSON 输出。如果需要自定义总结格式，可以修改 `prompt_template`：

**默认模板：**
```
你是一个视频总结专家。请根据提供的视频标题以及完整字幕，提炼出视频的核心内容和关键要点。请以JSON格式返回: {"core": "<核心内容>", "points": ["<要点1>", "<要点2>"]}
```

**自定义示例（侧重于技术要点）：**
```
你是一位技术博主。请只提取视频中的技术关键词、代码示例和性能指标。返回JSON格式：{"technical_keywords": [...], "code_snippets": [...], "performance_metrics": [...]}
```

---

## 💡 使用方法

### 基础用法

在聊天中发送视频链接，插件会自动识别并总结：

```
直接发送链接：
🧑: https://www.bilibili.com/video/BV1fb411s7oZ/

🤖: ⏳ 检测到视频，正在获取详情...
   ✅ 成功获取视频: C#/.NET 8 全新 GC 算法解读
   正在寻找可用字幕...
   ✅ 字幕下载成功 (约 2500 字)
   正在调用 AI 进行总结...
   🚀 AI 总结完成，正在生成卡片...
   
   📺 【C#/.NET 8 全新 GC 算法解读】
   
   📌 核心内容：
   本视频详细介绍了 .NET 8 中引入的全新垃圾回收（GC）算法...
   
   ✨ 关键要点：
   1. 新算法被称为"动态自适应代际GC"
   2. 主要解决了 Gen2 碎片化问题
   ...
```

### 支持的输入方式

```
# ✅ 完整 URL（推荐）
https://www.bilibili.com/video/BV1fb411s7oZ/

# ✅ B 站短链接
https://b23.tv/BV1fb411s7oZ

# ✅ 仅 BV 号
BV1fb411s7oZ

# ✅ 仅 av 号
av12345678

# ✅ 分P视频（自动识别第2P）
https://www.bilibili.com/video/BV1fb411s7oZ/?p=2

# ✅ 手机端链接
https://m.bilibili.com/video/BV1fb411s7oZ/
```

### 📊 输出格式

插件返回的总结遵循以下格式：

```
📺 【视频标题】

📌 核心内容：
视频的核心内容摘要，通常为1-2段话。

✨ 关键要点：
1. 第一个关键要点
2. 第二个关键要点
3. 第三个关键要点
...
```

---

## 🚀 高级功能

### 1. 分P视频处理

对于有多个分P的视频，插件会自动识别 URL 中的 `?p=` 参数：

```
# 总结第3P的内容
https://www.bilibili.com/video/BV1fb411s7oZ/?p=3

输出标题会自动标注：
📺 【原标题】(P3 分P标题)
```

### 2. 多 LLM 提供商支持

根据 AstrBot 的配置，你可以切换不同的 LLM 提供商：

- **DeepSeek** (默认推荐，成本低)
- **OpenAI GPT-4** (最佳质量)
- **Claude** (兼具质量和成本)
- **其他 AstrBot 支持的提供商**

在插件配置中选择 `llm_provider` 即可切换。

### 3. 登录字幕获取

某些 B 站视频的字幕需要登录才能查看。配置好 `SESSDATA` 和 `bili_jct` 后，插件会自动尝试获取这些字幕：

```
⚠️ 查看登录受限的字幕时流程：
1. 插件检测到字幕需要登录
2. 使用配置的凭证向 B 站 API 请求
3. 获取受限字幕内容
4. 进行总结并返回结果
```

---

## ❓ 常见问题

### Q1: 为什么收到"无法解析视频 BV 号"的错误？

**A:** 这通常是以下原因导致的：
- ❌ 链接输入有误（复制不完整）
- ❌ 输入的是播放列表链接而非单视频链接
- ❌ 网络连接问题无法访问 B 站 API

**解决方案：**
- 确保链接完整，推荐直接从浏览器地址栏复制
- 确认输入的是单个视频，而非播放列表
- 检查网络连接

### Q2: 多长的字幕才能生成总结？

**A:** 理论上没有最小限制，但建议：
- ✅ **理想长度**：500-20000 字
- ⚠️ **过短**：少于 100 字的字幕，总结效果可能一般
- ⚠️ **过长**：超过 20000 字的字幕会被截断以节省 LLM token

### Q3: 生成的总结质量不理想怎么办？

**A:** 尝试以下方法改进：
1. **修改提示词** - 在 `prompt_template` 中更具体地指导 LLM
2. **更换 LLM 提供商** - GPT-4 或 Claude 通常质量更好
3. **检查字幕质量** - 某些视频的字幕质量较差会影响总结

### Q4: 为什么某些视频无法获取字幕？

**A:** 可能原因：
- ❌ 视频本身没有字幕
- ❌ 字幕需要登录才能查看（需配置凭证）
- ❌ 字幕被上传者设为私密

**解决方案：**
- 配置 `SESSDATA` 和 `bili_jct` 以获取受限字幕
- 若仍无字幕，该视频可能确实没有字幕数据

### Q5: 配置了 SESSDATA 后仍提示"无可用字幕"？

**A:** 检查以下几点：
1. ✓ SESSDATA 和 bili_jct 是否都正确复制（位数要对）
2. ✓ 凭证是否过期（B 站 Cookie 可能会定期更新）
3. ✓ 视频本身是否有字幕
4. ✓ 在 B 站网站上登录后能否正常查看该视频的字幕

---

## 🔧 故障排除

### 常见错误信息

| 错误信息 | 可能原因 | 解决方案 |
|--------|--------|--------|
| `❌ 无法解析视频 BV 号` | 链接格式错误或网络问题 | 检查链接完整性，确保网络畅通 |
| `❌ 获取视频详情失败` | B 站 API 暂时不可用 | 稍后重试，或检查网络连接 |
| `❌ 该视频无可用字幕` | 视频无字幕或字幕需登录 | 配置凭证或更换视频 |
| `❌ 大模型输出格式错误` | LLM 返回了非 JSON 格式 | 检查提示词设置，或更换 LLM |
| `❌ 运行过程中出现错误` | 其他异常情况 | 查看 AstrBot 日志获取详细信息 |

### 调试日志

启用详细日志以诊断问题：

1. 打开 AstrBot 的配置文件
2. 查找 `log_level` 设置为 `DEBUG`
3. 查看 AstrBot 的日志输出，搜索 `Bilibili Summary` 相关信息

---

## 🛠️ 开发贡献

### 项目结构

```
astrbot_plugin_bsum/
├── main.py              # 主插件代码
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # 配置schema定义
├── requirements.txt     # 依赖列表
└── README.md           # 本说明文档
```

### 技术栈

- **aiohttp** - 异步 HTTP 请求库
- **beautifulsoup4** - HTML 解析（备用）
- **html2image** - HTML 转图片（可选）

### 贡献流程

1. **Fork 本项目**
2. **创建特性分支** (`git checkout -b feature/amazing-feature`)
3. **提交改动** (`git commit -m 'Add amazing feature'`)
4. **推送到分支** (`git push origin feature/amazing-feature`)
5. **提交 Pull Request**

### 报告问题

如遇到 Bug 或功能建议，欢迎提交 [Issue](https://github.com/loong486/astrbot_plugin_bsum/issues)。提交时请包含：
- 详细的问题描述
- 复现步骤
- 预期行为 vs 实际行为
- 相关日志片段

---

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源，详见 LICENSE 文件。

---

## 🙏 致谢

- 感谢 [AstrBot](https://github.com/Soulter/astrbot) 提供的优秀框架
- 感谢 B 站提供的公开 API
- 特别感谢所有贡献者和用户的支持

---

<div align="center">

**[⬆ 返回顶部](#-astrbot-bilibili-视频总结插件)**

Made with ❤️ by [loong486](https://github.com/loong486)

</div>
