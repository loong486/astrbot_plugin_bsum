from astrbot.api.all import *
from astrbot.api.event import filter
import aiohttp
import asyncio
import re
import json
import os
import time
from html2image import Html2Image

@register("bilibili_summary", "YourName", "B站视频轻量总结插件", "1.0.0")
class BilibiliSummaryPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        
        # ✨ 修复点：改用 os.getcwd() 获取当前工作目录，避免 Context 属性错误
        base_dir = os.getcwd()
        self.temp_dir = os.path.join(base_dir, "data", "bili_summary_pics")
        
        # 确保图片存放目录存在
        if not os.path.exists(self.temp_dir):
            try:
                os.makedirs(self.temp_dir, exist_ok=True)
            except Exception as e:
                print(f"[BiliSummary] 创建目录失败: {e}")
    
    @filter.command("bsum")
    async def bilibili_summary(self, event: AstrMessageEvent, url: str):
        '''生成B站视频总结卡片。使用方法：/bsum <B站链接>'''
        yield event.plain_result("⏳ 正在解析 B 站视频数据，请稍候...")
        
        try:
            bvid = self.extract_bvid(url)
            if not bvid:
                yield event.plain_result("❌ 无法识别链接中的 BV 号，请检查链接格式。")
                return

            yield event.plain_result(f"🔍 识别到视频 {bvid}，正在拉取数据...")
            text_content, video_title = await self.fetch_bilibili_subs(bvid)
            
            yield event.plain_result(f"🧠 正在阅读《{video_title}》的简介，生成结构化总结...")
            summary_data = await self.generate_summary_via_llm(text_content, video_title)
            
            yield event.plain_result("🎨 正在渲染暗色主题卡片，马上就来...")
            image_path = await self.render_html_to_image(video_title, summary_data)
            
            # 发送生成的图片
            yield event.image_result(image_path)
            
        except Exception as e:
            yield event.plain_result(f"❌ 运行过程中出现错误：{str(e)}")

    # ================= 核心功能实现 =================
    
    def extract_bvid(self, url: str) -> str:
        match = re.search(r'(BV[1-9A-HJ-NP-Za-km-z]{10})', url)
        return match.group(1) if match else ""

    async def fetch_bilibili_subs(self, bvid: str):
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"网络请求失败，状态码: {response.status}")
                
                data = await response.json()
                if data.get('code') != 0:
                    raise Exception(f"B站API返回错误: {data.get('message')}")
                    
                video_info = data['data']
                title = video_info['title']
                desc = video_info['desc'] if video_info['desc'] else "该视频未提供文字简介。"
                return desc, title

    async def generate_summary_via_llm(self, text: str, title: str) -> dict:
        api_key = self.config.get("llm_api_key", "").strip()
        api_url = self.config.get("llm_api_url", "").strip()
        model_name = self.config.get("llm_model_name", "").strip()
        
        if not api_url:
            api_url = "https://api.deepseek.com/v1/chat/completions"
        if not model_name:
            model_name = "deepseek-chat"

        if not api_key:
             raise Exception("未配置大模型的 API Key！请前往 AstrBot 管理面板 -> 插件配置 中填写。")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        system_prompt = (
            "你是一个专业的B站视频内容总结助手。请根据用户提供的视频标题和简介，"
            "提取出视频的核心内容和关键信息。\n"
            "你必须严格以 JSON 格式输出，不要包含任何额外的 Markdown 标记（如 ```json 等），"
            "只需要纯 JSON 字符串。JSON 结构必须如下：\n"
            "{\n"
            '  "core": "用一两句话概括视频的核心主题",\n'
            '  "points": ["要点1", "要点2", "要点3"]\n'
            "}"
        )
        
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"视频标题：{title}\n视频简介：{text}"}
            ],
            "temperature": 0.7 
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"大模型 API 请求失败: {error_text}")
                
                result = await response.json()
                content = result['choices'][0]['message']['content']
                
                try:
                    content = content.replace("```json", "").replace("```", "").strip()
                    summary_dict = json.loads(content)
                    return summary_dict
                except json.JSONDecodeError:
                    raise Exception("大模型没有按规定返回 JSON 格式。返回内容：" + content)

    async def render_html_to_image(self, title: str, summary: dict) -> str:
        def _render():
            # 针对 VPS 无头环境优化参数
            hti = Html2Image(custom_flags=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'])
            hti.output_path = self.temp_dir
            
            filename = f"summary_{int(time.time())}.png"
            output_filepath = os.path.join(self.temp_dir, filename)
            
            points_html = "".join([f"<li>{p}</li>" for p in summary.get('points', [])])
            core_text = summary.get('core', '未提取到核心内容')
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        background-color: #1e1e2e;
                        color: #cdd6f4;
                        font-family: 'sans-serif';
                        padding: 40px;
                        width: 720px;
                        margin: 0;
                        box-sizing: border-box;
                    }}
                    .container {{
                        background: #181825;
                        border-radius: 16px;
                        padding: 30px;
                        box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                        border: 1px solid #313244;
                    }}
                    h1 {{
                        color: #89b4fa;
                        font-size: 26px;
                        margin-top: 0;
                        border-bottom: 2px solid #313244;
                        padding-bottom: 15px;
                        line-height: 1.4;
                    }}
                    .section-title {{
                        color: #f38ba8;
                        font-size: 20px;
                        margin-top: 25px;
                        font-weight: bold;
                    }}
                    .core-text {{
                        background: #313244;
                        padding: 15px 20px;
                        border-left: 5px solid #a6e3a1;
                        border-radius: 8px;
                        font-size: 18px;
                        line-height: 1.6;
                        margin-top: 15px;
                    }}
                    ul {{
                        margin-top: 15px;
                        padding-left: 25px;
                    }}
                    li {{
                        font-size: 18px;
                        line-height: 1.6;
                        margin-bottom: 12px;
                        color: #bac2de;
                    }}
                    .footer {{
                        margin-top: 30px;
                        text-align: right;
                        color: #6c7086;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>{title}</h1>
                    <div class="section-title">🎯 核心提炼</div>
                    <div class="core-text">{core_text}</div>
                    <div class="section-title">💡 关键要点</div>
                    <ul>
                        {points_html}
                    </ul>
                    <div class="footer">🚀 Generated by AstrBot Bilibili Plugin</div>
                </div>
            </body>
            </html>
            """
            
            hti.snapshot(html_str=html_content, save_as=filename, size=(800, 800))
            return output_filepath
            
        return await asyncio.to_thread(_render)