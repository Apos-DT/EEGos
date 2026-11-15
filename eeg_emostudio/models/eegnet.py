"""EEGNet-style raw-waveform baseline."""

from __future__ import annotations

import torch
from torch import nn


class EEGNet(nn.Module):
    """Compact EEGNet for ``(batch, channels, time)`` input.

    The implementation follows the well-known block structure (temporal
    convolution, depthwise spatial convolution, separable convolution) and
    uses adaptive pooling so that short windows remain valid.  It is intended
    as a reproducible raw-signal baseline, not a claim of exact numerical
    equivalence with any particular paper implementation.
    """

    def __init__(
        self,
        n_channels: int,
        n_samples: int,
        n_classes: int,
        F1: int = 8,
        D: int = 2,
        F2: int = 16,
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.n_channels = n_channels
        self.n_samples = n_samples
        self.block1 = nn.Sequential(
            nn.Conv2d(1, F1, kernel_size=(1, 15), padding=(0, 7), bias=False),
            nn.BatchNorm2d(F1),
            nn.Conv2d(F1, F1 * D, kernel_size=(n_channels, 1), groups=F1, bias=False),
            nn.BatchNorm2d(F1 * D),
            nn.ELU(),
            nn.AvgPool2d(kernel_size=(1, 4)),
            nn.Dropout(dropout),
        )
        self.block2 = nn.Sequential(
            nn.Conv2d(F1 * D, F1 * D, kernel_size=(1, 15), padding=(0, 7), groups=F1 * D, bias=False),
            nn.Conv2d(F1 * D, F2, kernel_size=(1, 1), bias=False),
            nn.BatchNorm2d(F2),
            nn.ELU(),
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Dropout(dropout),
        )
        self.classifier = nn.Linear(F2, n_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim == 3:
            x = x.unsqueeze(1)
        if x.ndim != 4:
            raise ValueError(f"EEGNet 期望 (B, C, T) 或 (B, 1, C, T)，实际 {tuple(x.shape)}")
        h = self.block1(x)
        h = self.block2(h)
        return self.classifier(torch.flatten(h, 1))
