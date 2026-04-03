import asyncio
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse

import aiohttp
from astrbot.api import logger

from .config import PluginConfig
from .models import VideoInfo
from .resolver import resolve_video_id

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}

_ALLOWED_SUBTITLE_HOSTS = {
    "bilibili.com",
    "www.bilibili.com",
    "m.bilibili.com",
    "bilivideo.com",
    "www.bilivideo.com",
    "hdslb.com",
    "www.hdslb.com",
}


def _is_allowed_subtitle_url(url: str) -> bool:
    """字幕下载白名单校验，防止 SSRF。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in _ALLOWED_SUBTITLE_HOSTS:
        return True
    for suffix in ("bilibili.com", "bilivideo.com", "hdslb.com"):
        if host.endswith(f".{suffix}"):
            prefix = host[: -len(f".{suffix}")]
            if "." not in prefix:
                return True
    return False


def _pick_best_subtitle(subtitles: List[Dict[str, Any]]) -> str:
    """从字幕列表中按优先级挑选最佳字幕 URL。

    优先级（高→低）：
      1. 人工 CC 中文（ai_type=0, lan 含 zh）
      2. 人工 CC 任意语言（ai_type=0）
      3. AI 生成中文（ai_type!=0, lan 含 zh）
      4. 列表首项

    Bilibili player/v2 字幕对象中 ai_type=0 表示人工提交，
    ai_type=1 表示 AI 自动生成；缺失该字段时视同人工。
    """
    manual_zh = manual_any = ai_zh = None
    for sub in subtitles:
        url = sub.get("subtitle_url", "")
        if not url:
            continue
        ai_type = sub.get("ai_type", 0)
        lan = sub.get("lan", "").lower()
        is_manual = (ai_type == 0)
        is_zh = ("zh" in lan)

        if is_manual and is_zh and manual_zh is None:
            manual_zh = url
        if is_manual and manual_any is None:
            manual_any = url
        if not is_manual and is_zh and ai_zh is None:
            ai_zh = url

    return manual_zh or manual_any or ai_zh or subtitles[0].get("subtitle_url", "")


class BilibiliAPI:
    """封装所有对 B 站外部 HTTP API 的调用。"""

    def __init__(self, session: aiohttp.ClientSession, cfg: PluginConfig) -> None:
        self._session = session
        self._cfg = cfg

    # ── 请求辅助 ─────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        return dict(_DEFAULT_HEADERS)

    def _cookies(self) -> Dict[str, str]:
        cookies: Dict[str, str] = {}
        if self._cfg.bilibili_sessdata:
            cookies["SESSDATA"] = self._cfg.bilibili_sessdata
        if self._cfg.bilibili_jct:
            cookies["bili_jct"] = self._cfg.bilibili_jct
        return cookies

    async def _read_json(
        self, resp: aiohttp.ClientResponse, scene: str
    ) -> Optional[Dict[str, Any]]:
        if resp.status < 200 or resp.status >= 300:
            logger.warning(f"[bilisu/api] {scene} HTTP 异常: {resp.status}")
            return None
        try:
            data = await resp.json(content_type=None)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            text = await resp.text()
            logger.warning(
                f"[bilisu/api] {scene} JSON 解析失败: {e}; 响应片段: {text[:200]}"
            )
            return None
        if not isinstance(data, dict):
            logger.warning(f"[bilisu/api] {scene} 返回结构异常，非 dict。")
            return None
        return data

    def _fmt_api_error(self, scene: str, data: Dict[str, Any]) -> str:
        code = data.get("code")
        message = data.get("message") or data.get("msg") or "未知错误"
        logger.warning(
            f"[bilisu/api] {scene} 业务错误 code={code} message={message}"
        )
        if code in {-400, -404, 62002}:
            return "视频不存在或链接解析出的标识无效。"
        if code in {-352, -412}:
            return "B站接口触发了风控或请求限制，请稍后重试。"
        if code == 403:
            return "当前账号或网络环境无权限访问该视频信息。"
        return f"获取视频信息失败：{message}"

    # ── 视频信息 ─────────────────────────────────────────────

    async def get_video_info(
        self, bvid: str, page: int = 1
    ) -> Optional[Dict[str, Any]]:
        """返回 VideoInfo dict（成功）或含 "error" 键的 dict（业务失败）或 None（网络失败）。"""
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        async with self._session.get(
            api_url, headers=self._headers(), cookies=self._cookies()
        ) as resp:
            data = await self._read_json(resp, "get_video_info")
            if not data:
                return None
            if data.get("code") == 0:
                vdata = data["data"]
                pages = vdata.get("pages", [])
                cid = vdata.get("cid")
                title = vdata.get("title", "")
                page = max(1, page)

                if pages and page > len(pages):
                    return {"error": f"请求分P超出范围：该视频仅有 {len(pages)} P。"}

                if len(pages) >= page:
                    page_data = pages[page - 1]
                    cid = page_data.get("cid")
                    if len(pages) > 1:
                        title = f"{title} (P{page} {page_data.get('part', '')})"

                video_subtitles = vdata.get("subtitle", {}).get("list", [])
                return {
                    "aid": int(vdata.get("aid", 0)),
                    "cid": cid,
                    "title": title,
                    "desc": vdata.get("desc", ""),
                    "video_subtitles": video_subtitles,
                }
            return {"error": self._fmt_api_error("get_video_info", data)}

    # ── 字幕 ─────────────────────────────────────────────────

    async def get_subtitle(self, video_info: VideoInfo) -> Optional[str]:
        """获取字幕纯文本；优先 player/v2，回退 view 接口字幕列表。"""
        aid = video_info.aid
        cid = video_info.cid
        bvid_hint = ""  # bvid 仅作日志用，不影响逻辑

        url = (
            f"https://api.bilibili.com/x/player/v2"
            f"?aid={aid}&cid={cid}"
        )
        selected_url = ""

        try:
            async with self._session.get(
                url, headers=self._headers(), cookies=self._cookies()
            ) as resp:
                data = await self._read_json(resp, "get_subtitle(player/v2)")
                if data and data.get("code") == 0:
                    subtitles: List[Dict[str, Any]] = (
                        data.get("data", {})
                        .get("subtitle", {})
                        .get("subtitles", [])
                    )
                    if subtitles:
                        selected_url = _pick_best_subtitle(subtitles)
                elif data:
                    logger.warning(
                        f"[bilisu/api] player/v2 业务错误 "
                        f"code={data.get('code')} message={data.get('message') or data.get('msg')}"
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[bilisu/api] player/v2 调用异常: {e}")

        # 回退到 view 接口字幕
        if not selected_url and video_info.video_subtitles:
            logger.info("[bilisu/api] player/v2 无字幕，尝试 view 接口备选字幕。")
            selected_url = _pick_best_subtitle(video_info.video_subtitles)

        if not selected_url:
            return None

        if selected_url.startswith("//"):
            selected_url = "https:" + selected_url

        if not _is_allowed_subtitle_url(selected_url):
            logger.warning(f"[bilisu/api] 字幕URL不在白名单: {selected_url}")
            return None

        return await self._download_subtitle(selected_url)

    async def _download_subtitle(self, url: str) -> Optional[str]:
        async with self._session.get(url) as resp:
            data = await self._read_json(resp, "download_subtitle")
            if not data:
                return None
            body = data.get("body", [])
            if not isinstance(body, list):
                logger.warning("[bilisu/api] 字幕 body 结构异常，非 list。")
                return None
            texts = [
                item["content"]
                for item in body
                if isinstance(item, dict)
                and isinstance(item.get("content"), str)
                and item["content"].strip()
            ]
            if not texts:
                return None
            full_text = " ".join(texts)
            max_len = self._cfg.max_subtitle_length
            if len(full_text) > max_len:
                full_text = full_text[:max_len] + "..."
            return full_text

    # ── 批量候选解析 ─────────────────────────────────────────

    async def pick_first_valid(
        self, candidates: List[str]
    ) -> Tuple[Optional[VideoInfo], Optional[str], int]:
        """遍历候选标识，返回第一个成功的 (VideoInfo, bvid, page_num)。"""
        from .formatter import extract_links_from_text  # 避免循环导入
        import re as _re

        PAGE_PARAM = _re.compile(r"[?&]p=(\d+)")

        last_error: Optional[str] = None
        had_resolve_error = False

        for candidate in candidates:
            logger.info(f"[bilisu/api] 尝试候选: {candidate}")

            # 提取分P号
            p_match = PAGE_PARAM.search(candidate)
            page_num = 1
            if p_match:
                raw_p = int(p_match.group(1))
                page_num = max(1, min(raw_p, self._cfg.page_upper_bound))

            try:
                bvid = await resolve_video_id(
                    candidate,
                    self._session,
                    redirect_limit=self._cfg.short_link_redirect_limit,
                    short_timeout=self._cfg.short_link_timeout,
                    headers=self._headers(),
                )
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                logger.warning("[bilisu/api] resolve_video_id 超时")
                had_resolve_error = True
                continue
            except Exception as e:
                logger.warning(
                    f"[bilisu/api] resolve_video_id 异常: {type(e).__name__}"
                )
                had_resolve_error = True
                continue

            if not bvid:
                continue

            try:
                info_dict = await self.get_video_info(bvid, page_num)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(
                    f"[bilisu/api] get_video_info bvid={bvid} 异常: {type(e).__name__}"
                )
                had_resolve_error = True
                continue

            if not info_dict:
                continue

            if info_dict.get("error"):
                last_error = info_dict["error"]
                continue

            video_info = VideoInfo(
                aid=info_dict["aid"],
                cid=info_dict["cid"],
                title=info_dict["title"],
                desc=info_dict.get("desc", ""),
                video_subtitles=info_dict.get("video_subtitles", []),
            )
            return video_info, bvid, page_num

        return None, None, 1
