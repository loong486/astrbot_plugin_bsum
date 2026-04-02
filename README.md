<div align="center">
  <img src="https://socialify.git.ci/loong486/astrbot_plugin_bsum/image?description=1&font=Inter&forks=1&issues=1&language=1&name=1&owner=1&pattern=Plus&pulls=1&stargazers=1&theme=Dark" alt="astrbot_plugin_bsum" width="640" height="320" />
</div>

<div align="center">

# AstrBot Bilibili 视频总结插件

✨ **让 AI 助你一目十行，快速抓取 B 站视频核心价值** ✨

一款专为 [AstrBot](https://github.com/Astreter/AstrBot) 设计的高性能 Bilibili 视频总结插件。它能自动识别链接、提取 CC 字幕、并利用大语言模型（LLM）生成结构化的核心内容与关键要点总结。

</div>

---

## 🌟 核心特性

- **🚀 零指令触发**: 无需输入繁琐命令。直接在聊天中发送 B 站链接或 BV/AV 号，插件即可自动检测并启动总结。
- **📜 深度字幕提取**: 优先抓取官方 CC 字幕及 AI 自动生成的字幕，相比单纯总结简介，内容更真实、更完整。
- **📂 多分 P 完美支持**: 智能识别 `?p=N` 参数。无论是单集还是千集大合集，都能精准定位并总结你想看的那一集。
- **🎨 实时进度反馈**: 每一个处理步骤（获取详情、下载字幕、AI总结）都会实时反馈在对话中，告别盲目等待。
- **🔌 完美原生集成**: 直接调用 AstrBot 已配置的大模型提供商，无需额外填写 API Key，支持后台可视化模型切换。
- **🛡️ 强大的兼容性**: 完美支持 `b23.tv` 短链接、`AV` 号转换以及引用/转发消息中的链接提取。

## 📦 安装指南

1.  进入 AstrBot 插件市场或后台管理界面。
2.  搜索 `bilibili_summary` 或输入本插件仓库地址进行安装。
3.  或者，直接将项目克隆至 AstrBot 的 `data/plugins` 目录下。
4.  在管理面板开启插件。

## 🛠️ 配置说明

安装后，请在 AstrBot 管理后台进行以下配置：

| 配置项 | 描述 | 是否必填 |
| :--- | :--- | :---: |
| `llm_provider` | **选择总结模型**。下拉框选择 AstrBot 已配置的模型提供商。 | 否 (默认走对话模型) |
| `bilibili_sessdata`| **B站身份令牌**。用于获取需登录才能查看的字幕（如受限视频）。 | 否 |
| `bilibili_jct` | **B站 CSRF Token**。配合 SESSDATA 解锁更多 AI 自动生成的字幕。 | 否 |
| `prompt_template` | **系统提示词**。自定义 AI 的总结风格（默认为精简 JSON 引导）。 | 否 |

> **提示**：如何获取 `SESSDATA` 和 `bili_jct`？
> 登录 B 站网页版 -> 按 `F12` -> `Application(应用)` -> `Cookies` -> 复制对应值。

## 💡 使用方法

直接发送 B 站视频链接即可：

```text
https://www.bilibili.com/video/BV1Gf4y1y7wc/?p=5
```

或者是：

```text
帮我看看这个视频：BV1AWNFzvEEt
```

### 📝 输出示例

> 📺 **【1000集 TED-ED (P5 为什么水和油不相容)】**
>
> 📌 **核心内容**：
> 本视频深入浅出地解释了极性分子（水）与非极性分子（油）之间的相互作用力，阐述了由于氢键的存在，水分之间具有强烈的吸引力，从而排斥了不具备极性的油分子...
>
> ✨ **关键要点**：
> 1. 解释了极性分子与非极性分子的基本定义。
> 2. 详细演示了氢键在水分子结构中的决定性作用。
> 3. 破除了“油排斥水”的常见误区，指出实际上是水分子之间互相吸引导致油被挤出。
> 4. 介绍了表面活性剂（如洗洁精）如何破坏这种平衡。

---

## 🤝 贡献与反馈

欢迎提交 Pull Request 或 Issue 来帮助我们改进！

## 📄 开源许可

本项目基于 [MIT License](LICENSE) 开源。