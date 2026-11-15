"""Lightweight, dependency-light EEG preprocessing.

The production research pipeline can use MNE for EDF/BDF and ICA.  This
module deliberately depends only on NumPy/SciPy so that the graduation
project remains runnable on a clean machine and so that the core operations
are unit-testable.  MNE is an optional adapter, not a hard requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy import signal


@dataclass(frozen=True)
class PreprocessConfig:
    """Configuration for one preprocessing run."""

    fs: float
    bandpass: tuple[float, float] = (0.1, 70.0)
    notch_hz: float | None = 50.0
    target_fs: float | None = None
    rereference: str = "none"  # none | car
    amplitude_uv: float | None = 150.0


def _as_3d(x: np.ndarray) -> tuple[np.ndarray, bool]:
    array = np.asarray(x, dtype=np.float64)
    if array.ndim == 2:
        return array[np.newaxis, ...], True
    if array.ndim != 3:
        raise ValueError(f"EEG 数组应为 (channels, samples) 或 (trials, channels, samples)，实际 {array.shape}")
    return array, False


def common_average_reference(x: np.ndarray) -> np.ndarray:
    """Re-reference along the channel axis (second-last dimension)."""

    return x - np.mean(x, axis=-2, keepdims=True)


def preprocess_array(x: np.ndarray, config: PreprocessConfig) -> np.ndarray:
    """Band-pass, notch-filter, optionally re-reference and resample EEG.

    Parameters
    ----------
    x:
        ``(channels, samples)`` or ``(trials, channels, samples)`` in µV.
        The function never mutates the input.
    config:
        Filter and resampling parameters.
    """

    array, was_2d = _as_3d(x)
    fs = float(config.fs)
    if fs <= 0:
        raise ValueError("采样率必须为正数")
    nyquist = fs / 2.0
    low, high = config.bandpass
    if not 0 < low < high:
        raise ValueError("带通截止频率必须满足 0 < low < high")
    if high >= nyquist:
        high = nyquist * 0.95

    # Zero-phase Butterworth band-pass
    sos = signal.butter(4, [low, high], btype="bandpass", fs=fs, output="sos")
    filtered = signal.sosfiltfilt(sos, array, axis=-1)

    if config.notch_hz:
        if config.notch_hz < nyquist:
            b, a = signal.iirnotch(config.notch_hz, Q=30.0, fs=fs)
            filtered = signal.filtfilt(b, a, filtered, axis=-1)

    if config.rereference == "car":
        filtered = common_average_reference(filtered)

    if config.target_fs and abs(config.target_fs - fs) > 1e-9:
        gcd = np.gcd(int(round(config.target_fs)), int(round(fs)))
        up = int(round(config.target_fs)) // int(gcd)
        down = int(round(fs)) // int(gcd)
        filtered = signal.resample_poly(filtered, up, down, axis=-1)

    return filtered[0] if was_2d else filtered


def epoch_by_events(
    x: np.ndarray,
    events: Iterable[int],
    start_s: float,
    end_s: float,
    fs: float,
) -> np.ndarray:
    """Cut fixed-length epochs around event sample indices.

    Parameters
    ----------
    x:
        ``(channels, samples)`` continuous data.  A 3-D input is treated as
        ``(trials, channels, samples)`` and returns
        ``(events, trials, channels, samples)``; callers that need a single
        trial dimension should pass 2-D data.
    """

    array = np.asarray(x, dtype=np.float64)
    if array.ndim not in (2, 3):
        raise ValueError(f"EEG 数组应为 (channels, samples) 或 (trials, channels, samples)，实际 {array.shape}")
    start = int(round(start_s * fs))
    stop = int(round(end_s * fs))
    if stop <= start:
        raise ValueError("epoch 结束偏移必须大于开始偏移")
    epochs = []
    for event in events:
        begin = int(event) + start
        finish = int(event) + stop
        if begin < 0 or finish > array.shape[-1]:
            continue
        epochs.append(array[..., begin:finish])
    if not epochs:
        shape = (0, array.shape[-2], stop - start)
        return np.empty(shape, dtype=array.dtype)
    return np.stack(epochs, axis=0)


def reject_by_amplitude(epochs: np.ndarray, threshold_uv: float) -> np.ndarray:
    """Return a boolean keep-mask based on peak-to-peak amplitude."""

    if threshold_uv <= 0:
        raise ValueError("阈值必须为正数")
    peak_to_peak = np.ptp(epochs, axis=-1)
    return np.all(peak_to_peak <= threshold_uv, axis=1)


def robust_scale_channels(x: np.ndarray) -> np.ndarray:
    """Scale each channel by its median absolute deviation (MAD).

    This is a small, deterministic alternative to per-record z-scoring and
    is useful before feature extraction in cross-subject experiments.
    """

    array = np.asarray(x, dtype=np.float64)
    median = np.median(array, axis=-1, keepdims=True)
    mad = np.median(np.abs(array - median), axis=-1, keepdims=True)
    mad = np.where(mad < 1e-12, 1.0, mad)
    return (array - median) / (1.4826 * mad)
