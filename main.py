from astrbot.api.all import *
from astrbot.api.event import filter
import aiohttp
import asyncio
import re
import json
import os
import time
from html2image import Html2Image

@register("bilibili_summary", "YourName", "B站视频总结插件", "1.0.0")
class BilibiliSummaryPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        
        # 获取基础目录并确保图片存放目录存在
        base_dir = os.getcwd()
        self.temp_dir = os.path.join(base_dir, "data", "bili_summary_pics")
        os.makedirs(self.temp_dir, exist_ok=True)
    
    @filter.command("bsum")
    async def bilibili_summary(self, event: AstrMessageEvent, url: str):
        '''生成B站视频总结卡片。使用方法：/bsum <B站链接>'''
        yield event.plain_result("⏳ 正在处理中，请稍候...")
        
        try:
            bvid = self.extract_bvid(url)
            if not bvid:
                yield event.plain_result("❌ 无法识别链接中的 BV 号。")
                return

            # 1. 抓取数据
            text_content, video_title = await self.fetch_bilibili_subs(bvid)
            
            # 2. AI 总结
            summary_data = await self.generate_summary_via_llm(text_content, video_title)
            
            # 3. 渲染图片
            yield event.plain_result("🎨 正在绘制暗黑主题卡片...")
            image_path = await self.render_html_to_image(video_title, summary_data)
            
            # 4. 发送图片
            yield event.image_result(image_path)
            
        except Exception as e:
            yield event.plain_result(f"❌ 运行过程中出现错误：{str(e)}")

    # ================= 核心功能实现 =================
    
    def extract_bvid(self, url: str) -> str:
        match = re.search(r'(BV[1-9A-HJ-NP-Za-km-z]{10})', url)
        return match.group(1) if match else ""

    async def fetch_bilibili_subs(self, bvid: str):
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers=headers) as resp:
                data = await resp.json()
                if data.get('code') != 0: raise Exception(f"B站API错误: {data.get('message')}")
                video_info = data['data']
                return video_info['desc'] or "无简介", video_info['title']

    async def generate_summary_via_llm(self, text: str, title: str) -> dict:
        api_key = self.config.get("llm_api_key", "").strip()
        api_url = self.config.get("llm_api_url", "https://api.deepseek.com/v1/chat/completions")
        model_name = self.config.get("llm_model_name", "deepseek-chat")

        if not api_key: raise Exception("请在插件配置中填写 API Key！")

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "你是一个视频总结专家，请以JSON格式返回: {\"core\": \"...\", \"points\": [\"...\", \"...\"]}"},
                {"role": "user", "content": f"标题: {title}\n简介: {text}"}
            ],
            "response_format": {"type": "json_object"}
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as resp:
                result = await resp.json()
                content = result['choices'][0]['message']['content']
                return json.loads(content)

    async def render_html_to_image(self, title: str, summary: dict) -> str:
        def _render():
            try:
                browser_path = None
                paths_to_check = [
                    # Docker/Linux 现代包路径（优先检查）
                    "/usr/bin/chromium",
                    "/usr/bin/chromium-browser",
                    "/snap/bin/chromium",
                    "/usr/bin/google-chrome",
                    "/usr/bin/google-chrome-stable",
                    # Windows 路径
                    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                ]
                
                for p in paths_to_check:
                    if os.path.exists(p):
                        browser_path = p
                        print(f"[✓] 检测到浏览器: {browser_path}")
                        break
            
                if not browser_path:
                    raise Exception(
                        "❌ 未找到浏览器！\n"
                        "Docker 环境请执行：apt-get update && apt-get install -y chromium\n"
                        "本地环境请安装 Google Chrome"
                    )
            
                hti = Html2Image(
                    browser_executable=browser_path, 
                    custom_flags=[
                        '--no-sandbox',
                        '--disable-gpu',
                        '--disable-dev-shm-usage',
                        '--disable-extensions'
                    ]
                )
                hti.output_path = self.temp_dir
            
                filename = f"summary_{int(time.time())}.png"
                points_html = "".join([f"<li>{p}</li>" for p in summary.get('points', [])])
                
                html_content = f"""
                <html>
                <head><meta charset="utf-8"></head>
                <body style="background-color: #1e1e2e; color: #cdd6f4; font-family: sans-serif; padding: 30px; width: 600px; margin: 0;">
                    <div style="background: #181825; border-radius: 12px; padding: 25px; border: 1px solid #313244;">
                        <h1 style="color: #89b4fa; font-size: 24px; border-bottom: 1px solid #313244; padding-bottom: 10px; margin-top: 0;">{title}</h1>
                        <p style="background: #313244; padding: 15px; border-left: 4px solid #a6e3a1; border-radius: 4px;">{summary.get('core', '')}</p>
                        <ul style="line-height: 1.6;">{points_html}</ul>
                    </div>
                </body>
                </html>
                """
                
                hti.snapshot(html_str=html_content, save_as=filename, size=(660, 600))
                return os.path.join(self.temp_dir, filename)
            except Exception as e:
                print(f"[Html2Image Error]: {str(e)}")
                raise
            
        return await asyncio.to_thread(_render)