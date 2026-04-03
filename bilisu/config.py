from dataclasses import dataclass
from astrbot.api import logger

_DEFAULT_PROMPT = (
    '你是一个文本阅读和总结专家。我会直接为你提供视频的标题以及完整的字幕文本。'
    '请你完全根据我提供的这些文本内容进行总结，不要尝试访问视频或进行任何解析。'
    '即使内容较短，也请尽力提炼。'
    '请严格以JSON格式返回: {"core": "<核心总结文字>", "points": ["<要点1>", "<要点2>"]}'
)


@dataclass
class PluginConfig:
    bilibili_sessdata: str
    bilibili_jct: str
    llm_provider: str
    prompt_template: str
    max_subtitle_length: int
    max_component_scan_depth: int
    llm_context_budget: int
    page_upper_bound: int
    request_timeout: int
    short_link_timeout: int
    short_link_redirect_limit: int

    @staticmethod
    def _get_int(raw: dict, key: str, default: int, lo: int, hi: int) -> int:
        try:
            v = int(raw.get(key, default))
        except (TypeError, ValueError):
            logger.warning(f"[bilisu/config] 配置 {key} 非法，回退到 {default}")
            return default
        if v < lo:
            logger.warning(f"[bilisu/config] 配置 {key} 过小，提升到 {lo}")
            return lo
        if v > hi:
            logger.warning(f"[bilisu/config] 配置 {key} 过大，限制到 {hi}")
            return hi
        return v

    @classmethod
    def from_dict(cls, raw: dict) -> "PluginConfig":
        g = cls._get_int
        return cls(
            bilibili_sessdata=raw.get("bilibili_sessdata", "").strip(),
            bilibili_jct=raw.get("bilibili_jct", "").strip(),
            llm_provider=raw.get("llm_provider", ""),
            prompt_template=raw.get("prompt_template", _DEFAULT_PROMPT),
            max_subtitle_length=g(raw, "max_subtitle_length", 20000, 1000, 100000),
            max_component_scan_depth=g(raw, "max_component_scan_depth", 5, 1, 20),
            llm_context_budget=g(raw, "llm_context_budget", 3000, 512, 16000),
            page_upper_bound=g(raw, "page_upper_bound", 1000, 1, 100000),
            request_timeout=g(raw, "request_timeout", 45, 5, 120),
            short_link_timeout=g(raw, "short_link_timeout", 10, 3, 30),
            short_link_redirect_limit=g(raw, "short_link_redirect_limit", 5, 1, 10),
        )
