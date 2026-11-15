"""Normalisation helpers shared by data auditing and curation.

The questionnaire exports contain many human-entered variants.  All
normalisation rules live here so that the audit report, the quality
re-scoring and the final dataset manifest use exactly the same semantics.
"""

from __future__ import annotations

import math
import re
from typing import Any

import numpy as np

# The only known keying error in the video questionnaire: subject 张涵博
# wrote 388.mp4 while the stimulus is 38.mp4.  Keep the alias explicit and
# auditable instead of silently applying a global "mod 120" rule.
VIDEO_ID_ALIASES = {"388": 38}

_ENDPOINT_MAP = {
    # 9-point valence anchors
    "非常不愉快": 1.0,
    "非常愉快": 9.0,
    # 9-point arousal anchors
    "非常平静": 1.0,
    "非常激烈": 9.0,
}

_RATER_NOISE = re.compile(r"[\s\u200b\u200c\u200d·•]+")


def canonical_stimulus_id(value: Any, kind: str = "video") -> str | None:
    """Return ``"<n>.mp4"`` / ``"<n>.mp3"`` for a free-form stimulus key.

    Returns ``None`` when no positive integer can be found or when the
    identifier falls outside the configured 1..120 stimulus range.
    """

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    match = re.search(r"(\d+)", text)
    if not match:
        return None
    number = int(match.group(1))
    if kind == "video":
        number = VIDEO_ID_ALIASES.get(str(number), number)
        suffix = ".mp4"
    elif kind == "audio":
        suffix = ".mp3"
    else:
        raise ValueError(f"unsupported stimulus kind: {kind!r}")
    if not 1 <= number <= 120:
        return None
    return f"{number}{suffix}"


def normalize_rater(value: Any) -> str:
    """Normalise a rater name without changing its identity."""

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return _RATER_NOISE.sub("", str(value)).strip()


def parse_rating(value: Any, scale: str = "valence") -> float | None:
    """Parse a 1..9 rating, including the questionnaire's text anchors.

    ``scale`` is used only for reporting; text anchors are globally unique
    enough to map without ambiguity.  Values outside 1..9 are rejected so
    that coding errors are surfaced instead of silently clipped.
    """

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
    else:
        text = str(value).strip()
        if text in _ENDPOINT_MAP:
            return _ENDPOINT_MAP[text]
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if not match:
            return None
        number = float(match.group(0))
    if not 1.0 <= number <= 9.0:
        return None
    return number


def parse_clock_seconds(value: Any) -> float | None:
    """Parse a duration expressed as a clock string or an Excel fraction.

    The material spreadsheet stores some durations as ``0.07603`` (a day
    fraction) and the mapping export stores others as ``"1:43"`` or the
    Excel-derived ``"01:10:00"``.  The latter is an h:mm:ss rendering of a
    one-minute segment, so all clock strings are interpreted literally as
    h:mm:ss / mm:ss.
    """

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        if 0.0 <= number < 1.0:
            return number * 86_400.0
        return number
    text = str(value).strip().replace("：", ":")
    if not text:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        number = float(text)
        if 0.0 <= number < 1.0:
            return number * 86_400.0
        return number
    parts = text.split(":")
    try:
        nums = [float(part) for part in parts]
    except ValueError:
        return None
    if len(nums) == 2:
        minutes, seconds = nums
        return minutes * 60.0 + seconds
    if len(nums) == 3:
        hours, minutes, seconds = nums
        return hours * 3600.0 + minutes * 60.0 + seconds
    return None


_ISSUE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("损坏", ("损坏", "文件坏", "打不开")),
    ("无法播放", ("无法播放", "播放不了", "不能播放")),
    ("不同步", ("不同步", "声画不一")),
    ("加速", ("加速", "倍速", "慢倍速", "变速")),
    ("模糊", ("模糊", "画质", "清晰度", "不清晰")),
    ("杂音", ("杂音", "噪音", "音频", "声音", "听不清", "录音")),
    ("音量", ("过大", "过小", "音量")),
    ("卡顿", ("卡顿", "卡住")),
    ("内容", ("难以理解", "看不懂", "不理解", "字幕", "内容")),
)

ISSUE_SEVERITY: dict[str, float] = {
    "损坏": 1.00,
    "无法播放": 1.00,
    "不同步": 0.90,
    "加速": 0.90,
    "模糊": 0.80,
    "杂音": 0.65,
    "音量": 0.55,
    "卡顿": 0.60,
    "内容": 0.60,
    "其他": 0.50,
}


def classify_issue(text: Any) -> str | None:
    """Map a free-text playback problem to a coarse, auditable tag."""

    if text is None or (isinstance(text, float) and math.isnan(text)):
        return None
    value = str(text).strip()
    if value in {"", "没有", "无", "没有问题", "nan"}:
        return None
    for tag, keywords in _ISSUE_RULES:
        if any(keyword in value for keyword in keywords):
            return tag
    return "其他"


def parse_issue_cell(value: Any) -> tuple[float, tuple[str, ...], bool]:
    """Parse the multi-select playback-problem column.

    Returns ``(severity_index, tags, contradictory)`` where
    ``severity_index = 1 - prod(1 - severity)`` for all selected issues.
    """

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0, (), False
    text = str(value).strip()
    if text in {"", "没有问题", "nan"}:
        return 0.0, (), False
    parts = [part.strip() for part in re.split(r"[┋|]", text) if part.strip()]
    has_none = "没有问题" in parts
    tags: list[str] = []
    for part in parts:
        if part == "没有问题":
            continue
        detail = re.search(r"〖(.*?)〗", part)
        tag = classify_issue(detail.group(1) if detail else part)
        if tag and tag not in tags:
            tags.append(tag)
    if not tags:
        return 0.0, (), has_none
    survival = 1.0
    for tag in tags:
        survival *= 1.0 - ISSUE_SEVERITY.get(tag, 0.5)
    severity = 1.0 - survival
    if has_none:
        severity *= 0.9
    return round(severity, 4), tuple(tags), has_none


def parse_free_text_issue(value: Any) -> tuple[str | None, str]:
    """Extract the bracketed detail from the open-ended Q12 answer."""

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None, ""
    text = str(value).strip()
    if text in {"", "没有", "nan"}:
        return None, ""
    detail = re.search(r"〖(.*?)〗", text)
    clean = detail.group(1).strip() if detail else text
    return classify_issue(clean), clean
