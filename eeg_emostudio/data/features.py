"""Classical EEG features used by the baseline models."""

from __future__ import annotations

from typing import Mapping

import numpy as np
from scipy import signal

BANDS: dict[str, tuple[float, float]] = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 14.0),
    "beta": (14.0, 30.0),
    "gamma": (30.0, 45.0),
}


def _validate_epochs(epochs: np.ndarray) -> np.ndarray:
    array = np.asarray(epochs, dtype=np.float64)
    if array.ndim != 3:
        raise ValueError(f"epochs 应为 (trials, channels, samples)，实际 {array.shape}")
    if array.shape[0] == 0:
        raise ValueError("epochs 为空")
    return array


def compute_de_features(
    epochs: np.ndarray,
    fs: float,
    bands: Mapping[str, tuple[float, float]] = BANDS,
    window_s: float = 1.0,
    step_s: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute differential entropy (DE) in sliding windows.

    Returns
    -------
    features:
        ``(trials, windows, channels, bands)``.
    window_starts_s:
        Start time of each window in seconds.

    Notes
    -----
    For a zero-mean Gaussian signal, differential entropy is
    ``0.5 * log(2πeσ²)``.  The formula is applied per channel, band and
    window.  Filtering is zero-phase to avoid latency shifts.
    """

    array = _validate_epochs(epochs)
    if fs <= 0:
        raise ValueError("采样率必须为正数")
    if window_s <= 0:
        raise ValueError("window_s 必须为正数")
    step = window_s if step_s is None else step_s
    if step <= 0:
        raise ValueError("step_s 必须为正数")

    n_trials, n_channels, n_samples = array.shape
    window = int(round(window_s * fs))
    step = int(round(step * fs))
    if window < 2 or window > n_samples:
        window = min(max(n_samples, 2), max(window, 2))
    starts = list(range(0, max(n_samples - window, 0) + 1, step))
    if not starts:
        starts = [0]

    all_features = []
    for name, (low, high) in bands.items():
        if low >= fs / 2:
            raise ValueError(f"频带 {name} 下限超过 Nyquist")
        upper = min(high, fs / 2 * 0.95)
        sos = signal.butter(4, [low, upper], btype="bandpass", fs=fs, output="sos")
        filtered = signal.sosfiltfilt(sos, array, axis=-1)
        band_features = np.empty((n_trials, len(starts), n_channels), dtype=np.float64)
        for w_idx, start in enumerate(starts):
            segment = filtered[..., start : start + window]
            variance = np.var(segment, axis=-1)
            variance = np.maximum(variance, 1e-12)
            band_features[:, w_idx, :] = 0.5 * np.log(2.0 * np.pi * np.e * variance)
        all_features.append(band_features)

    features = np.stack(all_features, axis=-1)
    return features, np.asarray(starts) / fs


def aggregate_windows(features: np.ndarray, method: str = "mean") -> np.ndarray:
    """Aggregate the window axis to obtain one vector per trial."""

    array = np.asarray(features)
    if array.ndim != 4:
        raise ValueError(f"特征应为 (trials, windows, channels, bands)，实际 {array.shape}")
    if method == "mean":
        return array.mean(axis=1)
    if method == "std":
        return array.std(axis=1)
    if method == "concat":
        return array.reshape(array.shape[0], -1, array.shape[-1])
    raise ValueError("method 只支持 mean/std/concat")


def compute_bandpower_features(
    epochs: np.ndarray,
    fs: float,
    bands: Mapping[str, tuple[float, float]] = BANDS,
    nperseg_s: float = 1.0,
) -> np.ndarray:
    """Compute log band power with Welch's method.

    Returns ``(trials, channels, bands)``.  Unlike DE, this is intended as a
    robustness check and for readers who are more familiar with band power.
    """

    array = _validate_epochs(epochs)
    n_trials, n_channels, n_samples = array.shape
    nperseg = int(min(max(round(nperseg_s * fs), 16), n_samples))
    frequencies, psd = signal.welch(
        array, fs=fs, nperseg=nperseg, axis=-1, detrend="constant", scaling="density"
    )
    out = np.empty((n_trials, n_channels, len(bands)), dtype=np.float64)
    for b_idx, (_, (low, high)) in enumerate(bands.items()):
        mask = (frequencies >= low) & (frequencies <= min(high, fs / 2))
        if not mask.any():
            out[..., b_idx] = np.nan
            continue
        out[..., b_idx] = np.log(np.trapezoid(psd[..., mask], frequencies[mask], axis=-1) + 1e-12)
    return out


def zscore_features(train: np.ndarray, test: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fit feature-wise z-scoring on the training set only.

    The feature axis is flattened for standardization, which is appropriate
    for channel×band features and avoids the common leakage of fitting on the
    full dataset.
    """

    train = np.asarray(train, dtype=np.float64)
    test = np.asarray(test, dtype=np.float64)
    mean = train.mean(axis=0, keepdims=True)
    std = train.std(axis=0, keepdims=True)
    std = np.where(std < 1e-8, 1.0, std)
    return (train - mean) / std, (test - mean) / std
