import re
import asyncio
from typing import Optional
from urllib.parse import urlparse, urljoin

import aiohttp
from astrbot.api import logger

BVID_STRICT = re.compile(r"(?i)^BV[1-9A-HJ-NP-Za-km-z]{10}$")
BVID_SEARCH = re.compile(r"(?i)(BV[1-9A-HJ-NP-Za-km-z]{10})")
AV_SEARCH   = re.compile(r"(?i)\bav(\d+)\b")

ALLOWED_VIDEO_HOSTS = {
    "b23.tv",
    "www.b23.tv",
    "bilibili.com",
    "www.bilibili.com",
    "m.bilibili.com",
}


def normalize_bv(bvid: str) -> str:
    """规范 BV 前缀大小写，保留后续字符原始大小写。"""
    return f"BV{bvid[2:]}" if len(bvid) >= 2 else bvid


def is_allowed_video_url(url: str) -> bool:
    """短链白名单校验：只允许跳转到已知 B 站域名，防止 SSRF。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    return host in ALLOWED_VIDEO_HOSTS or host.endswith(".bilibili.com")


def extract_bv_from_url_path(url: str) -> Optional[str]:
    """从完整 bilibili URL 路径中提取 BV / av 标识，避免正则误命中。"""
    if not url.startswith(("http://", "https://")):
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or parts[0] != "video":
        return None
    candidate = parts[1].strip()
    if BVID_STRICT.match(candidate):
        return normalize_bv(candidate)
    m = AV_SEARCH.fullmatch(candidate)
    return f"av{m.group(1)}" if m else None


async def _resolve_short_link(
    session: aiohttp.ClientSession,
    url: str,
    *,
    redirect_limit: int,
    timeout_secs: int,
    headers: dict,
) -> Optional[str]:
    """手动逐跳跟随 b23.tv 短链，返回 BV 号；所有中间跳均经白名单校验。"""
    if not url.startswith("http"):
        url = "https://" + url

    current = url
    timeout = aiohttp.ClientTimeout(total=timeout_secs)

    for _ in range(redirect_limit):
        if not is_allowed_video_url(current):
            logger.warning(f"[bilisu/resolver] 短链跳转目标不在白名单: {current}")
            return None

        # 当前 URL 已是 bilibili 视频地址，直接提取 BV
        if "b23.tv" not in current:
            bv = BVID_SEARCH.search(current)
            if bv:
                return normalize_bv(bv.group(1))

        try:
            async with session.get(
                current,
                allow_redirects=False,
                headers=headers,
                ssl=True,
                timeout=timeout,
            ) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("Location", "")
                    if not loc:
                        return None
                    current = urljoin(str(resp.url), loc)
                    continue

                if resp.status < 200 or resp.status >= 400:
                    logger.warning(
                        f"[bilisu/resolver] 短链请求异常 status={resp.status}"
                    )
                    return None

                final = str(resp.url)
                if not is_allowed_video_url(final):
                    logger.warning(
                        f"[bilisu/resolver] 短链最终目标不在白名单: {final}"
                    )
                    return None

                bv = BVID_SEARCH.search(final)
                if bv:
                    return normalize_bv(bv.group(1))

                text = await resp.text()
                bv = BVID_SEARCH.search(text)
                return normalize_bv(bv.group(1)) if bv else None

        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            logger.warning("[bilisu/resolver] 短链解析超时")
            return None
        except Exception as e:
            logger.warning(f"[bilisu/resolver] 短链解析异常: {type(e).__name__}")
            return None

    logger.warning("[bilisu/resolver] 短链跳转次数超限")
    return None


async def resolve_video_id(
    video_input: str,
    session: aiohttp.ClientSession,
    *,
    redirect_limit: int,
    short_timeout: int,
    headers: dict,
) -> Optional[str]:
    """将各种输入格式统一解析为 BV 号（或 av<数字>）。

    解析顺序：
      1. 已是 BV 号 → 直接返回
      2. 完整 bilibili URL → 从路径提取
      3. b23.tv 短链 → 逐跳跟随
      4. 文本中含 BV → 正则提取
      5. av 号 → 调用 B 站 API 换取 bvid
    """
    # 1. 已是 BV 号
    if BVID_STRICT.match(video_input):
        return normalize_bv(video_input)

    # 2. 完整 bilibili URL
    from_path = extract_bv_from_url_path(video_input)
    if from_path:
        if from_path.lower().startswith("bv"):
            return normalize_bv(from_path)
        # av<数字>，跳到 av 分支
        video_input = from_path

    # 3. 短链
    if "b23.tv" in video_input:
        return await _resolve_short_link(
            session,
            video_input,
            redirect_limit=redirect_limit,
            timeout_secs=short_timeout,
            headers=headers,
        )

    # 4. 文本内含 BV
    bv = BVID_SEARCH.search(video_input)
    if bv:
        return normalize_bv(bv.group(1))

    # 5. av 号
    av = AV_SEARCH.search(video_input)
    if av:
        api_url = (
            f"https://api.bilibili.com/x/web-interface/view?aid={av.group(1)}"
        )
        try:
            async with session.get(api_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    if isinstance(data, dict) and data.get("code") == 0:
                        bvid = data["data"].get("bvid")
                        return normalize_bv(bvid) if bvid else None
                    logger.warning(
                        f"[bilisu/resolver] av→bv API 返回错误 "
                        f"code={data.get('code') if isinstance(data, dict) else 'N/A'}"
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[bilisu/resolver] av→bv 查询异常: {type(e).__name__}")

    return None
