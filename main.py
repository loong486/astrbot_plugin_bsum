from astrbot.api.all import *
from astrbot.api.event import filter  # ✨ 新增这一行：明确导入 AstrBot 的 filter 模块
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
            
            yield event.plain_result(f"✅ 处理完成！视频《{video_title}》的总结卡片已生成。")
            
        except Exception as e:
            yield event.plain_result(f"❌ 运行过程中出现错误：{str(e)}")

    # ================= 核心功能实现 =================
    
    def extract_bvid(self, url: str) -> str:
        # 使用正则表达式匹配链接中的 BV 号
        match = re.search(r'(BV[1-9A-HJ-NP-Za-km-z]{10})', url)
        return match.group(1) if match else ""

    async def fetch_bilibili_subs(self, bvid: str):
        await asyncio.sleep(1) 
        mock_title = "【测试视频】教你如何开发 AstrBot 插件"
        mock_subs = "大家好，今天我们来学习开发插件。首先第一步是准备环境..."
        return mock_subs, mock_title

    async def generate_summary_via_llm(self, text: str) -> dict:
        await asyncio.sleep(1)
        return {
            "core": "快速掌握 AstrBot 插件开发流程",
            "points": ["准备开发环境", "编写 main.py", "推送到 GitHub"]
        }

    async def render_html_to_image(self, title: str, summary: dict) -> str:
        # 模拟渲染过程
        return "summary_card.png"