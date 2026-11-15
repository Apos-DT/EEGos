"""Dual-view multi-prototype network (the proposed method in the thesis).

The model deliberately uses channel×band features so that it can be compared
fairly with DE/DGCNN baselines and trained on a CPU.  It has two spatial
views:

* electrode view: a shared per-channel encoder followed by channel attention;
* region view: contiguous channel groups, region-wise encoding and attention.

The fused embedding is classified and regularised by class prototypes.  Each
class may own several prototypes, which reflects the observation that one
emotion label can contain several subject/session-specific sub-patterns.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


def _contiguous_regions(n_channels: int, n_regions: int = 5) -> torch.Tensor:
    """Assign channels to contiguous regions, robust to small channel counts."""

    boundaries = torch.linspace(0, n_channels, steps=n_regions + 1).round().long()
    region_ids = torch.zeros(n_channels, dtype=torch.long)
    for region in range(n_regions):
        start, end = int(boundaries[region]), int(boundaries[region + 1])
        if end > start:
            region_ids[start:end] = region
    return region_ids


class DualViewMultiProto(nn.Module):
    def __init__(
        self,
        n_channels: int,
        n_features: int,
        n_classes: int,
        hidden: int = 32,
        n_prototypes: int = 2,
        n_regions: int = 5,
        dropout: float = 0.25,
        proto_margin: float = 1.0,
    ) -> None:
        super().__init__()
        self.n_channels = n_channels
        self.n_features = n_features
        self.n_classes = n_classes
        self.n_prototypes = n_prototypes
        self.proto_margin = proto_margin
        self.register_buffer("region_ids", _contiguous_regions(n_channels, n_regions), persistent=False)
        self.n_regions = int(n_regions)

        self.electrode_encoder = nn.Sequential(
            nn.Linear(n_features, hidden),
            nn.GELU(),
        )
        self.electrode_attention = nn.Linear(hidden, 1)
        self.region_encoder = nn.Sequential(
            nn.Linear(n_features, hidden),
            nn.GELU(),
        )
        self.region_attention = nn.Linear(hidden, 1)
        self.fusion = nn.Sequential(
            nn.Linear(hidden * 2, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.classifier = nn.Linear(hidden, n_classes)
        self.prototypes = nn.Parameter(torch.randn(n_classes, n_prototypes, hidden) * 0.05)

    def _electrode_view(self, x: torch.Tensor) -> torch.Tensor:
        encoded = self.electrode_encoder(x)  # (B, C, H)
        weights = torch.softmax(self.electrode_attention(encoded).squeeze(-1), dim=1)
        return torch.sum(encoded * weights.unsqueeze(-1), dim=1)

    def _region_view(self, x: torch.Tensor) -> torch.Tensor:
        batch, channels, features = x.shape
        counts = torch.zeros(self.n_regions, device=x.device, dtype=x.dtype)
        counts.index_add_(0, self.region_ids, torch.ones(channels, device=x.device, dtype=x.dtype))
        counts = counts.clamp_min(1.0)
        pooled = torch.zeros(batch, self.n_regions, features, device=x.device, dtype=x.dtype)
        pooled.index_add_(1, self.region_ids, x)
        pooled = pooled / counts.view(1, -1, 1)
        encoded = self.region_encoder(pooled)
        weights = torch.softmax(self.region_attention(encoded).squeeze(-1), dim=1)
        return torch.sum(encoded * weights.unsqueeze(-1), dim=1)

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        electrode = self._electrode_view(x)
        region = self._region_view(x)
        return self.fusion(torch.cat([electrode, region], dim=-1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.embed(x))

    def prototype_regularization(self, embedding: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """Compactness to the nearest own-class prototype + inter-class margin.

        Returns a scalar that can be added to cross-entropy.  Prototypes and
        embeddings are L2-normalised so that distances live on a fixed scale.
        """

        normed = F.normalize(embedding, dim=-1)
        prototypes = F.normalize(self.prototypes, dim=-1)
        distances = torch.cdist(normed, prototypes.reshape(-1, prototypes.shape[-1]))
        distances = distances.view(-1, self.n_classes, self.n_prototypes)
        batch_idx = torch.arange(normed.shape[0], device=normed.device)
        own = distances[batch_idx, labels].min(dim=-1).values
        other = distances.clone()
        other[batch_idx, labels] = float("inf")
        closest_other = other.reshape(normed.shape[0], -1).min(dim=-1).values
        compactness = own.mean()
        separation = F.relu(self.proto_margin - closest_other).mean()
        return compactness + separation
