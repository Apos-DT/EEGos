"""Model zoo for feature and raw-EEG baselines."""

from .dgcnn import DGCNN
from .dualview import DualViewMultiProto
from .eegnet import EEGNet
from .mlp import MLP
from .registry import build_model, model_names

__all__ = [
    "DGCNN",
    "DualViewMultiProto",
    "EEGNet",
    "MLP",
    "build_model",
    "model_names",
]
