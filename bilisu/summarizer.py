import re
import json
from typing import Optional, Dict, Any

from astrbot.api import logger
from astrbot.api.all import AstrMessageEvent

from .config import PluginConfig
from .models import SummaryResult


class Summarizer:
    """封装 LLM 调用、JSON 解析与结果校验。"""

    def __init__(self, context: Any, cfg: PluginConfig) -> None:
        self._context = context
        self._cfg = cfg

    # ── 公开接口 ─────────────────────────────────────────────

    async def summarize(
        self, event: AstrMessageEvent, subtitle_text: str, title: str
    ) -> SummaryResult:
        """调用 LLM 生成总结，返回 SummaryResult；失败时抛出异常。"""
        text = self._budget_text(subtitle_text)
        prompt = self._build_prompt(title, text)

        provider_id = self._cfg.llm_provider or await (
            self._context.get_current_chat_provider_id(umo=event.unified_msg_origin)
        )

        llm_resp = await self._context.llm_generate(
            chat_provider_id=provider_id, prompt=prompt
        )
        content = llm_resp.completion_text.strip()

        parsed = self._parse_llm_json(content)
        if parsed is None:
            logger.warning("[bilisu/summarizer] 大模型输出无有效JSON")
            raise ValueError("大模型输出格式错误。")

        core = parsed.get("core")
        if not isinstance(core, str) or not core.strip():
            logger.warning(
                f"[bilisu/summarizer] core 验证失败 type={type(core)}"
            )
            raise ValueError("大模型输出缺少核心总结。")

        points_raw = parsed.get("points", [])
        points = (
            [p for p in points_raw if isinstance(p, str) and p.strip()]
            if isinstance(points_raw, list)
            else []
        )

        return SummaryResult(core=core.strip(), points=points)

    # ── 内部辅助 ─────────────────────────────────────────────

    def _budget_text(self, text: str) -> str:
        estimated_chars = int(self._cfg.llm_context_budget * 2.5)
        if len(text) <= estimated_chars:
            return text

        truncated = text[:estimated_chars]
        sentence_ends = ("。", "！", "？", ".", "!", "?")
        cut = estimated_chars
        for i in range(estimated_chars - 1, max(estimated_chars - 100, 0), -1):
            if truncated[i] in sentence_ends:
                cut = i + 1
                break

        logger.info(
            f"[bilisu/summarizer] 字幕超预算，"
            f"原长 {len(text)} 字，截断到 {cut} 字。"
        )
        return truncated[:cut] + "（内容已截断）"

    def _build_prompt(self, title: str, text: str) -> str:
        template = self._cfg.prompt_template
        base = f"{template}\n\n【视频标题】: {title}\n\n【视频内容信息】:\n"
        max_chars = max(2048, min(self._cfg.llm_context_budget * 4, 48000))
        remaining = max_chars - len(base)
        if remaining <= 0:
            return base[:max_chars]
        if len(text) > remaining:
            logger.info(
                f"[bilisu/summarizer] prompt 超硬限制，"
                f"正文从 {len(text)} 字裁剪到 {remaining} 字。"
            )
            text = text[:remaining]
        return f"{base}{text}"

    @staticmethod
    def _parse_llm_json(content: str) -> Optional[Dict[str, Any]]:
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            obj = json.loads(cleaned)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass

        json_str = Summarizer._extract_json_object(cleaned)
        if json_str:
            json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
            try:
                obj = json.loads(json_str)
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _extract_json_object(text: str) -> Optional[str]:
        first = text.find("{")
        if first == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(first, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if not in_string:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return text[first : i + 1]
        return None
