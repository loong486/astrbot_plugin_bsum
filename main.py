from astrbot.api.all import *
from astrbot.api.event import filter
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
        yield event.plain_result("⏳ 正在解析 B 站视频数据，请稍候...")
        
        try:
            # 1. 提取 BV 号并获取字幕文本
            bvid = self.extract_bvid(url)
            if not bvid:
                yield event.plain_result("❌ 无法识别链接中的 BV 号，请检查链接格式。")
                return

            yield event.plain_result(f"🔍 识别到视频 {bvid}，正在拉取数据...")
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
        """调用 B 站公开 API 获取视频标题和简介"""
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        # 伪装成浏览器，防止被 B 站防火墙拦截
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 使用 aiohttp 发起异步网络请求
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"网络请求失败，状态码: {response.status}")
                
                data = await response.json()
                
                # B 站 API 规定，code 为 0 才代表请求成功
                if data.get('code') != 0:
                    raise Exception(f"B站API返回错误: {data.get('message')}")
                    
                video_info = data['data']
                title = video_info['title']
                # 获取视频简介，如果简介为空，则给一个默认提示
                desc = video_info['desc'] if video_info['desc'] else "该视频未提供文字简介。"
                
                print(f"成功获取视频: {title}, 封面: {video_info['pic']}")
                
                # 将简介作为我们要总结的文案返回
                return desc, title

    async def generate_summary_via_llm(self, text: str) -> dict:
        # 占位：目前仅模拟等待1秒并返回假数据
        await asyncio.sleep(1)
        return {
            "core": "快速掌握 AstrBot 插件开发流程",
            "points": ["准备开发环境", "编写 main.py", "推送到 GitHub"]
        }

    async def render_html_to_image(self, title: str, summary: dict) -> str:
        # 占位：模拟渲染过程
        await asyncio.sleep(1)
        return "summary_card.png"