"""Reproducible training loops for subject-dependent and LOSO experiments."""

from __future__ import annotations

import copy
import json
import platform
import random
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from ..data.manifest import validate_feature_arrays
from ..data.splits import assert_no_subject_leakage, describe_folds, loso_splits, subject_dependent_split
from ..models.registry import build_model
from .metrics import bootstrap_accuracy_ci, compute_metrics


@dataclass
class TrainConfig:
    epochs: int = 40
    batch_size: int = 32
    lr: float = 1e-3
    weight_decay: float = 1e-4
    patience: int = 10
    seed: int = 42
    device: str = "auto"
    proto_weight: float = 0.1
    hidden: int = 32
    dropout: float = 0.25
    n_prototypes: int = 2
    graph_k: int = 5
    val_fraction: float = 0.2
    model_kwargs: dict[str, Any] = field(default_factory=dict)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def resolve_device(requested: str = "auto") -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(requested)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("请求了 CUDA，但当前环境不可用")
    return device


def _standardise(train: np.ndarray, test: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    mean = train.mean(axis=0, keepdims=True)
    std = train.std(axis=0, keepdims=True)
    std = np.where(std < 1e-8, 1.0, std)
    return (train - mean) / std, (test - mean) / std, {
        "mean": mean.astype(float).tolist(),
        "std": std.astype(float).tolist(),
    }


def _class_weights(labels: np.ndarray, n_classes: int) -> torch.Tensor:
    counts = np.bincount(labels, minlength=n_classes).astype(np.float64)
    counts = np.where(counts == 0, 1.0, counts)
    weights = len(labels) / (n_classes * counts)
    return torch.tensor(weights, dtype=torch.float32)


def _make_model(name: str, n_channels: int, n_features: int, n_classes: int, config: TrainConfig) -> nn.Module:
    kwargs = dict(config.model_kwargs)
    key = name.lower()
    if key in {"mlp", "dgcnn", "dualview"}:
        kwargs.setdefault("hidden", config.hidden)
        kwargs.setdefault("dropout", config.dropout)
    if key == "dgcnn":
        kwargs.setdefault("k", config.graph_k)
    if key == "dualview":
        kwargs.setdefault("n_prototypes", config.n_prototypes)
    return build_model(name, n_channels, n_features, n_classes, **kwargs)


def _eval_loss(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    model.eval()
    losses = []
    with torch.no_grad():
        for xb, yb in loader:
            xb, yb = xb.to(device, non_blocking=device.type == "cuda"), yb.to(device, non_blocking=device.type == "cuda")
            losses.append(float(criterion(model(xb), yb).item()))
    return float(np.mean(losses)) if losses else float("nan")


def _train_fold(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    model_name: str,
    n_classes: int,
    config: TrainConfig,
) -> tuple[nn.Module, dict[str, Any], dict[str, Any]]:
    device = resolve_device(config.device)
    x_train, x_val, scaler = _standardise(x_train, x_val)
    train_dataset = TensorDataset(
        torch.tensor(x_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.long)
    )
    val_dataset = TensorDataset(
        torch.tensor(x_val, dtype=torch.float32), torch.tensor(y_val, dtype=torch.long)
    )
    generator = torch.Generator().manual_seed(config.seed)
    train_loader = DataLoader(
        train_dataset,
        batch_size=min(config.batch_size, len(train_dataset)),
        shuffle=True,
        generator=generator,
        num_workers=0,
        pin_memory=device.type == "cuda",
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=min(config.batch_size, max(len(val_dataset), 1)),
        shuffle=False,
        num_workers=0,
        pin_memory=device.type == "cuda",
    )
    n_channels, n_features = x_train.shape[1], x_train.shape[2]
    model = _make_model(model_name, n_channels, n_features, n_classes, config).to(device)
    criterion = nn.CrossEntropyLoss(weight=_class_weights(y_train, n_classes).to(device))
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.lr, weight_decay=config.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(config.epochs, 1))

    best_loss = float("inf")
    best_state = copy.deepcopy(model.state_dict())
    stale = 0
    history: list[dict[str, Any]] = []
    for epoch in range(1, config.epochs + 1):
        model.train()
        running = []
        for xb, yb in train_loader:
            xb, yb = xb.to(device, non_blocking=device.type == "cuda"), yb.to(device, non_blocking=device.type == "cuda")
            optimizer.zero_grad(set_to_none=True)
            logits = model(xb)
            loss = criterion(logits, yb)
            if hasattr(model, "prototype_regularization") and config.proto_weight > 0:
                embedding = model.embed(xb)  # type: ignore[attr-defined]
                loss = loss + config.proto_weight * model.prototype_regularization(embedding, yb)  # type: ignore[attr-defined]
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            running.append(float(loss.item()))
        scheduler.step()
        val_loss = _eval_loss(model, val_loader, criterion, device)
        history.append(
            {
                "epoch": epoch,
                "train_loss": round(float(np.mean(running)), 6),
                "val_loss": round(val_loss, 6),
                "lr": round(float(optimizer.param_groups[0]["lr"]), 8),
            }
        )
        if val_loss < best_loss - 1e-5:
            best_loss = val_loss
            best_state = copy.deepcopy(model.state_dict())
            stale = 0
        else:
            stale += 1
            if stale >= config.patience:
                break
    model.load_state_dict(best_state)
    model.eval()
    return model, {
        "best_val_loss": round(best_loss, 6),
        "epochs_run": len(history),
        "history": history,
        "scaler": scaler,
    }, asdict(config)


def predict(model: nn.Module, x: np.ndarray, device: torch.device, batch_size: int = 128) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    loader = DataLoader(
        TensorDataset(torch.tensor(x, dtype=torch.float32)),
        batch_size=batch_size,
        shuffle=False,
    )
    probs = []
    with torch.no_grad():
        for (xb,) in loader:
            logits = model(xb.to(device))
            probs.append(torch.softmax(logits, dim=-1).cpu().numpy())
    probabilities = np.concatenate(probs, axis=0) if probs else np.empty((0, 0))
    return probabilities.argmax(axis=1), probabilities


def _environment() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "torch": torch.__version__,
        "platform": platform.platform(),
        "cuda_available": torch.cuda.is_available(),
    }


