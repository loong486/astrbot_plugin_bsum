from astrbot.api.all import *
from astrbot.api.event import filter
import aiohttp
import re
import json

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

            # 设置 30 秒全局超时，防止协程挂死
            timeout = aiohttp.ClientTimeout(total=30)
            
            # 复用同一个 ClientSession，提升网络请求效率
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 1. 抓取数据 (修改了方法名以准确表达功能)
                text_content, video_title = await self.fetch_bilibili_info(session, bvid)
                
                # 2. AI 总结
                summary_data = await self.generate_summary_via_llm(session, text_content, video_title)
            
            # 3. 格式化输出
            result_text = self.format_summary(video_title, summary_data)
            yield event.plain_result(result_text)
            
        except Exception as e:
            # 引入标准日志记录，保留完整堆栈信息以便排错
            logger.error(f"Bilibili Summary Plugin Error: {str(e)}", exc_info=True)
            yield event.plain_result(f"❌ 运行过程中出现错误：{str(e)}")

    # ================= 核心功能实现 =================
    
    def extract_bvid(self, url: str) -> str:
        match = re.search(r'(BV[1-9A-HJ-NP-Za-km-z]{10})', url)
        return match.group(1) if match else ""

    async def fetch_bilibili_info(self, session: aiohttp.ClientSession, bvid: str):
        """获取 B 站视频标题和简介"""
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        # 使用现代浏览器 UA，防止被 WAF 拦截
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }
        
        async with session.get(api_url, headers=headers) as resp:
            data = await resp.json()
            if data.get('code') != 0:
                raise Exception(f"B站 API 错误: {data.get('message')}")
            
            video_info = data['data']
            return video_info['desc'] or "无简介", video_info['title']

    async def generate_summary_via_llm(self, session: aiohttp.ClientSession, text: str, title: str) -> dict:
        """调用大语言模型进行总结并返回 JSON 数据"""
        api_key = self.config.get("llm_api_key", "").strip()
        api_url = self.config.get("llm_api_url", "https://api.deepseek.com/v1/chat/completions")
        model_name = self.config.get("llm_model_name", "deepseek-chat")

        if not api_key:
            raise Exception("请在插件配置中填写 API Key！")

        headers = {
            "Authorization": f"Bearer {api_key}", 
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "你是一个视频总结专家，请以JSON格式返回: {\"core\": \"...\", \"points\": [\"...\", \"...\"]}"},
                {"role": "user", "content": f"标题: {title}\n简介: {text}"}
            ],
            "response_format": {"type": "json_object"}
        }
        
        async with session.post(api_url, headers=headers, json=payload) as resp:
            result = await resp.json()
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            # 清理可能存在的 Markdown 代码块标记
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            # JSON 解析容错处理
            try:
                return json.loads(content.strip())
            except json.JSONDecodeError:
                logger.error(f"大模型返回的 JSON 解析失败。原始内容: {content}")
                raise Exception("大模型返回的数据格式异常，无法解析。")

    def format_summary(self, title: str, summary: dict) -> str:
        """格式化总结输出为文字"""
        core = summary.get('core', '无')
        points = summary.get('points', [])
        
        # 使用列表推导式和 join 拼接字符串，提升性能
        points_text = "\n".join([f"{i}. {point}" for i, point in enumerate(points, 1)])
        
        result = f"""📺 【{title}】

📌 核心内容：
{core}

✨ 关键要点：
{points_text}"""
        
        return result