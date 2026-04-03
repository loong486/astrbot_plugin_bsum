import re
from typing import List, Tuple, Any

from .models import SummaryResult

BV_TEXT_PATTERN = re.compile(r"(?i)bv[1-9A-HJ-NP-Za-km-z]{10}")

_URL_PATTERNS = [
    r'https?://(?:www\.|m\.)?bilibili\.com/video/[^\s\uff0c\u3002\uff09\)!！\?？;；：:、]+',
    r'https?://b23\.tv/[^\s\uff0c\u3002\uff09\)!！\?？;；：:、]+',
    r'(?i)\bbv[1-9A-HJ-NP-Za-km-z]{10}\b',
    r'(?i)\bav\d+\b',
]


def extract_links_from_text(text: str) -> List[str]:
    """从纯文本中按位置顺序提取所有 bilibili 标识（URL / BV号 / av号）。"""
    hits: List[Tuple[int, str]] = []
    for pat in _URL_PATTERNS:
        for m in re.finditer(pat, text):
            raw = m.group(0)
            # 规范 BV 前缀大小写
            if BV_TEXT_PATTERN.fullmatch(raw):
                raw = f"BV{raw[2:]}"
            hits.append((m.start(), raw))
    hits.sort(key=lambda x: x[0])
    # 按出现顺序去重
    seen: set = set()
    result: List[str] = []
    for _, val in hits:
        if val not in seen:
            seen.add(val)
            result.append(val)
    return result


def flatten_strings(value: Any, max_depth: int = 5) -> List[str]:
    """递归提取容器（dict/list）中的所有字符串，深度受限以防栈溢出。"""
    if max_depth <= 0:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        results: List[str] = []
        for v in value.values():
            results.extend(flatten_strings(v, max_depth - 1))
        return results
    if isinstance(value, list):
        results = []
        for item in value:
            results.extend(flatten_strings(item, max_depth - 1))
        return results
    return []


def format_summary(title: str, result: SummaryResult) -> str:
    """将视频标题与总结结果格式化为最终消息文本。"""
    if result.points:
        pts = "\n".join(f"{i}. {p}" for i, p in enumerate(result.points, 1))
        pts_section = f"✨ 关键要点：\n{pts}"
    else:
        pts_section = "✨ 关键要点：暂无额外要点"
    return f"📺 【{title}】\n\n📌 核心内容：\n{result.core}\n\n{pts_section}"
