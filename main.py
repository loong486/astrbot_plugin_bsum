from astrbot.api.all import *
from astrbot.api.event import filter
import aiohttp
import asyncio
import re
import json
import os
import time

@register("bilibili_summary", "YourName", "B站视频总结插件", "1.0.0")
class BilibiliSummaryPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
    
    @filter.command("bsum")
    async def bilibili_summary(self, event: AstrMessageEvent, url: str):
        '''生成B站视频总结。使用方法：/bsum <B站链接>'''
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
            
            # 3. 格式化输出
            result_text = self.format_summary(video_title, summary_data)
            yield event.plain_result(result_text)
            
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

    def format_summary(self, title: str, summary: dict) -> str:
        """格式化总结输出为文字"""
        core = summary.get('core', '无')
        points = summary.get('points', [])
        
        result = f"""
📺 【{title}】

📌 核心内容：
{core}

✨ 关键要点：
"""
        for i, point in enumerate(points, 1):
            result += f"{i}. {point}\n"
        
        return result