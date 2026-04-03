import asyncio
from typing import List

import aiohttp
from astrbot.api import logger
from astrbot.api.all import AstrMessageEvent, Context, Star, register
from astrbot.api.event import filter
import astrbot.api.message_components as Comp

from bilisu.api import BilibiliAPI
from bilisu.config import PluginConfig
from bilisu.formatter import extract_links_from_text, flatten_strings, format_summary
from bilisu.summarizer import Summarizer


@register("bilibili_summary", "loong486", "B站视频总结插件", "2.0.0")
class BilibiliSummaryPlugin(Star):

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.cfg = PluginConfig.from_dict(config)

    # ── 触发器 ───────────────────────────────────────────────

    @filter.regex(
        r"(?i)(?:(?:www\.|m\.)?bilibili\.com/video/"
        r"|b23\.tv/"
        r"|\bBV[1-9A-HJ-NP-Za-km-z]{10}\b"
        r"|\bav\d+\b)"
    )
    async def bilibili_summary(self, event: AstrMessageEvent):
        """B站视频总结：自动识别链接/BV号/短链触发。"""
        candidates = self._extract_links(event)
        if not candidates:
            return

        yield event.plain_result("⏳ 检测到视频，正在获取详情...")

        timeout = aiohttp.ClientTimeout(total=self.cfg.request_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            api = BilibiliAPI(session, self.cfg)
            summarizer = Summarizer(self.context, self.cfg)

            # ① 解析视频信息
            video_info, bvid, page_num = await api.pick_first_valid(candidates)

            if not video_info:
                yield event.plain_result(
                    "❌ 无法解析视频 BV 号。\n请确保您发送的是一个有效的 B 站**视频**链接。"
                )
                return

            yield event.plain_result(
                f"✅ 成功获取视频: {video_info.title}\n正在寻找可用字幕..."
            )

            if not video_info.aid or not video_info.cid:
                logger.error(
                    f"[bilisu] 视频信息不完整 bvid={bvid} "
                    f"aid={video_info.aid} cid={video_info.cid}"
                )
                yield event.plain_result("❌ 获取视频信息不完整，无法继续处理。")
                return

            # ② 获取字幕
            try:
                subtitle = await api.get_subtitle(video_info)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(
                    f"[bilisu] get_subtitle bvid={bvid} error={type(e).__name__}"
                )
                yield event.plain_result("❌ 拉取字幕失败，请稍后再试。")
                return

            if not subtitle:
                yield event.plain_result("❌ 该视频无可用字幕。")
                return

            yield event.plain_result(
                f"✅ 字幕下载成功 (约 {len(subtitle)} 字)\n正在调用 AI 进行总结..."
            )

            # ③ LLM 总结
            try:
                result = await summarizer.summarize(event, subtitle, video_info.title)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(
                    f"[bilisu] llm_generate bvid={bvid} error={type(e).__name__}"
                )
                yield event.plain_result("❌ AI 总结生成失败，请稍后重试。")
                return

            yield event.plain_result("🚀 AI 总结完成，正在生成卡片...")

        # ④ 输出结果（在 session 关闭后）
        yield event.plain_result(format_summary(video_info.title, result))

    # ── 链接提取 ─────────────────────────────────────────────

    def _extract_links(self, event: AstrMessageEvent) -> List[str]:
        """从消息各组件中提取所有 bilibili 相关标识，按优先级去重。"""
        plain: List[str] = []
        reply: List[str] = []
        other: List[str] = []

        for component in event.message_obj.message:
            if isinstance(component, Comp.Plain):
                plain.extend(extract_links_from_text(component.text))
            elif isinstance(component, Comp.Reply):
                if hasattr(component, "text") and component.text:
                    reply.extend(extract_links_from_text(component.text))
            else:
                for attr in ("url", "text", "content", "title", "desc", "data"):
                    value = getattr(component, attr, None)
                    if value is not None:
                        for s in flatten_strings(
                            value, self.cfg.max_component_scan_depth
                        ):
                            other.extend(extract_links_from_text(s))

        seen: set = set()
        result: List[str] = []
        for link in plain + reply + other:
            if link not in seen:
                seen.add(link)
                result.append(link)
        return result
