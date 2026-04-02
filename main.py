from astrbot.api.all import *
from astrbot.api.event import filter
import aiohttp
import re
import json

@register("bilibili_summary", "YourName", "B站视频总结插件", "1.1.0")
class BilibiliSummaryPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
    
    @filter.regex(r"(?i)(?:bilibili\.com/video/|b23\.tv/|BV[a-zA-Z0-9]+|av\d+)")
    async def bilibili_summary(self, event: AstrMessageEvent):
        '''生成B站视频总结。自动检测B站链接或BV号触发。'''
        
        message_str = event.message_str
        bvid = await self.extract_bvid(message_str)
        if not bvid:
            return # 没匹配到BV号，直接忽略不处理
            
        yield event.plain_result("⏳ 检测到 B 站视频，正在生成总结，请稍候...")
        
        try:

            timeout = aiohttp.ClientTimeout(total=45) # 增加了超时时间以应对长字幕拉取
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 1. 抓取视频基础信息与字幕链接
                text_content, video_title, subtitle_url = await self.fetch_bilibili_info(session, bvid)
                
                # 2. 尝试抓取并合并字幕内容
                if not subtitle_url:
                    yield event.plain_result("❌ 该视频无可用字幕。")
                    return
                
                try:
                    sub_text = await self.fetch_subtitle_content(session, subtitle_url)
                    if not sub_text:
                        yield event.plain_result("❌ 该视频无可用字幕。")
                        return
                    
                    # 限制字幕长度，防止超出大模型 Token 限制 (设定20000字截断)
                    if len(sub_text) > 20000:
                        sub_text = sub_text[:20000] + "\n...(内容过长已截断)"
                    text_content = f"【视频完整字幕】\n{sub_text}"
                except Exception as e:
                    logger.warning(f"Bilibili Summary: 抓取字幕失败。原因: {str(e)}")
                    yield event.plain_result("❌ 该视频字幕抓取失败。")
                    return

                # 3. AI 总结
                summary_data = await self.generate_summary_via_llm(event, text_content, video_title)
            
            # 4. 格式化输出
            result_text = self.format_summary(video_title, summary_data)
            yield event.plain_result(result_text)
            
        except Exception as e:
            logger.error(f"Bilibili Summary Plugin Error: {str(e)}", exc_info=True)
            yield event.plain_result(f"❌ 运行过程中出现错误：{str(e)}")

    # ================= 核心功能实现 =================
    
    async def extract_bvid(self, text: str) -> str:
        """从文本中提取并解析真实的 BV 号（支持短链接、AV号等转换）"""
        # 1. 尝试直接匹配 BV 号
        match = re.search(r'(BV[1-9A-HJ-NP-Za-km-z]{10})', text)
        if match:
            return match.group(1)
            
        # 2. 尝试匹配 AV 号并转换
        av_match = re.search(r'(?i)av(\d+)', text)
        if av_match:
            aid = av_match.group(1)
            try:
                api_url = f"https://api.bilibili.com/x/web-interface/view?aid={aid}"
                headers = {"User-Agent": "Mozilla/5.0"}
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, headers=headers) as resp:
                        data = await resp.json()
                        if data.get('code') == 0:
                            return data['data'].get('bvid', "")
            except Exception as e:
                logger.error(f"AV转BV失败: {str(e)}")
                
        # 3. 尝试匹配 b23.tv 短链接并解析
        b23_match = re.search(r'https?://b23\.tv/[a-zA-Z0-9]+', text)
        if b23_match:
            short_url = b23_match.group(0)
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                async with aiohttp.ClientSession() as session:
                    async with session.get(short_url, headers=headers, allow_redirects=False) as resp:
                        if resp.status in [301, 302, 303, 307, 308]:
                            location = resp.headers.get('Location', '')
                            # 从重定向的 URL 中提取 BV 号
                            bv_match = re.search(r'(BV[1-9A-HJ-NP-Za-km-z]{10})', location)
                            if bv_match:
                                return bv_match.group(1)
            except Exception as e:
                logger.error(f"短链接解析失败: {str(e)}")
                
        return ""

    async def fetch_bilibili_info(self, session: aiohttp.ClientSession, bvid: str):
        """获取 B 站视频标题、简介和字幕链接"""
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }
        
        cookies = {}
        sessdata = self.config.get("bilibili_sessdata", "").strip()
        bili_jct = self.config.get("bilibili_jct", "").strip()
        if sessdata:
            cookies["SESSDATA"] = sessdata
        if bili_jct:
            cookies["bili_jct"] = bili_jct
        
        async with session.get(api_url, headers=headers, cookies=cookies) as resp:
            data = await resp.json()
            if data.get('code') != 0:
                raise Exception(f"B站 API 错误: {data.get('message')}")
            
            video_info = data['data']
            title = video_info.get('title', '')
            desc = video_info.get('desc', '无简介')
            
            # 提取字幕列表
            subtitles = video_info.get('subtitle', {}).get('list', [])
            subtitle_url = ""
            if subtitles:
                # 优先寻找中文或 AI 自动生成的字幕
                for sub in subtitles:
                    if 'zh' in sub.get('lan', '').lower():
                        subtitle_url = sub.get('subtitle_url', '')
                        break
                # 如果没有中文，默认拿第一个字幕
                if not subtitle_url and len(subtitles) > 0:
                    subtitle_url = subtitles[0].get('subtitle_url', '')
                    
            # 补全 https 协议头
            if subtitle_url and subtitle_url.startswith("//"):
                subtitle_url = "https:" + subtitle_url
                
            return desc, title, subtitle_url

    async def fetch_subtitle_content(self, session: aiohttp.ClientSession, subtitle_url: str) -> str:
        """从字幕 JSON 文件中提取纯文本字幕内容"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        # 很多时候不需要 Cookie 也能拿字幕，但传了更保险
        cookies = {}
        sessdata = self.config.get("bilibili_sessdata", "").strip()
        if sessdata:
            cookies["SESSDATA"] = sessdata
            
        async with session.get(subtitle_url, headers=headers, cookies=cookies) as resp:
            # content_type=None 允许解析 B 站 CDN 返回的 text/plain 格式 JSON
            data = await resp.json(content_type=None) 
            body = data.get('body', [])
            
            # 提取并拼接所有字幕片段
            texts = [item.get('content', '') for item in body]
            return " ".join(texts)

    async def generate_summary_via_llm(self, event: AstrMessageEvent, text: str, title: str) -> dict:
        """调用 AstrBot 内置大模型进行总结并返回 JSON 数据"""
        
        provider_id = self.config.get("llm_provider")
        if not provider_id:
            # 如果配置中留空，则默认使用当前对话会话分配的 provider
            umo = event.unified_msg_origin
            provider_id = await self.context.get_current_chat_provider_id(umo=umo)
            
        if not provider_id:
            raise Exception("未找到可用的大语言模型，请在 AstrBot 设置中配置并启用模型。")

        prompt_template = self.config.get(
            "prompt_template",
            "你是一个文本阅读和总结专家。我会直接为你提供视频的标题以及完整的字幕文本。请你完全根据我提供的这些文本内容进行总结，不要尝试访问视频或进行任何解析。即使内容较短，也请尽力提炼。请严格以JSON格式返回: {\"core\": \"<核心总结文字>\", \"points\": [\"<要点1>\", \"<要点2>\"]}"
        )

        prompt = f"{prompt_template}\n\n【视频标题】: {title}\n\n【视频内容信息】:\n{text}"
        
        # 使用 AstrBot 统一生成接口
        llm_resp = await self.context.llm_generate(
            chat_provider_id=provider_id,
            prompt=prompt
        )
        content = llm_resp.completion_text
        
        content = content.strip()
        if content.startswith("```json"): content = content[7:]
        if content.startswith("```"): content = content[3:]
        if content.endswith("```"): content = content[:-3]
        
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            logger.error(f"大模型返回的 JSON 解析失败。原始内容: {content}")
            raise Exception("大模型返回的数据格式异常，无法解析。")

    def format_summary(self, title: str, summary: dict) -> str:
        """格式化总结输出为文字"""
        core = summary.get('core', '无')
        points = summary.get('points', [])
        
        points_text = "\n".join([f"{i}. {point}" for i, point in enumerate(points, 1)])
        
        result = f"""📺 【{title}】

📌 核心内容：
{core}

✨ 关键要点：
{points_text}"""
        
        return result