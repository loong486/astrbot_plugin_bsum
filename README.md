<div align="center">
  <img src="https://socialify.git.ci/loong486/astrbot_plugin_bsum/image?description=1&font=Inter&forks=1&issues=1&language=1&name=1&owner=1&pattern=Plus&pulls=1&stargazers=1&theme=Dark" alt="astrbot_plugin_bsum" width="640" height="320" />
</div>

<div align="center">

# AstrBot BiliBili 视频总结插件

✨ 一款专为 AstrBot 设计的高性能 Bilibili 视频总结插件。它能自动识别链接、提取 CC 字幕、并利用大语言模型（LLM）生成结构化的核心内容与关键要点总结。✨

</div>

---

## 🚀 功能特性

- **🔗 智能链接识别**: 自动从 Bilibili 视频链接中提取 `BV` 号。
- **📝 文本提取**: 通过 Bilibili API 获取视频标题和简介。
- **🧠 AI 驱动总结**: 对接大语言模型（默认 DeepSeek），精准提炼视频核心内容。
- **💬 格式化输出**: 将总结结果以清晰、美观的卡片形式发送。
- **⚙️ 高度可配置**: 支持自定义 LLM API Key、接口地址和模型名称。

## 📦 安装指南

1.  进入 AstrBot 插件市场或后台管理界面。
2.  搜索 `bilibili_summary` 或本插件的仓库地址进行安装。
3.  或者，直接将项目文件下载并放置于 AstrBot 的 `plugins` 目录下。
4.  重启 AstrBot 以加载插件。

## 🛠️ 配置说明

安装插件后，请在 AstrBot 的插件配置中填写以下信息：

| 配置项          | 描述                                     | 是否必填 | 默认值                              |
| -------------- | ---------------------------------------- | -------- | ----------------------------------- |
| `bilibili_sessdata` | B站 SESSDATA，用于获取需登录才能看的字幕 | 否       | `""`                                |
| `bilibili_jct`  | B站 bili_jct (CSRF Token)，配合 SESSDATA 解锁更多 AI 字幕权限 | 否       | `""`                                |
| `llm_provider`  | 选择用于总结的大语言模型（下拉框选择）    | 否       | *(留空则默认使用当前会话的模型)*    |
| `prompt_template` | 系统提示词，用于指导大模型如何总结         | 否       | *(默认的 JSON 输出引导提示词)*      |

> **如何获取 SESSDATA 和 bili_jct**: 在电脑浏览器中登录 B 站，按 `F12` 打开开发者工具，进入 `Application` (应用) -> `Cookies`，找到 `SESSDATA` 和 `bili_jct` 的值并分别复制填入。

## 💡 使用方法

在聊天中发送以下命令即可：

```
/bsum <Bilibili视频链接>
```

**例如:**

```
/bsum https://www.bilibili.com/video/BV1fb411s7oZ/
```

### 📝 输出示例

机器人将会返回如下格式的总结：

> ⏳ 正在处理中，请稍候...

> 📺 【C#/.NET 8 全新 GC 算法解读】
>
> 📌 核心内容：
> 本视频详细介绍了 .NET 8 中引入的全新垃圾回收（GC）算法，该算法通过动态调整代际大小和优化对象提升策略，显著降低了高负载应用中的 GC 停顿时间（Pause Time），提升了整体性能和吞吐量。
>
> ✨ 关键要点：
> 1. 新算法被称为“动态自适应代际GC”。
> 2. 主要解决了 Gen2 碎片化和 Full GC 过于频繁的问题。
> 3. 通过内部遥测数据动态调整年轻代（Gen0/Gen1）的大小。
> 4. 优化了对象从年轻代晋升到老年代的阈值，减少不必要的对象迁移。
> 5. 在基准测试中，P99 延迟降低了高达 40%。

---

## 🤝 贡献

欢迎提交 Pull Requests 或 Issues 来改进此插件！

## 📄 开源许可

本项目基于 [MIT License](LICENSE) 开源。
