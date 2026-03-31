from astrbot.api.all import *
import aiohttp
import asyncio
import re

@register("bilibili_summary", "YourName", "B站视频轻量总结插件", "1.0.0")
class BilibiliSummaryPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 这里可以填入你使用的大模型 API 密钥
        self.llm_api_key = "YOUR_API_KEY"
    
    @filter.command("bsum")
    async def bilibili_summary(self, event: AstrMessageEvent, url: str):
        '''生成B站视频总结卡片。使用方法：/bsum <B站链接>'''
        yield event.plain_result("⏳ 正在轻量解析 B 站视频数据，请稍候...")
        
        try:
            # 1. 提取 BV 号并获取字幕文本
            bvid = self.extract_bvid(url)
            if not bvid:
                yield event.plain_result("❌ 无法识别链接中的 BV 号，请检查链接格式。")
                return

            yield event.plain_result(f"🔍 识别到视频 {bvid}，正在拉取字幕与元数据...")
            text_content, video_title = await self.fetch_bilibili_subs(bvid)
            
            # 2. 调用大模型进行总结
            yield event.plain_result("🧠 正在使用 AI 模型生成结构化总结...")
            summary_data = await self.generate_summary_via_llm(text_content)
            
            # 3. 渲染暗色卡片
            yield event.plain_result("🎨 正在渲染暗色主题卡片...")
            image_path = await self.render_html_to_image(video_title, summary_data)
            
            # 4. 发送图片结果
            # 假设 image_path 是本地生成的图片路径
            # yield event.image_result(image_path)
            yield event.plain_result(f"✅ 处理完成！视频《{video_title}》的总结卡片已生成。")
            
        except Exception as e:
            yield event.plain_result(f"❌ 运行过程中出现错误：{str(e)}")

    # ================= 核心功能实现 =================
    
    def extract_bvid(self, url: str) -> str:
        # 使用正则表达式匹配链接中的 BV 号
        match = re.search(r'(BV[1-9A-HJ-NP-Za-km-z]{10})', url)
        return match.group(1) if match else ""

    async def fetch_bilibili_subs(self, bvid: str):
        # 此处为轻量化爬取逻辑示意
        # 实际开发中，这里需要调用 B 站 api.bilibili.com 接口获取 cid，再获取字幕 json
        # 为了演示，我们返回模拟数据
        await asyncio.sleep(1) 
        mock_title = "【测试视频】教你如何开发 AstrBot 插件"
        mock_subs = "大家好，今天我们来学习开发插件。首先第一步是准备环境..."
        return mock_subs, mock_title

    async def generate_summary_via_llm(self, text: str) -> dict:
        # 在这里接入你选择的大模型（如 OpenAI API 或其他兼容格式的 API）
        # 将 text 发送给模型，要求其返回 JSON 格式的总结
        await asyncio.sleep(1)
        return {
            "core": "快速掌握 AstrBot 插件开发流程",
            "points": ["准备开发环境", "编写 main.py", "推送到 GitHub"]
        }

    async def render_html_to_image(self, title: str, summary: dict) -> str:
        # 使用 HTML/CSS 构建暗色卡片，然后用 html2image 等轻量工具截图
        # 预先写好一个精美的暗色 CSS 样式
        html_template = f"""
        <html>
        <body style="background-color: #1e1e2e; color: #cdd6f4; font-family: sans-serif; padding: 40px; width: 600px;">
            <h1 style="color: #89b4fa;">{title}</h1>
            <h3 style="color: #f38ba8;">🎯 核心总结</h3>
            <p>{summary['core']}</p>
            <h3 style="color: #a6e3a1;">💡 关键要点</h3>
            <ul>
                {''.join([f'<li>{p}</li>' for p in summary['points']])}
            </ul>
        </body>
        </html>
        """
        # 此处为 html2image 的调用示意
        # hti.snapshot(html_str=html_template, save_as='summary_card.png')
        return "summary_card.png"