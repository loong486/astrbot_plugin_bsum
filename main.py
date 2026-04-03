from astrbot.api import logger
from astrbot.api.all import AstrMessageEvent, Context, Star, register
from astrbot.api.event import filter
import aiohttp
import asyncio
import re
import json
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse
import astrbot.api.message_components as Comp

@register("bilibili_summary", "YourName", "B站视频总结插件", "1.2.0")
class BilibiliSummaryPlugin(Star):
    PAGE_PARAM_PATTERN = re.compile(r"[?&]p=(\d+)")
    BVID_STRICT_PATTERN = re.compile(r"(?i)^BV[1-9A-HJ-NP-Za-km-z]{10}$")
    BVID_SEARCH_PATTERN = re.compile(r"(?i)(BV[1-9A-HJ-NP-Za-km-z]{10})")
    BV_TEXT_PATTERN = re.compile(r"(?i)bv[1-9A-HJ-NP-Za-km-z]{10}")
    AV_SEARCH_PATTERN = re.compile(r"(?i)\bav(\d+)\b")
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
    }
    ALLOWED_SUBTITLE_HOSTS = {
        "bilibili.com",
        "www.bilibili.com",
        "m.bilibili.com",
        "bilivideo.com",
        "www.bilivideo.com",
        "hdslb.com",
        "www.hdslb.com",
    }
    ALLOWED_VIDEO_HOSTS = {
        "b23.tv",
        "www.b23.tv",
        "bilibili.com",
        "www.bilibili.com",
        "m.bilibili.com",
    }

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.bilibili_sessdata = self.config.get("bilibili_sessdata", "").strip()
        self.bilibili_jct = self.config.get("bilibili_jct", "").strip()
        self.max_subtitle_length = self.get_int_config(
            "max_subtitle_length",
            default=20000,
            min_value=1000,
            max_value=100000,
        )
        self.llm_context_budget = self.get_int_config(
            "llm_context_budget",
            default=3000,
            min_value=512,
            max_value=16000,
        )
        self.page_upper_bound = self.get_int_config(
            "page_upper_bound",
            default=1000,
            min_value=1,
            max_value=100000,
        )
        self.request_timeout = self.get_int_config(
            "request_timeout",
            default=45,
            min_value=5,
            max_value=120,
        )
        self.short_link_timeout = self.get_int_config(
            "short_link_timeout",
            default=10,
            min_value=3,
            max_value=30,
        )
        self.short_link_redirect_limit = self.get_int_config(
            "short_link_redirect_limit",
            default=5,
            min_value=1,
            max_value=10,
        )
    
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
        p_match = self.PAGE_PARAM_PATTERN.search(video_input)
        if p_match:
            raw_page = int(p_match.group(1))
            # 防护：页码不合理时回退到 P1
            page_num = max(1, min(raw_page, self.page_upper_bound))
        
        yield event.plain_result(f"⏳ 检测到视频，正在获取详情...")

        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 2. 解析为 BV 号
            try:
                bvid = await self.resolve_video_id(session, video_input)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                logger.warning("Bilibili Summary stage=resolve_video_id timeout")
                yield event.plain_result("❌ 解析视频标识超时，请稍后重试。")
                return
            except Exception as e:
                logger.warning(f"Bilibili Summary stage=resolve_video_id error={type(e).__name__}")
                yield event.plain_result("❌ 解析视频标识失败，请检查链接格式。")
                return

            if not bvid:
                yield event.plain_result("❌ 无法解析视频 BV 号。\n请确保您发送的是一个有效的 B 站**视频**链接。")
                return

            # 3. 获取视频基本信息 (标题, aid, cid)
            try:
                video_info = await self.get_video_info(session, bvid, page_num)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Bilibili Summary stage=get_video_info bvid={bvid} error={type(e).__name__}")
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
            aid = video_info.get("aid")
            cid = video_info.get("cid")
            if not aid or not cid:
                logger.error(f"Bilibili Summary: 视频信息不完整 bvid={bvid} aid={aid} cid={cid}")
                yield event.plain_result("❌ 获取视频信息不完整，无法继续处理。")
                return

            try:
                subtitle_text_raw = await self.get_subtitle(
                    session,
                    aid,
                    cid,
                    bvid,
                    video_info.get("video_subtitles"),
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(
                    f"Bilibili Summary stage=get_subtitle bvid={bvid} "
                    f"aid={aid} cid={cid} error={type(e).__name__}"
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
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Bilibili Summary stage=llm_generate bvid={bvid} error={type(e).__name__}")
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

    def _flatten_strings(self, value: Any, max_depth: int = 5) -> List[str]:
        """递归提取容器中的字符串，用于兜底扫描链接，增加深度限制避免栈溢出。"""
        if max_depth <= 0:
            return []
        
        results: List[str] = []
        if isinstance(value, str):
            results.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                results.extend(self._flatten_strings(v, max_depth - 1))
        elif isinstance(value, list):
            for item in value:
                results.extend(self._flatten_strings(item, max_depth - 1))
        return results

    def extract_links_from_text(self, text: str) -> List[str]:
        """从文本中提取bilibili相关标识，按出现顺序返回"""
        url_patterns = [
            r'https?://(?:www\.|m\.)?bilibili\.com/video/[^\s，。）\)!！\?？;；：:、]+',
            r'https?://b23\.tv/[^\s，。）\)!！\?？;；：:、]+',
            r'(?i)\bbv[1-9A-HJ-NP-Za-km-z]{10}\b',
            r'(?i)\bav\d+\b',
        ]
        matches_with_pos: List[tuple] = []
        for pattern in url_patterns:
            for match in re.finditer(pattern, text):
                matched_text = match.group(0)
                if self.BV_TEXT_PATTERN.fullmatch(matched_text):
                    matched_text = matched_text.upper()
                matches_with_pos.append((match.start(), matched_text))

        matches_with_pos.sort(key=lambda x: x[0])
        links = [m[1] for m in matches_with_pos]
        return links

    def extract_video_id_from_url(self, video_input: str) -> Optional[str]:
        """优先从完整 bilibili URL 的路径中提取视频 ID，避免正则误命中。"""
        if not video_input.startswith(("http://", "https://")):
            return None

        parsed = urlparse(video_input)
        host = (parsed.hostname or "").lower()
        if host not in {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}:
            return None

        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 2 or path_parts[0] != "video":
            return None

        candidate = path_parts[1].strip()
        if self.BVID_STRICT_PATTERN.match(candidate):
            return candidate.upper()

        av_match = self.AV_SEARCH_PATTERN.fullmatch(candidate)
        if av_match:
            return f"av{av_match.group(1)}"

        return None

    def format_bilibili_api_error(self, scene: str, data: Dict[str, Any]) -> str:
        """将 B 站接口业务错误转换为用户可理解的错误信息。"""
        code = data.get("code")
        message = data.get("message") or data.get("msg") or "未知错误"
        logger.warning(
            f"Bilibili Summary: {scene} 返回业务错误 code={code} message={message}"
        )

        if code in {-400, -404, 62002}:
            return "视频不存在或链接解析出的标识无效。"
        if code in {-352, -412}:
            return "B站接口触发了风控或请求限制，请稍后重试。"
        if code == 403:
            return "当前账号或网络环境无权限访问该视频信息。"
        return f"获取视频信息失败：{message}"

    async def resolve_video_id(self, session: aiohttp.ClientSession, video_input: str) -> Optional[str]:
        """将各种输入格式统一解析为 BV 号，修复短链冗余与死循环风险"""
        # 1. 已经是 BV 号
        if self.BVID_STRICT_PATTERN.match(video_input):
            return video_input.upper()

        normalized_video_id = self.extract_video_id_from_url(video_input)
        if normalized_video_id:
            if normalized_video_id.upper().startswith("BV"):
                return normalized_video_id.upper()
            video_input = normalized_video_id
        
        # 2. 短链接 b23.tv - 手动逐跳跟随并校验目标域
        if 'b23.tv' in video_input:
            try:
                if not video_input.startswith('http'):
                    video_input = 'https://' + video_input

                current_url = video_input
                for _ in range(self.short_link_redirect_limit):
                    if not self.is_allowed_video_url(current_url):
                        logger.warning(f"Bilibili Summary: 短链跳转目标不在白名单内: {current_url}")
                        return None

                    async with session.get(
                        current_url,
                        allow_redirects=False,
                        ssl=True,
                        timeout=aiohttp.ClientTimeout(total=self.short_link_timeout),
                    ) as resp:
                        if resp.status in [301, 302, 303, 307, 308]:
                            location = resp.headers.get("Location", "")
                            if not location:
                                return None
                            current_url = urljoin(str(resp.url), location)
                            continue

                        if resp.status < 200 or resp.status >= 400:
                            logger.warning(f"Bilibili Summary: 短链接请求异常 status={resp.status}")
                            return None

                        final_url = str(resp.url)
                        if not self.is_allowed_video_url(final_url):
                            logger.warning(f"Bilibili Summary: 短链最终目标不在白名单内: {final_url}")
                            return None

                        bv_match = self.BVID_SEARCH_PATTERN.search(final_url)
                        if bv_match:
                            return bv_match.group(1).upper()

                        text = await resp.text()
                        bv_match = self.BVID_SEARCH_PATTERN.search(text)
                        if bv_match:
                            return bv_match.group(1).upper()
                        return None

                logger.warning("Bilibili Summary: 短链跳转次数超限")
                return None
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                logger.warning("Bilibili Summary: 短链接解析超时")
            except Exception as e:
                logger.warning(f"Bilibili Summary: 解析短链接异常 error={type(e).__name__}")
            return None

        # 3. 完整链接或 av 号
        bv_match = self.BVID_SEARCH_PATTERN.search(video_input)
        if bv_match:
            return bv_match.group(1).upper()

        av_match = self.AV_SEARCH_PATTERN.search(video_input)
        if av_match:
            aid = av_match.group(1)
            api_url = f"https://api.bilibili.com/x/web-interface/view?aid={aid}"
            async with session.get(api_url) as resp:
                data = await self.read_json_response(resp, "resolve_video_id(aid)")
                if not data:
                    return None
                if data.get('code') == 0:
                    return data['data'].get('bvid')
                self.format_bilibili_api_error("resolve_video_id(aid)", data)

        return None

    def build_bilibili_headers(self) -> Dict[str, str]:
        """构造统一的 B 站请求头。"""
        return dict(self.DEFAULT_HEADERS)

    def build_bilibili_cookies(self) -> Dict[str, str]:
        """根据配置构造统一的 B 站请求 Cookie。"""
        cookies: Dict[str, str] = {}
        if self.bilibili_sessdata:
            cookies["SESSDATA"] = self.bilibili_sessdata
        if self.bilibili_jct:
            cookies["bili_jct"] = self.bilibili_jct
        return cookies

    # ================= 核心抓取逻辑 =================

    async def get_video_info(self, session: aiohttp.ClientSession, bvid: str, page: int = 1) -> Optional[Dict[str, Any]]:
        """获取视频基本信息"""
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        headers = self.build_bilibili_headers()
        cookies = self.build_bilibili_cookies()

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
            return {
                "error": self.format_bilibili_api_error("get_video_info", data)
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
        headers = self.build_bilibili_headers()
        cookies = self.build_bilibili_cookies()

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
                        if not selected_url:
                            selected_url = subtitles[0].get('subtitle_url', '')
                elif data:
                    logger.warning(
                        "Bilibili Summary: get_subtitle(player/v2) 返回业务错误 "
                        f"code={data.get('code')} message={data.get('message') or data.get('msg')}"
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Bilibili Summary: player/v2 接口调用异常: {e}")

        # 2. 如果 player/v2 没拿到，尝试使用 fallback_subtitles (来自 view 接口)
        if not selected_url and fallback_subtitles:
            logger.info("Bilibili Summary: player/v2 未获取到字幕，尝试使用 view 接口备选字幕。")
            for sub in fallback_subtitles:
                if 'zh' in sub.get('lan', '').lower():
                    selected_url = sub.get('subtitle_url', '')
                    break
            if not selected_url:
                selected_url = fallback_subtitles[0].get('subtitle_url', '')

        if selected_url:
            if selected_url.startswith("//"):
                selected_url = "https:" + selected_url
            if not self.is_allowed_subtitle_url(selected_url):
                logger.warning(f"Bilibili Summary: 字幕URL不在白名单内: {selected_url}")
                return None
            return await self.download_subtitle(session, selected_url)
            
        return None

    def is_allowed_subtitle_url(self, url: str) -> bool:
        """限制字幕下载目标域，使用更严格的白名单验证，降低 SSRF 风险。"""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        
        # 显式白名单：完整域名或直接子域（不允许多级子域）
        allowed_hosts = {
            "bilibili.com",
            "www.bilibili.com",
            "m.bilibili.com",
            "bilivideo.com",
            "www.bilivideo.com",
            "hdslb.com",
            "www.hdslb.com",
        }
        
        if host in allowed_hosts:
            return True
        
        # 只允许一级子域（*.bilibili.com 但不允许 a.b.bilibili.com）
        for suffix in ["bilibili.com", "bilivideo.com", "hdslb.com"]:
            if host.endswith(f".{suffix}"):
                prefix = host[:-len(f".{suffix}")]
                # 确保前缀中没有点号（即仅一层子域）
                if "." not in prefix:
                    return True
        
        return False

    def is_allowed_video_url(self, url: str) -> bool:
        """限制短链解析过程中的目标域，避免被重定向到非预期站点。"""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        host = (parsed.hostname or "").lower()
        if not host:
            return False

        allowed_hosts = {
            "b23.tv",
            "www.bilibili.com",
            "m.bilibili.com",
            "bilibili.com",
            "www.b23.tv",
        }
        if host in allowed_hosts:
            return True

        return host.endswith(".bilibili.com")

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
        """根据LLM上下文预算动态截断摘要文本，智能截断避免中断句子。
        
        粗估：文字 -> token 的比例约为 1:0.4（中文偏少）。
        预留 prompt + output 空间，确保总token在安全范围内。
        """
        estimated_chars = self.llm_context_budget * 2.5
        estimated_chars = int(estimated_chars)

        if len(text) <= estimated_chars:
            return text

        truncated = text[:estimated_chars]
        
        # 智能截断：向后找到最近的句号、感叹号或问号，避免在句子中间截断
        sentence_ends = ["。", "！", "？", ".", "!", "?"]
        last_good_pos = estimated_chars
        for i in range(estimated_chars - 1, max(estimated_chars - 100, 0), -1):
            if truncated[i] in sentence_ends:
                last_good_pos = i + 1
                break
        
        truncated = truncated[:last_good_pos]
        
        logger.info(
            f"Bilibili Summary: 字幕长度超预算，"
            f"原长 {len(text)} 字，智能截断到 {last_good_pos} 字。"
        )
        return truncated + "（内容已截断）"

    def get_int_config(
        self,
        key: str,
        default: int,
        min_value: int,
        max_value: int,
    ) -> int:
        """读取并校验整数配置，异常值自动回退到安全范围。"""
        raw_value = self.config.get(key, default)
        try:
            parsed_value = int(raw_value)
        except (TypeError, ValueError):
            logger.warning(f"Bilibili Summary: 配置 {key} 非法，使用默认值 {default}")
            return default

        if parsed_value < min_value:
            logger.warning(f"Bilibili Summary: 配置 {key} 过小，提升到 {min_value}")
            return min_value
        if parsed_value > max_value:
            logger.warning(f"Bilibili Summary: 配置 {key} 过大，限制到 {max_value}")
            return max_value
        return parsed_value

    def clamp_prompt_text(self, prompt_template: str, title: str, text: str) -> str:
        """对最终 prompt 做长度硬约束，避免估算误差导致上下文超限。"""
        base_prompt = f"{prompt_template}\n\n【视频标题】: {title}\n\n【视频内容信息】:\n"
        max_prompt_chars = max(2048, min(self.llm_context_budget * 4, 48000))
        remaining_chars = max_prompt_chars - len(base_prompt)
        if remaining_chars <= 0:
            return base_prompt[:max_prompt_chars]

        if len(text) > remaining_chars:
            logger.info(
                "Bilibili Summary: 最终 prompt 超出硬限制，"
                f"正文从 {len(text)} 字裁剪到 {remaining_chars} 字。"
            )
            text = text[:remaining_chars]

        return f"{base_prompt}{text}"

    async def read_json_response(self, resp: aiohttp.ClientResponse, scene: str) -> Optional[Dict[str, Any]]:
        """统一处理HTTP状态与JSON解析异常，避免上游抖动放大。"""
        if resp.status < 200 or resp.status >= 300:
            logger.warning(f"Bilibili Summary: {scene} HTTP状态异常: {resp.status}")
            return None

        try:
            data = await resp.json(content_type=None)
        except asyncio.CancelledError:
            raise
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
        prompt = self.clamp_prompt_text(prompt_template, title, text)
        
        llm_resp = await self.context.llm_generate(chat_provider_id=provider_id, prompt=prompt)
        content = llm_resp.completion_text.strip()

        parsed = self.parse_llm_json(content)
        if parsed is None:
            logger.warning("Bilibili Summary: 大模型输出无有效JSON")
            raise Exception("大模型输出格式错误。")

        # 强化验证：core 必须是非空字符串
        core = parsed.get("core")
        if not isinstance(core, str) or not core.strip():
            logger.warning(f"Bilibili Summary: 大模型 core 验证失败 type={type(core)}")
            raise Exception("大模型输出缺少核心总结。")
        
        # 验证 points：必须是列表
        points_raw = parsed.get("points", [])
        if not isinstance(points_raw, list):
            logger.warning(f"Bilibili Summary: 大模型 points 类型错误 expected=list got={type(points_raw)}")
            points = []
        else:
            points = [p for p in points_raw if isinstance(p, str) and p.strip()]

        return {
            "core": core.strip(),
            "points": points,
        }

    def parse_llm_json(self, content: str) -> Optional[Dict[str, Any]]:
        """从LLM输出中提取JSON对象，仅接受严格JSON，使用嵌套括号匹配。"""
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        # 优先尝试直接按JSON解析。
        try:
            obj = json.loads(cleaned)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass

        # 使用嵌套括号匹配找JSON对象，正确处理字符串中的特殊字符。
        json_obj = self.extract_json_object(cleaned)
        if json_obj:
            candidate = self.sanitize_json_candidate(json_obj)
            try:
                obj = json.loads(candidate)
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                pass

        return None

    def extract_json_object(self, text: str) -> Optional[str]:
        """智能查找JSON对象边界，处理嵌套{}、字符串中的特殊字符。"""
        first_brace = text.find("{")
        if first_brace == -1:
            return None

        depth = 0
        in_string = False
        escape = False

        for i in range(first_brace, len(text)):
            char = text[i]

            if escape:
                escape = False
                continue

            if char == "\\":
                escape = True
                continue

            if char == '"' and not escape:
                in_string = not in_string
                continue

            if not in_string:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return text[first_brace:i + 1]

        return None

    def sanitize_json_candidate(self, candidate: str) -> str:
        """对候选JSON做最小修复：去除对象/数组结尾多余逗号。"""
        return re.sub(r",\s*([}\]])", r"\1", candidate)

    def format_summary(self, title: str, summary: dict) -> str:
        core = summary.get('core', '无')
        points = summary.get('points', [])
        if points:
            points_text = "\n".join([f"{i}. {point}" for i, point in enumerate(points, 1)])
            points_section = f"✨ 关键要点：\n{points_text}"
        else:
            points_section = "✨ 关键要点：暂无额外要点"
        return f"📺 【{title}】\n\n📌 核心内容：\n{core}\n\n{points_section}"
