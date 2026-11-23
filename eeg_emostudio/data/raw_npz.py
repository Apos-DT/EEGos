"""Schema checks for the local EEG time-series interchange format."""

import numpy as np


def declared_eeg(data):
    """Check explicit modality metadata, if present, without inferring it from shape."""
    if "modality" not in data.files:
        return False
    modality = np.asarray(data["modality"])
    if modality.size != 1 or modality.dtype.kind not in "US":
        raise ValueError("modality 必须为单个文本值")
    if modality.astype(str).item().strip().casefold() != "eeg":
        raise ValueError("文件标记的模态不是 EEG")
    return True


def raw_eeg_arrays(data):
    """Read validated arrays; legacy raw files can supply fs at processing time."""
    declared_eeg(data)
    if "feature_names" in data.files:
        raise ValueError("检测到特征集字段 feature_names，需要输入 EEG 原始时间序列")
    missing = {"x", "y", "subjects"} - set(data.files)
    if missing:
        raise ValueError(f"缺少字段：{', '.join(sorted(missing))}")
    x, y, subjects = data["x"], data["y"], data["subjects"]
    if x.ndim != 3 or not all(x.shape) or x.dtype.kind not in "iuf":
        raise ValueError("x 必须是非空实数数组 (trials, channels, samples)")
    if y.shape != (len(x),) or subjects.shape != (len(x),):
        raise ValueError("y 和 subjects 必须是一维，且与 x 的试次数相同")
    if y.dtype.kind not in "iuf" or not np.isfinite(y).all() or (y < 0).any():
        raise ValueError("y 必须为非负整数类别编码")
    if y.dtype.kind == "f" and not np.equal(y, np.floor(y)).all():
        raise ValueError("y 必须为非负整数类别编码")
    fs = None
    if "fs" in data.files:
        sampling_rate = np.asarray(data["fs"])
        if sampling_rate.size != 1 or sampling_rate.dtype.kind not in "iuf":
            raise ValueError("fs 必须是单个正数采样率")
        fs = float(sampling_rate.item())
        if not np.isfinite(fs) or fs <= 0:
            raise ValueError("fs 必须是单个正数采样率")
    return x, y, subjects, fs
