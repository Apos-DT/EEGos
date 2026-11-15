"""Training and evaluation utilities."""

from .metrics import compute_metrics, confusion_matrix
from .trainer import TrainConfig, predict, run_loso, run_subject_dependent, set_seed

__all__ = [
    "TrainConfig",
    "compute_metrics",
    "confusion_matrix",
    "predict",
    "run_loso",
    "run_subject_dependent",
    "set_seed",
]
