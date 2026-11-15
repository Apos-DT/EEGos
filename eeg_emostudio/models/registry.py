"""Model factory shared by the CLI and tests."""

from __future__ import annotations

from typing import Any

from torch import nn

from .dgcnn import DGCNN
from .dualview import DualViewMultiProto
from .eegnet import EEGNet
from .mlp import MLP

MODEL_NAMES = ("mlp", "dgcnn", "dualview", "eegnet")


def model_names() -> tuple[str, ...]:
    return MODEL_NAMES


def build_model(
    name: str,
    n_channels: int,
    n_features: int,
    n_classes: int,
    **kwargs: Any,
) -> nn.Module:
    """Build a model by name.

    ``n_features`` is the number of feature bands for feature models, or the
    number of time samples for EEGNet.
    """

    key = name.lower().strip()
    if key == "mlp":
        return MLP(n_channels, n_features, n_classes, **kwargs)
    if key == "dgcnn":
        return DGCNN(n_channels, n_features, n_classes, **kwargs)
    if key == "dualview":
        return DualViewMultiProto(n_channels, n_features, n_classes, **kwargs)
    if key == "eegnet":
        return EEGNet(n_channels, n_features, n_classes, **kwargs)
    raise ValueError(f"未知模型 {name!r}；可选：{', '.join(MODEL_NAMES)}")
