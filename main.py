from astrbot.api import logger
from astrbot.api.all import AstrMessageEvent, Context, Star, register
from astrbot.api.event import filter
import aiohttp
import re
import json
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse
import astrbot.api.message_components as Comp

@register("bilibili_summary", "YourName", "B站视频总结插件", "1.2.0")
class BilibiliSummaryPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.bilibili_sessdata = self.config.get("bilibili_sessdata", "").strip()
        self.bilibili_jct = self.config.get("bilibili_jct", "").strip()
        self.max_subtitle_length = 20000 # 安全截断
        self.llm_context_budget = self.config.get("llm_context_budget", 3000)  # 预留给LLM上下文token数（粗估）
    
    @filter.regex(r"(?i)(?:(?:www\.|m\.)?bilibili\.com/video/|b23\.tv/|\bBV[1-9A-HJ-NP-Za-km-z]{10}\b|\bav\d+\b)")
    async def bilibili_summary(self, event: AstrMessageEvent):
        '''生成B站视频总结。自动检测B站链接或BV号触发。'''
        
        # 1. 从消息中提取所有可能的 bilibili 链接
        links = self.extract_bilibili_links_from_message(event)
        if not links:
            return

        # 仅处理第一个发现的链接
        video_input = links[0]
        logger.info(f"Bilibili Summary: 提取到视频标识: {video_input}")
        
        # 提取分P号
        page_num = 1
        p_match = re.search(r'[?&]p=(\d+)', video_input)
        if p_match:
            page_num = max(1, int(p_match.group(1)))
        
        yield event.plain_result(f"⏳ 检测到视频，正在获取详情...")

        timeout = aiohttp.ClientTimeout(total=45)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 2. 解析为 BV 号
            try:
                bvid = await self.resolve_video_id(session, video_input)
            except Exception as e:
                logger.error(f"Bilibili Summary stage=resolve_video_id error={e}", exc_info=True)
                yield event.plain_result("❌ 解析视频标识失败，请检查链接格式。")
                return

            if not bvid:
                yield event.plain_result("❌ 无法解析视频 BV 号。\n请确保您发送的是一个有效的 B 站**视频**链接。")
                return

            # 3. 获取视频基本信息 (标题, aid, cid)
            try:
                video_info = await self.get_video_info(session, bvid, page_num)
            except Exception as e:
                logger.error(f"Bilibili Summary stage=get_video_info bvid={bvid} error={e}", exc_info=True)
                yield event.plain_result("❌ 获取视频详情失败，请稍后再试。")
                return

            if not video_info:
                yield event.plain_result("❌ 获取视频详情失败。")
                return

            if video_info.get("error"):
                yield event.plain_result(f"❌ {video_info['error']}")
                return

            video_title = video_info.get("title", "未知标题")
            yield event.plain_result(f"✅ 成功获取视频: {video_title}\n正在寻找可用字幕...")

            # 4. 获取字幕文本
            try:
                subtitle_text_raw = await self.get_subtitle(
                    session,
                    video_info["aid"],
                    video_info["cid"],
                    bvid,
                    video_info.get("video_subtitles"),
                )
            except Exception as e:
                logger.error(
                    f"Bilibili Summary stage=get_subtitle bvid={bvid} "
                    f"aid={video_info.get('aid')} cid={video_info.get('cid')} error={e}",
                    exc_info=True,
                )
                yield event.plain_result("❌ 拉取字幕失败，请稍后再试。")
                return

            if not subtitle_text_raw:
                yield event.plain_result("❌ 该视频无可用字幕。")
                return

            subtitle_text = self.budget_text_for_llm(subtitle_text_raw)

            yield event.plain_result(
                f"✅ 字幕下载成功 (约 {len(subtitle_text)} 字)\n正在调用 AI 进行总结..."
            )

            # 5. 调用 AI 总结
            try:
                summary_data = await self.generate_summary_via_llm(event, subtitle_text, video_title)
            except Exception as e:
                logger.error(f"Bilibili Summary stage=llm_generate bvid={bvid} error={e}", exc_info=True)
                yield event.plain_result("❌ AI 总结生成失败，请稍后重试。")
                return

            yield event.plain_result("🚀 AI 总结完成，正在生成卡片...")

        # 6. 格式化输出
        result_text = self.format_summary(video_title, summary_data)
        yield event.plain_result(result_text)

    # ================= 辅助解析逻辑 =================

    def extract_bilibili_links_from_message(self, event: AstrMessageEvent) -> List[str]:
        """从消息链中提取所有可能的bilibili链接"""
        plain_links: List[str] = []
        reply_links: List[str] = []
        other_links: List[str] = []

        for component in event.message_obj.message:
            if isinstance(component, Comp.Plain):
                plain_links.extend(self.extract_links_from_text(component.text))
            elif isinstance(component, Comp.Reply):
                if hasattr(component, 'text') and component.text:
                    reply_links.extend(self.extract_links_from_text(component.text))
            # 兼容更多消息组件：扫描常见字段中的可见文本与URL。
            else:
                other_links.extend(self.extract_links_from_component(component))

        ordered_links = plain_links + reply_links + other_links
        return self.deduplicate_keep_order(ordered_links)

    def deduplicate_keep_order(self, values: List[str]) -> List[str]:
        """按出现顺序去重，避免重复扫描导致的误选。"""
        seen = set()
        result: List[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def extract_links_from_component(self, component: Any) -> List[str]:
        """从非纯文本组件中尽可能提取链接或视频标识"""
        candidates: List[str] = []
        for attr in ("url", "text", "content", "title", "desc", "data"):
            value = getattr(component, attr, None)
            if isinstance(value, str):
                candidates.append(value)
            elif isinstance(value, dict):
                candidates.extend(self._flatten_strings(value))
            elif isinstance(value, list):
                candidates.extend(self._flatten_strings(value))

        links: List[str] = []
        for text in candidates:
            links.extend(self.extract_links_from_text(text))
        return links

    def _flatten_strings(self, value: Any) -> List[str]:
        """递归提取容器中的字符串，用于兜底扫描链接"""
        results: List[str] = []
        if isinstance(value, str):
            results.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                results.extend(self._flatten_strings(v))
        elif isinstance(value, list):
            for item in value:
                results.extend(self._flatten_strings(item))
        return results

    def extract_links_from_text(self, text: str) -> List[str]:
        """从文本中提取bilibili相关标识，按出现顺序返回"""
        url_patterns = [
            r'https?://(?:www\.|m\.)?bilibili\.com/video/(?:[^\s\'\"<>，。）\)!！\?？;；：:、])+',
            r'https?://b23\.tv/(?:[^\s\'\"<>，。）\)!！\?？;；：:、])+',
            r'\bBV[1-9A-HJ-NP-Za-km-z]{10}\b',
            r'(?i)\bav\d+\b',
        ]
        matches_with_pos: List[tuple] = []
        for pattern in url_patterns:
            for match in re.finditer(pattern, text):
                matches_with_pos.append((match.start(), match.group(0)))

        matches_with_pos.sort(key=lambda x: x[0])
        links = [m[1] for m in matches_with_pos]
        return links

    async def resolve_video_id(self, session: aiohttp.ClientSession, video_input: str) -> Optional[str]:
        """将各种输入格式统一解析为 BV 号"""
        # 1. 已经是 BV 号
        if re.match(r'^BV[1-9A-HJ-NP-Za-km-z]{10}$', video_input):
            return video_input
        
        # 2. 短链接 b23.tv
        if 'b23.tv' in video_input:
            try:
                # 确保短链接有协议头
                if not video_input.startswith('http'):
                    video_input = 'https://' + video_input

                # 先尝试获取重定向地址（不跟随重定向）
                async with session.get(video_input, allow_redirects=False) as resp:
                    if resp.status in [301, 302, 303, 307, 308]:
                        location = resp.headers.get('Location', '')
                        if location:
                            location = urljoin(str(resp.url), location)
                        bv_match = re.search(r'(BV[1-9A-HJ-NP-Za-km-z]{10})', location)
                        if bv_match:
                            return bv_match.group(1)
                        # 如果重定向地址中没有BV号，可能是跳转到中间页面，需要跟随重定向
                        if location:
                            video_input = location

                # 如果上面没有返回，尝试跟随重定向获取最终页面
                async with session.get(video_input, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    bv_match = re.search(r'(BV[1-9A-HJ-NP-Za-km-z]{10})', final_url)
                    if bv_match:
                        return bv_match.group(1)
                    # 尝试从响应内容中解析BV号
                    text = await resp.text()
                    bv_match = re.search(r'(BV[1-9A-HJ-NP-Za-km-z]{10})', text)
                    if bv_match:
                        return bv_match.group(1)
            except Exception as e:
                logger.error(f"解析短链接失败: {e}")
                return None

        # 3. 完整链接或 av 号
        bv_match = re.search(r'(BV[1-9A-HJ-NP-Za-km-z]{10})', video_input)
        if bv_match: return bv_match.group(1)

        av_match = re.search(r'(?i)\bav(\d+)\b', video_input)
        if av_match:
            aid = av_match.group(1)
            api_url = f"https://api.bilibili.com/x/web-interface/view?aid={aid}"
            async with session.get(api_url) as resp:
                data = await self.read_json_response(resp, "resolve_video_id(aid)")
                if not data:
                    return None
                if data.get('code') == 0:
                    return data['data'].get('bvid')

        return None

    # ================= 核心抓取逻辑 =================

    async def get_video_info(self, session: aiohttp.ClientSession, bvid: str, page: int = 1) -> Optional[Dict[str, Any]]:
        """获取视频基本信息"""
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/"
        }
        cookies = {}
        if self.bilibili_sessdata: cookies["SESSDATA"] = self.bilibili_sessdata
        if self.bilibili_jct: cookies["bili_jct"] = self.bilibili_jct

        async with session.get(api_url, headers=headers, cookies=cookies) as resp:
            data = await self.read_json_response(resp, "get_video_info")
            if not data:
                return None
            if data.get('code') == 0:
                vdata = data['data']
                pages = vdata.get('pages', [])
                cid = vdata.get('cid') # 默认取 P1
                title = vdata.get('title', '')
                page = max(1, page)

                if pages and page > len(pages):
                    return {
                        "error": f"请求分P超出范围：该视频仅有 {len(pages)} P。"
                    }
                
                # 如果是多P视频，根据 page 参数获取对应的 cid
                if len(pages) >= page:
                    page_data = pages[page-1]
                    cid = page_data.get('cid')
                    # 如果是多P视频，标题加上分P名
                    if len(pages) > 1:
                        title = f"{title} (P{page} {page_data.get('part', '')})"
                
                # 获取视频级字幕作为备选
                video_subtitles = vdata.get('subtitle', {}).get('list', [])
                
                return {
                    'aid': vdata.get('aid'),
                    'cid': cid,
                    'title': title,
                    'desc': vdata.get('desc'),
                    'video_subtitles': video_subtitles
                }
        return None

    async def get_subtitle(
        self,
        session: aiohttp.ClientSession,
        aid: int,
        cid: int,
        bvid: str,
        fallback_subtitles: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """获取字幕内容，结合 player/v2 和 view 接口的返回结果"""
        url = f"https://api.bilibili.com/x/player/v2?aid={aid}&cid={cid}&bvid={bvid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/"
        }
        cookies = {}
        if self.bilibili_sessdata: cookies["SESSDATA"] = self.bilibili_sessdata
        if self.bilibili_jct: cookies["bili_jct"] = self.bilibili_jct

        selected_url = ""
        
        # 1. 尝试从 player/v2 获取字幕
        try:
            async with session.get(url, headers=headers, cookies=cookies) as resp:
                data = await self.read_json_response(resp, "get_subtitle(player/v2)")
                if not data:
                    data = {}
                if data.get('code') == 0:
                    subtitles = data.get('data', {}).get('subtitle', {}).get('subtitles', [])
                    if subtitles:
                        # 优先选择中文
                        for sub in subtitles:
                            if 'zh' in sub.get('lan', '').lower():
                                selected_url = sub.get('subtitle_url', '')
                                break
                        if not selected_url: selected_url = subtitles[0].get('subtitle_url', '')
        except Exception as e:
            logger.warning(f"Bilibili Summary: player/v2 接口调用异常: {e}")

        # 2. 如果 player/v2 没拿到，尝试使用 fallback_subtitles (来自 view 接口)
        if not selected_url and fallback_subtitles:
            logger.info("Bilibili Summary: player/v2 未获取到字幕，尝试使用 view 接口备选字幕。")
            for sub in fallback_subtitles:
                if 'zh' in sub.get('lan', '').lower():
                    selected_url = sub.get('subtitle_url', '')
                    break
            if not selected_url: selected_url = fallback_subtitles[0].get('subtitle_url', '')

        if selected_url:
            if selected_url.startswith("//"): selected_url = "https:" + selected_url
            if not self.is_allowed_subtitle_url(selected_url):
                logger.warning(f"Bilibili Summary: 字幕URL不在白名单内: {selected_url}")
                return None
            return await self.download_subtitle(session, selected_url)
            
        return None

    def is_allowed_subtitle_url(self, url: str) -> bool:
        """限制字幕下载目标域，降低意外外连风险。"""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False

        allowed_suffixes = (
            "bilibili.com",
            "bilivideo.com",
            "hdslb.com",
        )
        return any(host == suffix or host.endswith(f".{suffix}") for suffix in allowed_suffixes)

    async def download_subtitle(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """下载字幕 JSON 并转换为纯文本"""
        async with session.get(url) as resp:
            data = await self.read_json_response(resp, "download_subtitle")
            if not data:
                return None
            body = data.get('body', [])
            if not isinstance(body, list):
                logger.warning("Bilibili Summary: 字幕 body 结构异常，非 list。")
                return None

            texts: List[str] = []
            for item in body:
                if not isinstance(item, dict):
                    continue
                content = item.get('content', '')
                if isinstance(content, str) and content.strip():
                    texts.append(content)

            if not texts:
                return None

            full_text = " ".join(texts)
            if len(full_text) > self.max_subtitle_length:
                full_text = full_text[:self.max_subtitle_length] + "..."
            return full_text

    def budget_text_for_llm(self, text: str) -> str:
        """根据LLM上下文预算动态截断摘要文本，避免超限。\n
        粗估：文字 -> token 的比例约为 1:0.4（中文偏少）。
        预留 prompt + output 空间，确保总token在安全范围内。
        """
        estimated_chars = self.llm_context_budget * 2.5
        estimated_chars = int(estimated_chars)

        if len(text) <= estimated_chars:
            return text

        truncated = text[:estimated_chars]
        logger.info(
            f"Bilibili Summary: 字幕长度超预算，"
            f"原长 {len(text)} 字，截断到 {estimated_chars} 字。"
        )
        return truncated + "..."

    async def read_json_response(self, resp: aiohttp.ClientResponse, scene: str) -> Optional[Dict[str, Any]]:
        """统一处理HTTP状态与JSON解析异常，避免上游抖动放大。"""
        if resp.status < 200 or resp.status >= 300:
            logger.warning(f"Bilibili Summary: {scene} HTTP状态异常: {resp.status}")
            return None

        try:
            data = await resp.json(content_type=None)
        except Exception as e:
            text = await resp.text()
            logger.warning(f"Bilibili Summary: {scene} JSON解析失败: {e}; 响应片段: {text[:200]}")
            return None

        if not isinstance(data, dict):
            logger.warning(f"Bilibili Summary: {scene} 返回结构异常，非 dict。")
            return None
        return data

    # ================= AI 与 格式化 =================

    async def generate_summary_via_llm(self, event: AstrMessageEvent, text: str, title: str) -> dict:
        provider_id = self.config.get("llm_provider")
        if not provider_id:
            provider_id = await self.context.get_current_chat_provider_id(umo=event.unified_msg_origin)
            
        prompt_template = self.config.get("prompt_template", "你是一个文本阅读和总结专家。我会直接为你提供视频的标题以及完整的字幕文本。请你完全根据我提供的这些文本内容进行总结，不要尝试访问视频或进行任何解析。即使内容较短，也请尽力提炼。请严格以JSON格式返回: {\"core\": \"<核心总结文字>\", \"points\": [\"<要点1>\", \"<要点2>\"]}")
        prompt = f"{prompt_template}\n\n【视频标题】: {title}\n\n【视频内容信息】:\n{text}"
        
        llm_resp = await self.context.llm_generate(chat_provider_id=provider_id, prompt=prompt)
        content = llm_resp.completion_text.strip()

        parsed = self.parse_llm_json(content)
        if parsed is None:
            logger.error(f"大模型解析失败: {content}")
            raise Exception("大模型输出格式错误。")

        core = parsed.get("core", "").strip() if isinstance(parsed.get("core"), str) else ""
        points_raw = parsed.get("points", [])
        points = points_raw if isinstance(points_raw, list) else []
        points = [p for p in points if isinstance(p, str) and p.strip()]

        if not core:
            raise Exception("大模型输出缺少核心总结。")

        return {
            "core": core,
            "points": points,
        }

    def parse_llm_json(self, content: str) -> Optional[Dict[str, Any]]:
        """从LLM输出中提取JSON对象，仅接受严格JSON。"""
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        # 优先尝试直接按JSON解析。
        try:
            obj = json.loads(cleaned)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass

        # 允许存在前后说明文字，抽取第一个JSON对象（非贪婪）。
        match = re.search(r"\{[\s\S]*?\}", cleaned)
        if match:
            candidate = self.sanitize_json_candidate(match.group(0))
            try:
                obj = json.loads(candidate)
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                pass

        # 进一步尝试：从最后匹配的 } 向前回溯，找到对应的 {（处理多块情况）。
        last_brace = cleaned.rfind("}")
        if last_brace > 0:
            for start_pos in range(last_brace - 1, -1, -1):
                if cleaned[start_pos] == "{":
                    candidate = cleaned[start_pos:last_brace + 1]
                    candidate = self.sanitize_json_candidate(candidate)
                    try:
                        obj = json.loads(candidate)
                        return obj if isinstance(obj, dict) else None
                    except json.JSONDecodeError:
                        continue

        return None

    def sanitize_json_candidate(self, candidate: str) -> str:
        """对候选JSON做最小修复：去除对象/数组结尾多余逗号。"""
        return re.sub(r",\s*([}\]])", r"\1", candidate)

    def format_summary(self, title: str, summary: dict) -> str:
        core = summary.get('core', '无')
        points = summary.get('points', [])
        points_text = "\n".join([f"{i}. {point}" for i, point in enumerate(points, 1)])
        return f"📺 【{title}】\n\n📌 核心内容：\n{core}\n\n✨ 关键要点：\n{points_text}"
