"""A compact DGCNN-style graph baseline for channel×band features."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


class GraphConv(nn.Module):
    def __init__(self, in_features: int, out_features: int) -> None:
        super().__init__()
        self.linear = nn.Linear(in_features, out_features)

    def forward(self, x: torch.Tensor, adjacency: torch.Tensor) -> torch.Tensor:
        # x: (B, C, F), adjacency: (B, C, C)
        return torch.bmm(adjacency, self.linear(x))


class DGCNN(nn.Module):
    """Dense-graph convolution with cosine kNN adjacency.

    This is a feature-level baseline, not a reproduction of the full DGCNN
    paper.  It keeps the two ingredients that matter for the comparison:
    dynamic graph construction from the current sample and graph aggregation
    over electrodes.
    """

    def __init__(
        self,
        n_channels: int,
        n_features: int,
        n_classes: int,
        hidden: int = 64,
        k: int = 5,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        self.k = max(1, min(k, n_channels))
        self.input_proj = nn.Linear(n_features, hidden)
        self.conv1 = GraphConv(hidden, hidden)
        self.conv2 = GraphConv(hidden, hidden)
        self.norm1 = nn.LayerNorm(hidden)
        self.norm2 = nn.LayerNorm(hidden)
        self.classifier = nn.Sequential(
            nn.Linear(hidden * 2, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, n_classes),
        )

    def _adjacency(self, x: torch.Tensor) -> torch.Tensor:
        normed = F.normalize(x, dim=-1)
        similarity = torch.bmm(normed, normed.transpose(1, 2))
        batch, channels, _ = similarity.shape
        values, indices = similarity.topk(self.k, dim=-1)
        mask = torch.zeros_like(similarity).scatter_(2, indices, 1.0)
        similarity = similarity.masked_fill(mask == 0, float("-inf"))
        return torch.softmax(similarity, dim=-1)

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        h = self.input_proj(x)
        adjacency = self._adjacency(h)
        h = F.gelu(self.norm1(self.conv1(h, adjacency) + h))
        adjacency = self._adjacency(h)
        h = F.gelu(self.norm2(self.conv2(h, adjacency) + h))
        pooled = torch.cat([h.max(dim=1).values, h.mean(dim=1)], dim=-1)
        return pooled

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.embed(x))
