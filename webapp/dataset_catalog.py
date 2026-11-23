"""Source datasets for the catalog, independent of the EEG training inputs."""

from .config import DATA_DIR, SEED_IV_DIR
from .db import transaction


SOURCES = (
    {
        "id": "seed-iv", "name": "SEED-IV", "modalities": ["EEG", "眼动"],
        "task": "脑电情绪识别",
        "structure": "按会话、被试和试次组织。现有流程读取脑电 MAT 并构建 EEG 特征。",
        "adapter": "eeg", "eeg_workflow_url": "/eeg",
        "source_url": "https://bcmi.sjtu.edu.cn/home/seed/seed-iv.html",
        "access": "沿用现有本地数据目录。",
    },
    {
        "id": "meld", "name": "MELD", "modalities": ["文本", "音频", "视频"],
        "task": "多方对话情绪与情感倾向识别",
        "structure": "按 train/dev/test 划分。CSV 记录发言与标签，按划分、Dialogue_ID 和 Utterance_ID 关联 MP4。",
        "source_url": "https://github.com/declare-lab/MELD",
        "access": "官方仓库提供标注和原始音视频包的获取入口。",
    },
    {
        "id": "emorynlp", "name": "EmoryNLP", "modalities": ["文本"],
        "task": "多方对话文本情绪识别",
        "structure": "官方 JSON 按 train/dev/test 划分，包含剧集、场景、发言、说话人和情绪标签。独立的音视频扩展可作为后续版本登记。",
        "source_url": "https://github.com/emorynlp/emotion-detection",
        "access": "原始文本标注由 Emory NLP 公开发布。",
    },
    {
        "id": "noxi", "name": "NoXi", "modalities": ["音频", "视频"],
        "task": "双人互动行为与参与度分析",
        "structure": "以双人互动会话为单位组织。MultiMediate 版本提供音视频与时间对齐的行为标注，参与度可按帧查看。",
        "source_url": "https://www.multimediate-challenge.org/datasets/Dataset_NoXi/",
        "access": "由课题组按官方要求签署 EULA 后获取。仅供非商业科研使用。",
    },
    {
        "id": "iemocap", "name": "IEMOCAP", "modalities": ["文本", "音频", "视频", "动作捕捉"],
        "task": "双人对话情绪识别",
        "structure": "按会话组织剧本和即兴对话。音视频、转写、情绪标注与动作捕捉可按会话及片段关联。",
        "source_url": "https://sail.usc.edu/iemocap/iemocap_release.htm",
        "access": "通过 USC 官方表单申请数据访问许可。",
    },
)


def migrate_catalog() -> None:
    with transaction() as conn:
        if conn.execute("SELECT 1 FROM legacy_imports WHERE domain = 'builtin_catalog'").fetchone():
            return
    with transaction(write=True) as conn:
        if conn.execute("SELECT 1 FROM legacy_imports WHERE domain = 'builtin_catalog'").fetchone():
            return
        for order, source in enumerate(SOURCES):
            conn.execute(
                """INSERT INTO catalog_sources
                   (id, name, task, structure, source_url, access, adapter, eeg_workflow_url, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source["id"], source["name"], source["task"], source["structure"], source["source_url"],
                 source["access"], source.get("adapter"), source.get("eeg_workflow_url"), order),
            )
            conn.executemany(
                "INSERT INTO catalog_source_modalities (source_id, modality, sort_order) VALUES (?, ?, ?)",
                ((source["id"], modality, index) for index, modality in enumerate(source["modalities"])),
            )
        conn.execute("INSERT INTO legacy_imports (domain) VALUES ('builtin_catalog')")


def _local_status(source_id):
    if source_id == "seed-iv":
        directory = SEED_IV_DIR / "eeg_raw_data"
        present = any(path.is_file() for path in directory.glob("*/*.mat"))
        return ("available" if present else "missing"), "data/SEED_IV"

    directory = DATA_DIR / "external" / source_id / "raw"
    relative_path = f"data/external/{source_id}/raw"
    if source_id == "meld":
        if (directory / "MELD.Raw.tar.gz").is_file():
            return "unverified", relative_path
        if all((directory / "annotations" / f"{split}_sent_emo.csv").is_file()
               for split in ("train", "dev", "test")):
            return "annotations", relative_path
        if (directory / "MELD.Raw.tar.gz.part").is_file():
            return "partial", relative_path
    elif source_id == "emorynlp":
        for release in directory.glob("emotion-detection-*/json"):
            if all((release / f"emotion-detection-{split}.json").is_file()
                   for split in ("trn", "dev", "tst")):
                return "available", relative_path
    elif source_id in {"noxi", "iemocap"}:
        if directory.is_dir() and any(directory.iterdir()):
            return "unverified", relative_path
        return "access_required", relative_path
    return "missing", relative_path


def list_source_datasets():
    """Read dataset descriptors and local presence without opening dataset content."""
    migrate_catalog()
    with transaction() as conn:
        sources = [dict(row) for row in conn.execute(
            """SELECT id, name, task, structure, source_url, access, adapter, eeg_workflow_url
               FROM catalog_sources ORDER BY sort_order, id"""
        )]
        modalities = {}
        for row in conn.execute(
            "SELECT source_id, modality FROM catalog_source_modalities ORDER BY source_id, sort_order"
        ):
            modalities.setdefault(row["source_id"], []).append(row["modality"])
    datasets = []
    for source in sources:
        source["modalities"] = modalities.get(source["id"], [])
        status, path = _local_status(source["id"])
        if "EEG" not in source["modalities"]:
            preparation = "no_eeg"
        elif source.get("adapter") != "eeg" or not source.get("eeg_workflow_url"):
            preparation = "adapter_pending"
        else:
            preparation = "ready" if status == "available" else "files_missing"
        datasets.append({
            **source,
            "local_status": status,
            "local_path": path,
            "eeg_preparation": preparation,
        })
    return datasets
