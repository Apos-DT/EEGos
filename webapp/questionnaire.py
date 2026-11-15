"""问卷题目 schema：定义、校验、问卷星表头推断与默认量表模板。

设计要点
--------
* **role 是核心**：题目可以任意增删改，但标注了 role 的字段仍能被
  ``eeg_emostudio.audit.normalize`` 的清洗/质量评分逻辑识别，也能导出成
  问卷星兼容格式。未标注 role 的题进入 ``answers`` 但不参与质量计算。
* **schema 版本化**：问卷定义保存 ``schema_version`` 与 ``schema_hash``，
  每份答卷也记录二者；改题之后历史答卷仍能追溯当时使用的量表。
* **平台元数据**：问卷星导出的 7 个系统列单独建模，IP 只保留地区与
  不可逆哈希，满足「被试身份伪匿名化」要求。

本模块只依赖标准库与项目中已有的 normalize 函数，不引入新依赖。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from eeg_emostudio.audit.normalize import (
    canonical_stimulus_id,
    normalize_rater,
    parse_free_text_issue,
    parse_issue_cell,
    parse_rating,
)

QUESTION_TYPES = ("text", "rating", "single", "multiple", "textarea")
QUESTION_TYPE_LABELS = {
    "text": "单行填空",
    "rating": "量表评分",
    "single": "单选",
    "multiple": "多选",
    "textarea": "多行文本",
}

ROLES = {
    "": "不参与分析（自定义题）",
    "rater": "评分者姓名",
    "stimulus": "刺激编号",
    "valence": "效价 1–9",
    "arousal": "唤醒度 1–9",
    "clarity": "主导情绪明确度",
    "emotion": "主导情绪类别",
    "coverage": "情绪覆盖时长",
    "stability": "情绪稳定性 / 反转",
    "familiarity": "素材熟悉度",
    "comprehension": "片段可理解性",
    "issues": "播放问题（多选）",
    "other": "其他影响因素",
    "intensity": "情绪强度",
    "discrete": "离散情绪",
    "note": "备注",
}

# 问卷星固定的平台元数据列，按名称识别而非位置（SRS A-01：字段可能变化）
PLATFORM_COLUMNS = {
    "序号": "serial_no",
    "提交答卷时间": "submitted_at",
    "所用时间": "duration_s",
    "来源": "source",
    "来源详情": "source_detail",
    "来自IP": "ip",
    "总分": "total_score",
}
PLATFORM_OUTPUT_COLUMNS = list(PLATFORM_COLUMNS.keys())

# 顺序敏感：具体关键词必须排在「主导情绪」这类泛化词之前
_ROLE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("姓名",), "rater"),
    (("编号",), "stimulus"),
    (("效价",), "valence"),
    (("唤醒",), "arousal"),
    (("熟悉",), "familiarity"),
    (("理解",), "comprehension"),
    (("覆盖",), "coverage"),
    (("多长时间",), "coverage"),
    (("反转",), "stability"),
    (("变化",), "stability"),
    (("播放过程",), "issues"),
    (("以下问题",), "issues"),
    (("未被上述",), "other"),
    (("是否形成",), "clarity"),
    (("明确、突出",), "clarity"),
    (("请选择",), "emotion"),
    (("强度",), "intensity"),
    (("主导情绪",), "emotion"),
]

_INDEX_RE = re.compile(r"^\s*(\d+)\s*[、.．:：)）]\s*")
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)")
_IP_REGION_RE = re.compile(r"\(([^)]*)\)\s*$")
_MULTI_SEPARATOR = "┋"


class SchemaError(ValueError):
    """题目定义或答卷不符合 schema 约定。"""


def strip_index(column: str) -> tuple[int | None, str]:
    """拆掉问卷星表头的 ``1、`` 前缀，返回 (题号, 题干)。"""

    text = (column or "").strip()
    match = _INDEX_RE.match(text)
    if match:
        return int(match.group(1)), text[match.end():].strip()
    return None, text


def infer_role(title: str) -> str:
    """根据题干关键词推断语义角色；无法判断时返回空串。"""

    for keywords, role in _ROLE_HINTS:
        if any(keyword in title for keyword in keywords):
            return role
    return ""


def _blank(question: dict[str, Any]) -> dict[str, Any]:
    """把外部传入的题目补全为完整结构，并丢弃未知字段。"""

    qtype = str(question.get("type") or "text")
    if qtype not in QUESTION_TYPES:
        raise SchemaError(f"不支持的题型：{qtype}")
    role = str(question.get("role") or "")
    if role not in ROLES:
        raise SchemaError(f"未知字段角色：{role}")
    item: dict[str, Any] = {
        "id": str(question.get("id") or "").strip(),
        "type": qtype,
        "title": str(question.get("title") or "").strip(),
        "required": bool(question.get("required", True)),
        "role": role,
    }
    if not item["title"]:
        raise SchemaError("题干不能为空")
    if qtype in {"single", "multiple"}:
        options = [str(value).strip() for value in question.get("options") or []]
        item["options"] = [value for value in options if value]
        if not item["options"]:
            raise SchemaError(f"「{item['title']}」缺少选项")
    if qtype == "rating":
        low = int(question.get("min", 1))
        high = int(question.get("max", 9))
        if high <= low or high - low > 20:
            raise SchemaError(f"「{item['title']}」量表范围不合法")
        item["min"] = low
        item["max"] = high
        item["min_label"] = str(question.get("min_label") or "")
        item["max_label"] = str(question.get("max_label") or "")
    # 从问卷星导入时保留原表头，保证导出可逐列还原
    if question.get("source_column"):
        item["source_column"] = str(question["source_column"])
    if question.get("score") is not None:
        item["score"] = float(question["score"])
    return item


def normalize_schema(raw: Any) -> list[dict[str, Any]]:
    """校验并规范化题目列表，自动补全缺失的 id。"""

    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SchemaError("题目定义必须是列表")
    questions = [_blank(item) for item in raw]
    seen: set[str] = set()
    for index, question in enumerate(questions, start=1):
        qid = question["id"]
        if not qid:
            qid = f"q{index}"
        if qid in seen:
            raise SchemaError(f"题目 id 重复：{qid}")
        question["id"] = qid
        seen.add(qid)
    return questions


def validate_schema(schema: list[dict[str, Any]]) -> None:
    if not schema:
        raise SchemaError("问卷至少需要一道题")
    normalize_schema(schema)


def schema_fingerprint(schema: list[dict[str, Any]]) -> str:
    """题目结构的稳定指纹，用于判断答卷对应哪一版量表。"""

    payload = json.dumps(normalize_schema(schema), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 默认量表模板：与既有问卷星「情绪诱发情况评估」12 题逐列对应
# ---------------------------------------------------------------------------

_CLARITY_OPTIONS = [
    "产生了非常清晰、突出的主导情绪",
    "产生了较为清晰的主导情绪",
    "能够辨认出情绪，但主导情绪不够明确",
    "产生了一些情绪，但感受比较模糊",
    "没有产生明显情绪",
]
_EMOTION_OPTIONS = ["恐惧/不安", "悲伤/失落", "温馨/放松", "激昂", "愉快", "无法判断"]
_COVERAGE_OPTIONS = [
    "总时长75%以上", "约占总时长50%-75%", "约占总时长25%-50%", "不足总时长25%", "无法判断",
]
_STABILITY_OPTIONS = [
    "主导情绪从头到尾基本稳定", "有一定波动，但主导情绪不变",
    "无法判断", "有明显反转或频繁情绪变化",
]
_FAMILIARITY_OPTIONS = [
    "从未接触过", "隐约见过或听过", "比较熟悉，知道大概故事情节", "非常熟悉，能预想到后续内容",
]
_COMPREHENSION_OPTIONS = [
    "基本完全理解", "大部分能够理解", "能够理解一部分", "大部分无法理解", "完全无法理解",
]
_ISSUE_OPTIONS = [
    "没有问题", "画面模糊", "存在杂音(如录制到人声等)", "声音过大或过小",
    "画面或声音播放卡顿", "内容难以理解", "音画不同步", "其他",
]


def default_schema(kind: str = "video") -> list[dict[str, Any]]:
    """生成与既有问卷星导出格式一致的标准 12 题量表。

    ``kind`` 为 ``video`` 或 ``audio``；音频版只替换措辞与编号列名，
    role 与题型完全一致，因此两套问卷可以共用清洗与质量评分。
    """

    if kind not in {"video", "audio"}:
        raise ValueError("kind 必须是 video 或 audio")
    video = kind == "video"
    noun = "视频" if video else "音乐"
    stimulus_col = "2、视频编号:" if video else "2、音乐歌曲编号:"
    understanding = (
        "10、在未观看完整电影/电视剧的情况下，你是否仍能理解该片段？"
        if video else "10、在未收听完整曲目的情况下，你是否仍能理解该片段？"
    )
    stability = (
        "8、视频诱发的主导情绪是否存在明显的情绪反转或多种情绪变化？"
        if video else "8、音乐诱发的主导情绪是否存在明显的情绪反转或多种情绪变化？"
    )
    raw: list[dict[str, Any]] = [
        {"id": "q1", "type": "text", "title": "您的姓名：", "role": "rater", "source_column": "1、您的姓名："},
        {"id": "q2", "type": "text", "title": stimulus_col.split("、", 1)[1], "role": "stimulus", "source_column": stimulus_col},
        {"id": "q3", "type": "rating", "title": f"请为该{noun}使你实际产生的情绪效价（不愉快~愉快）打分:", "role": "valence", "min": 1, "max": 9, "min_label": "非常不愉快", "max_label": "非常愉快", "source_column": f"3、请为该{noun}使你实际产生的情绪效价（不愉快~愉快）打分:"},
        {"id": "q4", "type": "rating", "title": f"请为该{noun}使你实际产生的情绪唤醒度（平静~激烈）打分：", "role": "arousal", "min": 1, "max": 9, "min_label": "非常平静", "max_label": "非常激烈", "source_column": f"4、请为该{noun}使你实际产生的情绪唤醒度（平静~激烈）打分："},
        {"id": "q5", "type": "single", "title": f"观看该{noun}后，你是否形成了一种明确、突出的主导情绪？", "role": "clarity", "options": _CLARITY_OPTIONS, "source_column": f"5、观看该{noun}后，你是否形成了一种明确、突出的主导情绪？"},
        {"id": "q6", "type": "single", "title": f"请选择该{noun}诱发你实际产生的主导情绪：", "role": "emotion", "options": _EMOTION_OPTIONS, "source_column": f"6、请选择该{noun}诱发你实际产生的主导情绪："},
        {"id": "q7", "type": "single", "title": "主导情绪大约覆盖素材多长时间？", "role": "coverage", "options": _COVERAGE_OPTIONS, "source_column": "7、主导情绪大约覆盖素材多长时间？"},
        {"id": "q8", "type": "single", "title": stability.split("、", 1)[1], "role": "stability", "options": _STABILITY_OPTIONS, "source_column": stability},
        {"id": "q9", "type": "single", "title": f"在本次测试前，你对该{noun}的熟悉程度？", "role": "familiarity", "options": _FAMILIARITY_OPTIONS, "source_column": f"9、在本次测试前，你对该{noun}的熟悉程度？"},
        {"id": "q10", "type": "single", "title": understanding.split("、", 1)[1], "role": "comprehension", "options": _COMPREHENSION_OPTIONS, "source_column": understanding},
        {"id": "q11", "type": "multiple", "title": "播放过程中是否存在以下问题？可多选：", "role": "issues", "options": _ISSUE_OPTIONS, "source_column": "11、播放过程中是否存在以下问题？可多选："},
        {"id": "q12", "type": "textarea", "title": "是否存在未被上述问题涵盖，但明显影响情绪体验的因素？", "role": "other", "source_column": "12、是否存在未被上述问题涵盖，但明显影响情绪体验的因素？"},
    ]
    for item in raw:
        item["required"] = True
    return normalize_schema(raw)


# ---------------------------------------------------------------------------
# 问卷星 CSV → schema 推断
# ---------------------------------------------------------------------------


def _clean_values(rows: list[dict[str, str]], column: str) -> list[str]:
    return [str(row.get(column) or "").strip() for row in rows if str(row.get(column) or "").strip()]


def _parse_scale(value: Any, low: int, high: int) -> float | None:
    """沿用 audit 的 1–9 文字锚点解析，再按题目自定义范围校验。"""

    number = parse_rating(value)
    if number is None:
        return None
    return number if low <= number <= high else None


def infer_schema(
    columns: list[str],
    rows: list[dict[str, str]],
    kind: str = "video",
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """从问卷星导出表头与样本行推断题目定义。

    返回 ``(schema, platform_map)``；``platform_map`` 把平台元数据字段
    映射到实际列名，供导入时取值。推断规则以「题干关键词 + 取值形态」
    双重判断，多选题按问卷星标准的 ``┋`` 分隔符还原选项。
    """

    platform_map: dict[str, str] = {}
    question_columns: list[str] = []
    # 最长匹配优先：否则「来源详情」会被更短的「来源」抢先匹配
    platform_keys = sorted(PLATFORM_COLUMNS, key=len, reverse=True)
    for column in columns:
        _, title = strip_index(column)
        matched = next((key for key in platform_keys if key in title), None)
        if matched:
            platform_map[PLATFORM_COLUMNS[matched]] = column
        else:
            question_columns.append(column)
    if not question_columns:
        raise SchemaError("未识别到任何题目列，请检查 CSV 表头")

    schema: list[dict[str, Any]] = []
    for position, column in enumerate(question_columns, start=1):
        index, title = strip_index(column)
        values = _clean_values(rows, column)
        role = infer_role(title)
        qtype = "text"
        question: dict[str, Any] = {
            "id": f"q{index or position}",
            "type": qtype,
            "title": title,
            "required": True,
            "role": role,
            "source_column": column,
        }
        multi = "多选" in title or any(_MULTI_SEPARATOR in value for value in values)
        rating_like = values and sum(1 for value in values if parse_rating(value) is not None) / len(values) >= 0.9
        unique = list(dict.fromkeys(values))
        if role in {"rater", "stimulus"}:
            qtype = "text"
        elif role in {"valence", "arousal"} or (rating_like and ("打分" in title or "评分" in title)):
            qtype = "rating"
            question.update({"min": 1, "max": 9})
            if role == "valence":
                question.update({"min_label": "非常不愉快", "max_label": "非常愉快"})
            elif role == "arousal":
                question.update({"min_label": "非常平静", "max_label": "非常激烈"})
        elif multi or role == "issues":
            qtype = "multiple"
            options: list[str] = []
            for value in unique:
                for part in re.split(r"[┋|]", value):
                    part = re.sub(r"〖.*?〗", "", part).strip()
                    if part and part not in options:
                        options.append(part)
            question["options"] = options or ["没有问题"]
        elif role == "other":
            qtype = "textarea"
        elif len(unique) <= 12 and max((len(value) for value in unique), default=0) <= 40:
            qtype = "single"
            counts = Counter(values)
            question["options"] = [value for value, _ in counts.most_common()]
        else:
            qtype = "textarea"
        question["type"] = qtype
        schema.append(question)
    return normalize_schema(schema), platform_map


# ---------------------------------------------------------------------------
# 平台元数据解析（含 IP 脱敏）
# ---------------------------------------------------------------------------


def parse_duration(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _DURATION_RE.search(text)
    if not match:
        return None
    number = float(match.group(1))
    if "分" in text and "秒" not in text:
        number *= 60
    elif "小时" in text:
        number *= 3600
    return number


def hash_ip(value: Any) -> tuple[str, str]:
    """返回 ``(地区, 不可逆哈希)``；原始 IP 不落盘。"""

    text = str(value or "").strip()
    if not text:
        return "", ""
    region_match = _IP_REGION_RE.search(text)
    region = region_match.group(1) if region_match else ""
    address = _IP_REGION_RE.sub("", text).strip()
    digest = hashlib.sha256(address.encode("utf-8")).hexdigest()[:12] if address else ""
    return region, digest


def parse_platform_meta(row: dict[str, str], platform_map: dict[str, str]) -> dict[str, Any]:
    def get(key: str) -> str:
        column = platform_map.get(key)
        return str(row.get(column) or "").strip() if column else ""

    region, ip_digest = hash_ip(get("ip"))
    serial = get("serial_no")
    total = get("total_score")
    return {
        "serial_no": int(serial) if serial.isdigit() else None,
        "submitted_at": get("submitted_at"),
        "duration_s": parse_duration(get("duration_s")),
        "source": get("source"),
        "source_detail": get("source_detail"),
        "ip_region": region,
        "ip_hash": ip_digest,
        "total_score": int(total) if re.fullmatch(r"-?\d+", total) else None,
    }


# ---------------------------------------------------------------------------
# 答卷校验与归一化
# ---------------------------------------------------------------------------


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        items = [part.strip() for part in re.split(r"[┋|]", str(value))]
    return [item for item in items if item]


def normalize_answer(question: dict[str, Any], value: Any, kind: str = "video") -> Any:
    """按 role 把原始答案转成分析用值；无法解析时返回 None。"""

    role = question.get("role", "")
    qtype = question["type"]
    if role == "rater":
        return normalize_rater(value) or None
    if role == "stimulus":
        return canonical_stimulus_id(value, kind)
    # 角色专属解析必须排在通用题型分支之前：issues / other 虽然在采集端
    # 表现为多选/文本题，但分析端需要结构化的问题严重度与归类标签。
    if role == "issues":
        raw = "┋".join(_as_list(value)) if isinstance(value, (list, tuple, set)) else str(value or "")
        severity, tags, contradictory = parse_issue_cell(raw)
        return {"severity": severity, "tags": list(tags), "contradictory": contradictory}
    if role == "other":
        tag, text = parse_free_text_issue(value)
        return {"tag": tag, "text": text}
    if qtype == "rating":
        return _parse_scale(value, int(question.get("min", 1)), int(question.get("max", 9)))
    if qtype == "multiple":
        return _as_list(value)
    text = str(value or "").strip()
    return text or None


def validate_answers(
    schema: list[dict[str, Any]],
    answers: dict[str, Any],
    kind: str = "video",
    strict: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """校验一份答卷。

    返回 ``(原始答案, 归一化值, 异常标记)``。``strict=True`` 时必填缺失
    或非法评分会抛 :class:`SchemaError`（用于在线提交）；导入历史数据时
    用 ``strict=False``，只记录标记而不丢弃整行，保证可回溯。
    """

    clean: dict[str, Any] = {}
    normalized: dict[str, Any] = {}
    flags: list[str] = []
    for question in schema:
        qid = question["id"]
        raw = answers.get(qid)
        if isinstance(raw, str):
            raw = raw.strip()
        empty = raw is None or raw == "" or raw == []
        if empty:
            clean[qid] = "" if question["type"] != "multiple" else []
            normalized[qid] = None
            if question.get("required", True):
                flags.append(f"missing:{qid}")
            continue
        clean[qid] = raw
        value = normalize_answer(question, raw, kind)
        normalized[qid] = value
        if value is None:
            flags.append(f"invalid:{qid}")
            continue
        if question["type"] == "single" and question.get("options"):
            if str(value) not in {str(option) for option in question["options"]}:
                flags.append(f"outside_option:{qid}")
        if question["type"] == "multiple" and question.get("options") and isinstance(value, list):
            unknown = [item for item in value if item not in {str(option) for option in question["options"]}]
            if unknown:
                flags.append(f"outside_option:{qid}")
    if strict:
        fatal = [flag for flag in flags if flag.startswith(("missing:", "invalid:"))]
        if fatal:
            raise SchemaError("请完整填写必答题：" + "、".join(
                next((q["title"] for q in schema if q["id"] == flag.split(":", 1)[1]), flag)
                for flag in fatal
            ))
    return clean, normalized, flags


def wjx_header(question: dict[str, Any], index: int) -> str:
    """生成问卷星风格表头；导入过的题优先沿用原始表头。"""

    return question.get("source_column") or f"{index}、{question['title']}"


def survey_kind(survey: dict[str, Any]) -> str:
    """统一推断问卷量表模态：显式 kind 优先，否则按素材模态推断。

    kind 是刺激编号归一化（.mp4 / .mp3）与默认量表版本的输入，不是纯展示字段；
    读写两侧必须用同一口径，否则编辑后会出现「表头是音乐版、编号却是视频版」的静默错误。
    """

    explicit = survey.get("kind")
    if explicit in {"video", "audio"}:
        return explicit
    materials = survey.get("materials") or []
    if materials and all(item.get("modality") == "audio" for item in materials):
        return "audio"
    return "video"


def schema_for_survey(survey: dict[str, Any]) -> list[dict[str, Any]]:
    """读取问卷题目定义；旧版无 schema 的问卷统一回退到默认量表。

    surveys（读侧）与 survey_meta（写/统计/导出侧）共用本函数，避免旧问卷
    在部分端点拿到空 schema 而返回 400。
    """

    raw = survey.get("schema")
    if raw:
        return normalize_schema(raw)
    return default_schema(survey_kind(survey))
