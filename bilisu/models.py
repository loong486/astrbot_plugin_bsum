from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class VideoInfo:
    aid: int
    cid: int
    title: str
    desc: str
    video_subtitles: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SummaryResult:
    core: str
    points: List[str] = field(default_factory=list)
