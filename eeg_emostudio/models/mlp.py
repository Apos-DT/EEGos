"""A strong, deliberately simple baseline for channel×band features."""

from __future__ import annotations

import torch
from torch import nn


class MLP(nn.Module):
    def __init__(
        self,
        n_channels: int,
        n_features: int,
        n_classes: int,
        hidden: int = 128,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        self.n_channels = n_channels
        self.n_features = n_features
        self.encoder = nn.Sequential(
            nn.Flatten(),
            nn.Linear(n_channels * n_features, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, hidden),
            nn.GELU(),
        )
        self.classifier = nn.Linear(hidden, n_classes)

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        return self.encoder(x)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.embed(x))
