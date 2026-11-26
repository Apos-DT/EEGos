"""Paper-oriented SEED-IV DDA runner kept outside the EEG-EmoStudio package.

The upstream repository's SEED-IV train.py currently trains only with source
cross-entropy: its GDD/LSD calls are commented out. This sidecar reuses the
authors' Encoder/ClassClassifier definitions but implements the paper losses
and split protocol here so the host system only needs a process boundary.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import random
import platform
import scipy
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import scipy.io as sio
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
from dda_report import now, digest, save_json, read_json, write_report


SESSION_LABELS = {
    "1": [1, 2, 3, 0, 2, 0, 0, 1, 0, 1, 2, 1, 1, 1, 2, 3, 2, 2, 3, 3, 0, 3, 0, 3],
    "2": [2, 1, 3, 0, 0, 2, 0, 2, 3, 3, 2, 3, 2, 0, 1, 1, 2, 1, 0, 3, 0, 1, 3, 1],
    "3": [1, 2, 2, 1, 3, 3, 3, 1, 1, 2, 1, 0, 2, 3, 3, 0, 2, 3, 0, 0, 2, 0, 1, 0],
}
CLASS_NAMES = ["平静", "悲伤", "恐惧", "快乐"]


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_subject(path: Path, session: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mat = sio.loadmat(path, verify_compressed_data_integrity=False)
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    trial_indices: list[np.ndarray] = []
    labels = SESSION_LABELS[session]
    for trial, label in enumerate(labels, start=1):
        key = f"de_LDS{trial}"
        if key not in mat:
            raise ValueError(f"{path.name} 缺少 {key}")
        feature = np.asarray(mat[key], dtype=np.float32)
        if feature.ndim != 3 or feature.shape[0] != 62 or feature.shape[2] != 5:
            raise ValueError(f"{path.name}:{key} 形状异常：{feature.shape}")
        samples = feature.transpose(1, 0, 2).reshape(feature.shape[1], -1)
        xs.append(samples)
        ys.append(np.full(len(samples), label, dtype=np.int64))
        trial_indices.append(np.full(len(samples), trial, dtype=np.int64))
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(trial_indices)


def load_session(root: Path, session: str) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    directory = root / "eeg_feature_smooth" / session
    if not directory.is_dir():
        raise FileNotFoundError(f"SEED-IV session 目录不存在：{directory}")
    files = sorted(directory.glob("*.mat"), key=lambda p: int(p.name.split("_")[0]))
    if len(files) != 15:
        raise ValueError(f"session {session} 应有 15 个 MAT 文件，实际 {len(files)}")
    result = {}
    for path in files:
        sid = f"S{int(path.name.split('_')[0]):02d}"
        result[sid] = load_subject(path, session)
    return result


def normalize_reference(x: np.ndarray) -> np.ndarray:
    """Match UDDA/seed4/load_data.py: min-max each sample across 62 channels per band."""
    shaped = x.reshape(len(x), 62, 5)
    lo = shaped.min(axis=1, keepdims=True)
    hi = shaped.max(axis=1, keepdims=True)
    return ((shaped - lo) / np.maximum(hi - lo, 1e-6)).reshape(len(x), 310).astype(np.float32)


def gaussian_kernel(a: torch.Tensor, b: torch.Tensor, kernels: int = 5, mul: float = 2.0) -> torch.Tensor:
    values = torch.cat([a, b], dim=0)
    distances = torch.cdist(values, values, p=2).square()
    n = values.shape[0]
    denom = max(n * n - n, 1)
    bandwidth = distances.detach().sum() / denom
    bandwidth = bandwidth / (mul ** (kernels // 2))
    bandwidth = bandwidth.clamp_min(1e-6)
    return sum(torch.exp(-distances / (bandwidth * (mul ** i))) for i in range(kernels))


def gdd_loss(source: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    n, m = len(source), len(target)
    kernel = gaussian_kernel(source, target)
    return (
        kernel[:n, :n].mean()
        + kernel[n:, n:].mean()
        - 2.0 * kernel[:n, n:].mean()
    )


def lsd_loss(
    source: torch.Tensor,
    target: torch.Tensor,
    source_y: torch.Tensor,
    target_y: torch.Tensor,
    n_classes: int,
) -> torch.Tensor:
    n, m = len(source), len(target)
    kernel = gaussian_kernel(source, target)
    kss, ktt, kst = kernel[:n, :n], kernel[n:, n:], kernel[:n, n:]
    distances: dict[tuple[int, int], torch.Tensor] = {}
    for c1 in range(n_classes):
        smask = source_y == c1
        for c2 in range(n_classes):
            tmask = target_y == c2
            if not smask.any() or not tmask.any():
                continue
            dss = kss[smask][:, smask].mean()
            dtt = ktt[tmask][:, tmask].mean()
            dst = kst[smask][:, tmask].mean()
            distances[c1, c2] = dss + dtt - 2.0 * dst
    intra = [distances[c, c] for c in range(n_classes) if (c, c) in distances]
    inter = [v for (c1, c2), v in distances.items() if c1 != c2]
    if not intra or not inter:
        return source.sum() * 0.0
    return torch.stack(intra).mean() - torch.stack(inter).mean()


def accuracy(model: torch.nn.Module, x: torch.Tensor, y: torch.Tensor, device: torch.device) -> tuple[float, np.ndarray]:
    model.eval()
    predictions: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(x), 512):
            logits = model(x[start : start + 512].to(device))
            predictions.append(logits.argmax(1).cpu().numpy())
    pred = np.concatenate(predictions)
    return float(np.mean(pred == y.numpy())), pred


def score_predictions(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int = 4) -> dict[str, Any]:
    matrix = np.zeros((n_classes, n_classes), dtype=np.int64)
    np.add.at(matrix, (y_true.astype(int), y_pred.astype(int)), 1)
    total = max(int(matrix.sum()), 1)
    accuracy_value = float(np.trace(matrix) / total)
    recalls, f1s = [], []
    for cls in range(n_classes):
        tp = float(matrix[cls, cls])
        support = float(matrix[cls].sum())
        predicted = float(matrix[:, cls].sum())
        recall = tp / support if support else 0.0
        precision = tp / predicted if predicted else 0.0
        recalls.append(recall)
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    expected = float(np.dot(matrix.sum(axis=1), matrix.sum(axis=0)) / (total * total))
    kappa = (accuracy_value - expected) / (1.0 - expected) if expected < 1 else 0.0
    return {
        "n_samples": int(matrix.sum()),
        "accuracy": round(accuracy_value, 4),
        "balanced_accuracy": round(float(np.mean(recalls)), 4),
        "macro_f1": round(float(np.mean(f1s)), 4),
        "cohen_kappa": round(float(kappa), 4),
        "confusion_matrix": matrix.tolist(),
        "per_class": [
            {"class_id": c, "class_name": CLASS_NAMES[c], "support": int(matrix[c].sum()),
             "recall": round(recalls[c], 4), "f1": round(f1s[c], 4)}
            for c in range(n_classes)
        ],
    }


def make_model() -> torch.nn.Module:
    seed4 = Path(__file__).resolve().parent / "UDDA" / "seed4"
    sys.path.insert(0, str(seed4))
    from network import ClassClassifier, Encoder  # author-provided MLP architecture

    return torch.nn.Sequential(Encoder(310), ClassClassifier(4))


def train_fold(
    source_x: np.ndarray,
    source_y: np.ndarray,
    target_x: np.ndarray,
    target_y: np.ndarray,
    target_labeled: np.ndarray,
    args: argparse.Namespace,
    fold_seed: int,
) -> dict[str, Any]:
    seed_everything(fold_seed)
    source_x, target_x = normalize_reference(source_x), normalize_reference(target_x)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    device_name = torch.cuda.get_device_name(0) if device.type == "cuda" else "CPU"
    print(f"device={device} device_name={device_name}", flush=True)
    model = make_model().to(device)
    optimizer = torch.optim.SGD(model.parameters(), lr=args.lr, weight_decay=5e-4)

    sx = torch.from_numpy(source_x)
    sy = torch.from_numpy(source_y.astype(np.int64))
    tx = torch.from_numpy(target_x)
    ty = torch.from_numpy(target_y.astype(np.int64))
    tl = torch.from_numpy(target_labeled.astype(bool))
    test_mask = ~tl if args.algorithm == "SDDA" else torch.ones_like(tl, dtype=torch.bool)
    eval_x, eval_y = tx[test_mask], ty[test_mask]
    use_cuda = device.type == "cuda"
    source_loader = DataLoader(
        TensorDataset(sx, sy), batch_size=args.batch_size, shuffle=True, pin_memory=use_cuda
    )
    target_loader = DataLoader(
        TensorDataset(tx, ty, tl), batch_size=args.batch_size, shuffle=True, pin_memory=use_cuda
    )
    best_acc = -1.0
    best_pred: np.ndarray | None = None
    history: list[dict[str, float]] = []
    started = time.time()
    started_at = now()
    best_epoch = None

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_losses: list[float] = []
        for (xb, yb), (xt, yt, labeled_mask) in zip(source_loader, target_loader):
            xb, yb = xb.to(device, non_blocking=use_cuda), yb.to(device, non_blocking=use_cuda)
            xt = xt.to(device, non_blocking=use_cuda)
            yt = yt.to(device, non_blocking=use_cuda)
            labeled_mask = labeled_mask.to(device, non_blocking=use_cuda)
            sf = model[0](xb)
            tf = model[0](xt)
            source_logits = model[1](sf)
            target_logits = model[1](tf)
            ce = F.cross_entropy(source_logits, yb)
            if args.algorithm == "SDDA" and labeled_mask.any():
                source_loss_sum = F.cross_entropy(source_logits, yb, reduction="sum")
                target_loss_sum = F.cross_entropy(
                    target_logits[labeled_mask], yt[labeled_mask], reduction="sum"
                )
                ce = (source_loss_sum + target_loss_sum) / (len(yb) + int(labeled_mask.sum()))

            with torch.no_grad():
                probability = torch.softmax(target_logits, dim=1)
                confidence, pseudo = probability.max(dim=1)
                reliable = confidence >= args.pseudo_threshold
                t_alignment_y = pseudo[reliable]
            t_alignment_f = tf[reliable]

            alpha = 1.0 / (1.0 + math.exp(float(np.clip(epoch - 100.0, -60.0, 60.0))))
            if args.algorithm == "SDDA" and labeled_mask.any():
                t_alignment_y = torch.where(labeled_mask, yt, pseudo)[reliable | labeled_mask]
                t_alignment_f = tf[reliable | labeled_mask]
            if len(t_alignment_f) > 0:
                align = alpha * gdd_loss(sf, tf)
                if len(t_alignment_f) > 1:
                    align = align + (1.0 - alpha) * lsd_loss(
                        sf, t_alignment_f, yb, t_alignment_y, 4
                    )
            else:
                align = alpha * gdd_loss(sf, tf)
            loss = ce + args.beta * align
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            epoch_losses.append(float(loss.detach().cpu()))

        if epoch % args.eval_interval == 0 or epoch == args.epochs:
            model.eval()
            acc, pred = accuracy(model, eval_x, eval_y, device)
            history.append({"epoch": epoch, "evaluated_at": now(), "elapsed_seconds": round(time.time() - started, 3), "accuracy": acc, "loss": float(np.mean(epoch_losses))})
            record_event(Path(args.output_dir), "epoch_evaluated", seed=fold_seed, **history[-1])
            if acc > best_acc:
                best_acc, best_pred = acc, pred.copy()
                best_epoch = epoch
            print(f"epoch={epoch}/{args.epochs} acc={acc:.4f} best={best_acc:.4f}", flush=True)

    final_acc, final_pred = accuracy(model, eval_x, eval_y, device)
    return {
        "started_at": started_at,
        "finished_at": now(),
        "seed": fold_seed,
        "peak_epoch": best_epoch,
        "final_accuracy": final_acc,
        "final_predictions": final_pred,
        "peak_accuracy": best_acc,
        "peak_predictions": best_pred if best_pred is not None else final_pred,
        "history": history,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.data_root).resolve()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    meta = read_json(out / "run_meta.json")
    record_event(out, "data_loading_started")
    session_data = {session: load_session(root, session) for session in ("1", "2", "3")}
    files = [{"path": str(p.relative_to(root)), "size_bytes": p.stat().st_size, "sha256": digest(p)}
             for p in sorted((root / "eeg_feature_smooth").glob("*/*.mat"))]
    save_json(out / "dataset_manifest.json", {"root": str(root), "files": files})
    meta["dataset_info"] = {"name": "SEED-IV", "root": str(root), "feature": "de_LDS1–de_LDS24",
        "channels": 62, "bands": 5, "window_seconds": 4, "classes": CLASS_NAMES,
        "subjects": 15, "sessions": 3, "trials_per_subject_session": 24,
        "loaded_windows": sum(len(d[1]) for session in session_data.values() for d in session.values()),
        "loaded_files": len(files), "manifest": "dataset_manifest.json", "manifest_sha256": digest(out / "dataset_manifest.json")}
    meta["data_loaded_at"] = now()
    save_json(out / "run_meta.json", meta)
    record_event(out, "data_loading_finished", files=len(files))
    folds: list[dict[str, Any]] = []
    fold_no = 0
    if args.setting == "cross-subject":
        candidates = []
        for session in ("1", "2", "3"):
            subjects = sorted(session_data[session])
            for target_sid in subjects:
                sources = [session_data[session][sid] for sid in subjects if sid != target_sid]
                candidates.append((session, target_sid, sources, session_data[session][target_sid]))
    else:
        candidates = []
        subjects = sorted(session_data["1"])
        for target_session in ("1", "2", "3"):
            sources = [session_data[s][sid] for s in ("1", "2", "3") if s != target_session for sid in subjects]
            targets = [session_data[target_session][sid] for sid in subjects]
            candidates.append((target_session, "ALL", sources, tuple(np.concatenate([d[i] for d in targets]) for i in range(3))))
    if args.target_subject and args.setting == "cross-session":
        raise ValueError("cross-session 按论文定义将 15 名被试汇总为一个目标 session，不接受 --target-subject")
    if args.target_subject:
        candidates = [row for row in candidates if row[1] == args.target_subject]
    if args.target_session:
        candidates = [row for row in candidates if row[0] == args.target_session]
    if args.max_folds:
        candidates = candidates[: args.max_folds]
    if not candidates:
        raise ValueError("筛选后没有可运行的 fold")

    meta["planned_folds"] = len(candidates)
    save_json(out / "run_meta.json", meta)
    write_report(out)
    for session, target_sid, source_domains, target_domain in candidates:
        fold_no += 1
        source_x = np.concatenate([domain[0] for domain in source_domains])
        source_y = np.concatenate([domain[1] for domain in source_domains])
        target_x, target_y, trial_ids = target_domain
        label_trials = set(range(1, args.target_labeled_trials + 1)) if args.algorithm == "SDDA" else set()
        target_labeled = np.isin(trial_ids, list(label_trials))
        record_event(out, "fold_started", fold=fold_no, session=session, target_subject=target_sid, seed=args.seed + fold_no)
        result = train_fold(
            source_x,
            source_y,
            target_x,
            target_y,
            target_labeled,
            args,
            args.seed + fold_no,
        )
        target_test_y = target_y[~target_labeled] if args.algorithm == "SDDA" else target_y
        final_score = score_predictions(target_test_y, result["final_predictions"])
        folds.append({
            "fold": fold_no,
            "session": session,
            "target_subject": target_sid,
            "source_subjects": 14 if args.setting == "cross-subject" else 15,
            "n_source": len(source_y),
            "n_target": len(target_test_y),
            "n_target_labeled": int(target_labeled.sum()),
            **final_score,
            "final_accuracy": result["final_accuracy"],
            "paper_protocol_peak_accuracy": result["peak_accuracy"],
            "elapsed_seconds": result["elapsed_seconds"],
            "history": result["history"],
            "started_at": result["started_at"], "finished_at": result["finished_at"],
            "seed": result["seed"], "peak_epoch": result["peak_epoch"],
            "source_sessions": [session] if args.setting == "cross-subject" else [s for s in ("1", "2", "3") if s != session],
            "source_subject_ids": [f"S{i:02d}" for i in range(1, 16) if args.setting != "cross-subject" or f"S{i:02d}" != target_sid],
        })
        save_json(out / "progress.json", {"planned_folds": len(candidates), "folds": folds})
        record_event(out, "fold_finished", fold=fold_no, accuracy=result["final_accuracy"])
        write_report(out)
        print(
            f"fold={fold_no}/{len(candidates)} session={session} target={target_sid} "
            f"final={result['final_accuracy']:.4f} peak={result['peak_accuracy']:.4f}",
            flush=True,
        )

    final = [row["final_accuracy"] for row in folds]
    peak = [row["paper_protocol_peak_accuracy"] for row in folds]
    fold_confusion = np.sum([np.asarray(row["confusion_matrix"], dtype=np.int64) for row in folds], axis=0)
    rng = np.random.default_rng(args.seed)
    unit_key = "target_subject" if args.setting == "cross-subject" else "session"
    units = sorted({str(row[unit_key]) for row in folds})
    unit_scores = [float(np.mean([r["final_accuracy"] for r in folds if str(r[unit_key]) == unit])) for unit in units]
    boot = [float(np.mean(rng.choice(unit_scores, size=len(units), replace=True))) for _ in range(2000)] if len(units) > 1 else []
    per_subject = []
    for sid in sorted({row["target_subject"] for row in folds if row["target_subject"] != "ALL"}):
        subject_folds = [row for row in folds if row["target_subject"] == sid]
        per_subject.append({
            "subject": sid,
            "n": int(sum(row["n_target"] for row in subject_folds)),
            "accuracy": round(float(np.mean([row["accuracy"] for row in subject_folds])), 4),
            "macro_f1": round(float(np.mean([row["macro_f1"] for row in subject_folds])), 4),
        })
    metrics = {
        "model": f"DDA-{args.algorithm}",
        "setting": "loso" if args.setting == "cross-subject" else "cross-session",
        "n_samples": int(sum(row["n_target"] for row in folds)),
        "n_subjects": 15,
        "n_classes": 4,
        "class_names": CLASS_NAMES,
        "overall": {
            "accuracy": round(float(np.mean(final)), 4),
            "accuracy_std": round(float(np.std(final, ddof=1)) if len(final) > 1 else 0.0, 4),
            "balanced_accuracy": round(float(np.mean([r["balanced_accuracy"] for r in folds])), 4),
            "macro_f1": round(float(np.mean([r["macro_f1"] for r in folds])), 4),
            "cohen_kappa": round(float(np.mean([r["cohen_kappa"] for r in folds])), 4),
            "accuracy_ci95": [round(float(np.quantile(boot, 0.025)), 4), round(float(np.quantile(boot, 0.975)), 4)] if boot else [None, None],
            "accuracy_ci_unit": unit_key,
            "confusion_matrix": fold_confusion.tolist(),
            "paper_protocol_peak_accuracy": round(float(np.mean(peak)), 4),
            "paper_protocol_peak_std": round(float(np.std(peak, ddof=1)) if len(peak) > 1 else 0.0, 4),
        },
        "folds": folds,
        "per_subject": per_subject,
        "protocol": {
            "data": "SEED-IV official de_LDS windows, 62 channels x 5 bands",
            "fold_protocol": "cross-subject leaves one subject out within each session (45 folds); cross-session leaves one full session out (3 folds)",
            "target_labels_used_for_gradient": args.algorithm == "SDDA",
            "target_label_trials": args.target_labeled_trials if args.algorithm == "SDDA" else 0,
            "selection_uses_target_test_accuracy": True,
            "selection_note": "paper_protocol_peak_accuracy evaluates target labels every N epochs and selects the peak; final_accuracy is reported separately to expose this selection effect.",
            "normalization": "per-window min-max across 62 channels independently for each band, matching author load_data.py",
            "batch_sampling": "paired shuffled DataLoaders with zip, matching the author's train.py loop; therefore each epoch length is the shorter loader length, which differs from Algorithm 1's all-source-samples wording",
            "seed": args.seed,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "beta": args.beta,
            "pseudo_threshold": args.pseudo_threshold,
        },
    }
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    meta["training_finished_at"] = now()
    save_json(out / "run_meta.json", meta)
    write_report(out)
    return metrics


def record_event(output, event, **fields):
    heartbeat_path = Path(output) / "heartbeat.json"
    heartbeat = read_json(heartbeat_path)
    if event == "fold_started":
        heartbeat = {"fold": fields.get("fold"), "epoch": None}
    if event in ("fold_started", "epoch_evaluated", "fold_finished", "run_finished", "run_failed"):
        heartbeat.update(at=now(), event=event, **fields)
        save_json(heartbeat_path, heartbeat)
    with (Path(output) / "timeline.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": now(), "event": event, **fields}, ensure_ascii=False) + "\n")


def run_recorded(args):
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "metrics.json").exists() or (out / "timeline.jsonl").exists():
        raise ValueError("输出目录已存在实验记录，请使用新目录以保留原始结果。")
    meta = read_json(out / "run_meta.json")
    started = time.time()
    meta.update({"run_id": out.name, "status": "running", "started_at": now(),
        "source": "real", "dataset": "SEED-IV", "algorithm": args.algorithm,
        "parameters": {**vars(args), "optimizer": "SGD", "weight_decay": 0.0005, "momentum": 0,
            "dropout": 0.5, "eval_batch_size": 512, "gaussian_kernels": 5, "gaussian_mul": 2.0,
            "dynamic_alpha": "1/(1+exp(epoch-100))", "fold_seed": "base seed + 1-based fold index",
            "normalization": "per-window, per-band min-max across channels", "batch_pairing": "zip(source_loader,target_loader)"}, "external_engine": "JC-Journal-Club/DDA",
        "external_engine_commit": "1f1b2bdbbf9a1156272dfdf67831dc43fffb23d1",
        "paper_doi": "10.1109/JBHI.2022.3210158",
        "architecture": "Encoder(310→512→128→128→64) + ClassClassifier(4); see author network.py",
        "code_sha256": {p.name: digest(p) for p in (Path(__file__), Path(__file__).with_name("dda_report.py"), Path(__file__).parent / "UDDA/seed4/network.py")},
        "environment": {"python": sys.version, "python_executable": sys.executable,
            "platform": platform.platform(), "torch": torch.__version__, "numpy": np.__version__,
            "scipy": scipy.__version__, "cuda_runtime": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
            "gpu_memory_bytes": torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else None},
        "implementation_note": "External reimplementation; upstream losses disabled. Threshold=0.75 is an assumption; zip batches follow shorter loader. Test peak uses target test labels.",
    })
    (out / "code").mkdir(exist_ok=True)
    for source in (Path(__file__), Path(__file__).with_name("dda_report.py"), Path(__file__).parent / "UDDA/seed4/network.py"):
        shutil.copy2(source, out / "code" / source.name)
    save_json(out / "run_meta.json", meta)
    record_event(out, "run_started")
    try:
        if not torch.cuda.is_available():
            raise RuntimeError("本机复现要求 CUDA GPU；请检查 GPU 环境，禁止自动退回 CPU。")
        if args.algorithm == "SDDA" and not 1 <= args.target_labeled_trials <= 23:
            raise ValueError("SDDA 标签 trial 数应在 1–23，必须保留测试 trial。")
        metrics = run(args)
    except BaseException as exc:
        meta = read_json(out / "run_meta.json")
        meta.update(status="failed", finished_at=now(), elapsed_seconds=round(time.time()-started,3), error=f"{type(exc).__name__}: {exc}")
        save_json(out / "run_meta.json", meta)
        record_event(out, "run_failed", error=meta["error"])
        write_report(out)
        raise
    meta = read_json(out / "run_meta.json")
    meta.update(status="success", finished_at=now(), elapsed_seconds=round(time.time()-started,3))
    save_json(out / "run_meta.json", meta)
    record_event(out, "run_finished")
    write_report(out)
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="SEED-IV DDA paper reproduction sidecar")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--setting", choices=["cross-subject", "cross-session"], default="cross-subject")
    parser.add_argument("--algorithm", choices=["UDDA", "SDDA"], default="UDDA")
    parser.add_argument("--target-labeled-trials", type=int, default=4, choices=range(0, 25))
    parser.add_argument("--target-subject", choices=[f"S{i:02d}" for i in range(1, 16)])
    parser.add_argument("--target-session", choices=["1", "2", "3"])
    parser.add_argument("--max-folds", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=600, choices=range(1, 601))
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--eval-interval", type=int, default=10)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--beta", type=float, default=0.3)
    parser.add_argument("--pseudo-threshold", type=float, default=0.75)
    parser.add_argument("--seed", type=int, default=42)
    metrics = run_recorded(parser.parse_args())
    print(json.dumps({"accuracy": metrics["overall"]["accuracy"], "folds": len(metrics["folds"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