def _save_result(result: dict[str, Any], output_dir: str | Path | None) -> None:
    if output_dir is None:
        return
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_loso(
    x: np.ndarray,
    y: np.ndarray,
    subjects: Sequence[str],
    model_name: str = "dualview",
    config: TrainConfig | None = None,
    class_names: Sequence[str] | None = None,
    output_dir: str | Path | None = None,
    trial_ids=None, sessions=None,
) -> dict[str, Any]:
    """Run leave-one-subject-out evaluation and return fold + aggregate metrics."""

    config = config or TrainConfig()
    features = np.asarray(x, dtype=np.float32)
    labels = np.asarray(y, dtype=np.int64)
    groups = np.asarray([str(item) for item in subjects])
    validate_feature_arrays(features, labels, groups)
    set_seed(config.seed)
    device = resolve_device(config.device)
    n_classes = int(labels.max()) + 1
    folds = loso_splits(labels, groups, val_fraction=config.val_fraction, seed=config.seed, trial_ids=trial_ids, sessions=sessions)
    fold_records: list[dict[str, Any]] = []
    oof_pred = np.full(len(labels), -1, dtype=np.int64)
    oof_prob = np.full((len(labels), n_classes), np.nan, dtype=np.float64)

    for fold in folds:
        assert_no_subject_leakage(fold, groups)
        train_idx, val_idx, test_idx = fold["train_idx"], fold["val_idx"], fold["test_idx"]
        model, training_info, config_used = _train_fold(
            features[train_idx],
            labels[train_idx],
            features[val_idx],
            labels[val_idx],
            model_name,
            n_classes,
            config,
        )
        scaler = training_info["scaler"]
        x_test = (features[test_idx] - np.asarray(scaler["mean"])) / np.asarray(scaler["std"])
        pred, prob = predict(model, x_test, device)
        oof_pred[test_idx] = pred
        oof_prob[test_idx] = prob
        metrics = compute_metrics(labels[test_idx], pred, n_classes, class_names)
        metrics.update(
            {
                "fold": fold["fold"],
                "test_subject": fold["test_subject"],
                "train_subjects": sorted(set(groups[train_idx].tolist())),
                "n_train": int(len(train_idx)),
                "n_val": int(len(val_idx)),
                "n_test": int(len(test_idx)),
            }
        )
        fold_records.append(metrics)
        if output_dir is not None:
            ckpt_dir = Path(output_dir) / "checkpoints"
            ckpt_dir.mkdir(parents=True, exist_ok=True)
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "scaler": training_info["scaler"],
                    "model_name": model_name, "n_channels": features.shape[1], "n_features": features.shape[2], "n_classes": n_classes,
                    "class_names": list(class_names) if class_names is not None else None,
                    "train_idx": train_idx.tolist(), "val_idx": val_idx.tolist(), "test_idx": test_idx.tolist(),
                    "config": config_used,
                    "fold": fold["fold"],
                    "test_subject": fold["test_subject"],
                },
                ckpt_dir / f"fold_{fold['fold']:02d}_{fold['test_subject']}.pt",
            )
        print(
            f"[LOSO {fold['fold']:02d}/{len(folds)}] test={fold['test_subject']!s:<8} "
            f"acc={metrics['accuracy']:.4f} macroF1={metrics['macro_f1']:.4f}"
        )

    if np.any(oof_pred < 0):
        raise RuntimeError("存在未被任何折预测的样本，无法计算 OOF 指标")
    overall = compute_metrics(labels, oof_pred, n_classes, class_names)
    overall["accuracy_ci_unit"] = "subject mean"
    overall["accuracy_ci95"] = bootstrap_accuracy_ci(labels, oof_pred, seed=config.seed, groups=groups)
    overall["confusion_matrix"] = compute_metrics(
        labels, oof_pred, n_classes, class_names
    )["confusion_matrix"]
    per_subject = []
    for subject in sorted(set(groups.tolist())):
        mask = groups == subject
        metrics = compute_metrics(labels[mask], oof_pred[mask], n_classes, class_names)
        per_subject.append(
            {
                "subject": subject,
                "n": int(mask.sum()),
                "accuracy": metrics["accuracy"],
                "macro_f1": metrics["macro_f1"],
            }
        )

    result: dict[str, Any] = {
        "evaluation_version": 2,
        "validation_unit": "source-subject" if len(set(groups)) > 2 else "trial" if trial_ids is not None else "sample",
        "setting": "leave-one-subject-out",
        "model": model_name,
        "n_samples": int(len(labels)),
        "n_subjects": int(len(set(groups.tolist()))),
        "n_classes": n_classes,
        "class_names": list(class_names) if class_names is not None else [str(i) for i in range(n_classes)],
        "folds": fold_records,
        "overall": overall,
        "per_subject": per_subject,
        "config": asdict(config),
        "environment": _environment(),
        "fold_description": describe_folds(folds, groups),
    }
    if output_dir is not None:
        _save_result(result, output_dir)
        np.savez_compressed(
            Path(output_dir) / "oof_predictions.npz",
            y_true=labels,
            y_pred=oof_pred,
            probabilities=oof_prob,
            subjects=groups,
        )
    return result


