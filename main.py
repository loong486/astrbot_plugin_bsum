from astrbot.api.all import *
from astrbot.api.event import filter
import aiohttp
import asyncio
import re
import json

@register("bilibili_summary", "YourName", "B站视频轻量总结插件", "1.0.0")
class BilibiliSummaryPlugin(Star):
    # ✨ 这里的 init 方法多了一个 config: dict 参数，用来接收面板上的配置
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
    
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
            
            yield event.plain_result("🎨 正在渲染暗色主题卡片...")
            image_path = await self.render_html_to_image(video_title, summary_data)
            
            yield event.plain_result(f"✅ 处理完成！视频《{video_title}》的总结卡片已生成。\n（测试阶段打印结果：{summary_data['core']}）")
            
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
        # ✨ 从 AstrBot 可视化面板读取用户填写的配置
        api_key = self.config.get("llm_api_key", "").strip()
        api_url = self.config.get("llm_api_url", "").strip()
        model_name = self.config.get("llm_model_name", "").strip()
        
        # 兜底机制：如果用户没填 URL 和模型名，默认给 DeepSeek 的
        if not api_url:
            api_url = "https://api.deepseek.com/v1/chat/completions"
        if not model_name:
            model_name = "deepseek-chat"

        # 检查是否填了 API Key
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
                    raise Exception("大模型没有按规定返回 JSON 格式，请重试。返回内容：" + content)

    async def render_html_to_image(self, title: str, summary: dict) -> str:
        await asyncio.sleep(1)
        return "summary_card.png"