def run_subject_dependent(
    x: np.ndarray,
    y: np.ndarray,
    subjects: Sequence[str],
    model_name: str = "dualview",
    config: TrainConfig | None = None,
    class_names: Sequence[str] | None = None,
    output_dir: str | Path | None = None,
    trial_ids=None, sessions=None,
) -> dict[str, Any]:
    """Run the within-subject (random stratified) evaluation setting."""

    config = config or TrainConfig()
    features = np.asarray(x, dtype=np.float32)
    labels = np.asarray(y, dtype=np.int64)
    groups = np.asarray([str(item) for item in subjects])
    validate_feature_arrays(features, labels, groups)
    set_seed(config.seed)
    device = resolve_device(config.device)
    n_classes = int(labels.max()) + 1
    split = subject_dependent_split(
        labels,
        groups,
        test_fraction=0.2,
        val_fraction=config.val_fraction,
        seed=config.seed, trial_ids=trial_ids, sessions=sessions,
    )
    model, training_info, config_used = _train_fold(
        features[split["train_idx"]],
        labels[split["train_idx"]],
        features[split["val_idx"]],
        labels[split["val_idx"]],
        model_name,
        n_classes,
        config,
    )
    scaler = training_info["scaler"]
    x_test = (features[split["test_idx"]] - np.asarray(scaler["mean"])) / np.asarray(scaler["std"])
    pred, prob = predict(model, x_test, device)
    metrics = compute_metrics(labels[split["test_idx"]], pred, n_classes, class_names)
    from ..data.splits import trial_groups
    confidence_groups = trial_groups(groups, sessions, trial_ids)
    metrics["accuracy_ci95"] = bootstrap_accuracy_ci(labels[split["test_idx"]], pred, seed=config.seed,
        groups=confidence_groups[split["test_idx"]] if confidence_groups is not None else None)
    result = {
        "evaluation_version": 2,
        "split_unit": "trial" if trial_ids is not None else "sample",
        "setting": "subject-dependent",
        "model": model_name,
        "n_samples": int(len(labels)),
        "split_sizes": {key: int(len(value)) for key, value in split.items()},
        "test_metrics": metrics,
        "overall": metrics,
        "per_subject": [], "folds": [],
        "n_subjects": len(set(groups)),
        "n_classes": n_classes,
        "class_names": list(class_names) if class_names is not None else [str(i) for i in range(n_classes)],
        "split_indices": {key: value.tolist() for key, value in split.items()},
        "training": {key: value for key, value in training_info.items() if key != "scaler"},
        "config": config_used,
        "environment": _environment(),
    }
    if output_dir is not None:
        _save_result(result, output_dir)
        torch.save({"state_dict": model.state_dict(), "scaler": scaler,
                    "model_name": model_name, "n_channels": features.shape[1], "n_features": features.shape[2], "n_classes": n_classes,
                    "config": config_used, "class_names": list(class_names) if class_names is not None else None,
                    "split_indices": result["split_indices"]}, Path(output_dir) / "checkpoint.pt")
        np.savez_compressed(
            Path(output_dir) / "test_predictions.npz",
            y_true=labels[split["test_idx"]],
            y_pred=pred,
            probabilities=prob,
        )
    return result
