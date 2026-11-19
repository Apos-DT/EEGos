"""Command-line interface for EEG-EmoStudio."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from . import __version__
from .audit.runner import run_workspace_audit
from .audit.quality import (
    combine_quality_tables,
    load_quality_table,
    select_balanced,
    selection_markdown,
)
from .data.manifest import load_features
from .data.seed_iv import audit_seed_iv, build_seed_iv
from .data.eeglab import process_eeglab_set
from .pipeline import build_features_from_raw
from .reporting.figures import plot_confusion_matrix, plot_subject_accuracy
from .reporting.html import render_loso_report

QUALITY_FILES = {
    "video": "research/quality/video/视频质量排序.csv",
    "audio": "research/quality/audio/音乐歌曲质量排序.csv",
}


def _cmd_audit(args: argparse.Namespace) -> int:
    report = run_workspace_audit(
        workspace=args.workspace,
        out_dir=args.out,
        probe_media=args.probe_media,
    )
    print(f"[audit] 输出目录: {Path(args.out).resolve()}")
    for kind, survey in report.get("surveys", {}).items():
        print(
            f"  {kind}: raw={survey['raw_rows']} dedup={survey['dedup_rows']} "
            f"raters={survey['n_raters']} stimuli={survey['n_stimuli']} "
            f"duplicates={survey['duplicate_rows']}"
        )
    print(f"  summary: {Path(args.out).resolve() / 'audit_summary.json'}")
    return 0


def _cmd_select(args: argparse.Namespace) -> int:
    root = Path(args.workspace).resolve()
    tables = {}
    for kind, relative in QUALITY_FILES.items():
        path = root / relative
        if path.exists():
            tables[kind] = load_quality_table(path, kind=kind)
    if not tables:
        print("[select] 未找到质量排序文件；请先运行质量评分流程", file=sys.stderr)
        return 2
    combined = combine_quality_tables(tables.get("video"), tables.get("audio"))
    modalities = tuple(item.strip() for item in args.modalities.split(",") if item.strip())
    selected, summary = select_balanced(
        combined,
        per_class=args.per_class,
        min_grade=args.min_grade,
        modalities=modalities,
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    selected.to_csv(out / "selected_materials.csv", index=False, encoding="utf-8-sig")
    (out / "selection_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "selection_report.md").write_text(selection_markdown(selected, summary), encoding="utf-8")
    print(f"[select] 已选 {len(selected)} 条 → {out.resolve()}")
    for warning in summary["warnings"]:
        print(f"  WARNING: {warning}")
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    from .demo import run_demo

    result = run_demo(
        args.out,
        epochs=args.epochs,
        model=args.model,
        n_subjects=args.subjects,
        n_per_class=args.per_class,
        seed=args.seed,
    )
    overall = result["overall"]
    print(
        f"[demo] accuracy={overall['accuracy']:.4f} macroF1={overall['macro_f1']:.4f} "
        f"kappa={overall['cohen_kappa']:.4f}"
    )
    print(f"  report: {(Path(args.out) / 'report.html').resolve()}")
    print("  注意：演示数据为合成特征，仅用于验证软件流水线。")
    return 0


def _cmd_seed_iv(args: argparse.Namespace) -> int:
    sessions = tuple(int(item) for item in args.sessions.split(",") if item.strip())
    subjects = tuple(int(item) for item in args.subjects.split(",")) if args.subjects else None
    if args.audit_only:
        summary = audit_seed_iv(args.root, feature_key=args.feature, sessions=sessions, subjects=subjects)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    out = args.out or (
        "data/processed/seed_iv_de_LDS_trial.npz"
        if args.aggregate == "trial"
        else "data/processed/seed_iv_de_LDS.npz"
    )
    summary = build_seed_iv(
        root=args.root,
        output=out,
        feature_key=args.feature,
        sessions=sessions,
        subjects=subjects,
        aggregate=args.aggregate,
    )
    print(
        f"[seed-iv] {summary['n_subjects']} 被试 · {summary['n_trials']} trials · "
        f"{summary.get('aggregation', 'window')} · "
        f"{summary['n_samples']} windows · {summary['n_channels']} ch × {summary['n_bands']} bands"
    )
    print(f"  output: {Path(summary['output']).resolve()}")
    print(f"  manifest: {Path(summary['manifest']).resolve()}")
    print(f"  class windows: {summary['class_counts_windows']}")
    return 0


def _cmd_eeglab(args: argparse.Namespace) -> int:
    band = tuple(float(item) for item in args.bandpass.split(","))
    if len(band) != 2:
        raise SystemExit("--bandpass 需要两个逗号分隔的频率")
    result = process_eeglab_set(
        args.input,
        args.out,
        subject=args.subject,
        bandpass=(band[0], band[1]),
        notch_hz=args.notch,
        target_fs=args.target_fs,
        rereference=args.reref,
        epoch_start=args.epoch_start,
        epoch_end=args.epoch_end,
        reject_uv=args.reject,
        event_map_text=args.event_map,
        window_s=args.window,
        run_ica=args.ica,
    )
    print(f"[eeglab] {result['n_channels']} ch · {result['duration_s']} s · {result['n_events']} events")
    print(f"  clean: {Path(args.out, 'eeg_clean.npz').resolve()}")
    if result.get("training"):
        print(f"  raw: {result['training']['raw']}")
        print(f"  features: {result['training']['features']} ({result['training']['n_trials']} trials)")
    else:
        print("  未检测到可映射事件；只输出连续清洗数据，未生成训练集。")
    return 0


def _cmd_features(args: argparse.Namespace) -> int:
    summary = build_features_from_raw(
        raw_path=args.raw,
        output_path=args.out,
        fs=args.fs,
        window_s=args.window,
        step_s=args.step,
        aggregate=args.aggregate,
        notch_hz=None if args.no_notch else args.notch,
        target_fs=args.target_fs,
    )
    print(f"[features] {summary['n_samples']} 样本 × {summary['n_channels']} 通道 × {summary['n_bands']} 频带")
    print(f"  output: {Path(summary['features']).resolve()}")
    return 0


def _cmd_train(args: argparse.Namespace) -> int:
    from .training.trainer import TrainConfig, run_loso, run_subject_dependent

    data = load_features(args.data)
    x, y, subjects = data["x"], data["y"], data["subjects"]
    n_classes = int(y.max()) + 1
    class_names = data["class_names"]
    if class_names is None or len(class_names) < n_classes:
        class_names = np.asarray([f"class_{index}" for index in range(n_classes)])
    class_names = [str(item) for item in class_names[:n_classes]]
    config = TrainConfig(
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        weight_decay=args.weight_decay,
        patience=args.patience,
        seed=args.seed,
        device=args.device,
        hidden=args.hidden,
        dropout=args.dropout,
        n_prototypes=args.prototypes,
        proto_weight=args.proto_weight,
    )
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.setting == "loso":
        result = run_loso(
            x,
            y,
            subjects,
            model_name=args.model,
            config=config,
            class_names=class_names,
            output_dir=output_dir,
        )
        matrix_path = plot_confusion_matrix(
            result["overall"]["confusion_matrix"],
            class_names,
            output_dir / "figures" / "confusion_matrix.png",
            title=f"{args.model} · LOSO",
        )
        subject_path = plot_subject_accuracy(
            result["per_subject"],
            output_dir / "figures" / "per_subject_accuracy.png",
            chance=1.0 / n_classes,
        )
        render_loso_report(
            result,
            output_dir / "report.html",
            [matrix_path, subject_path],
            title="EEG 情绪识别跨被试（LOSO）训练报告",
        )
        print(
            f"[train] LOSO accuracy={result['overall']['accuracy']:.4f} "
            f"macroF1={result['overall']['macro_f1']:.4f} "
            f"kappa={result['overall']['cohen_kappa']:.4f}"
        )
    else:
        result = run_subject_dependent(
            x,
            y,
            subjects,
            model_name=args.model,
            config=config,
            class_names=class_names,
            output_dir=output_dir,
        )
        print(
            f"[train] subject-dependent accuracy={result['test_metrics']['accuracy']:.4f} "
            f"macroF1={result['test_metrics']['macro_f1']:.4f}"
        )
    print(f"  report: {(output_dir / 'report.html').resolve()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eeg-emostudio",
        description="EEG-EmoStudio：脑电情绪识别数据制备与模型训练工作台",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="审计本地刺激/问卷/质量数据")
    audit.add_argument("--workspace", default=".", help="项目根目录")
    audit.add_argument("--out", default="artifacts/audit", help="输出目录")
    audit.add_argument("--probe-media", action="store_true", help="读取媒体真实时长（较慢）")
    audit.set_defaults(func=_cmd_audit)

    select = sub.add_parser("select", help="按模态×四象限选择平衡刺激材料")
    select.add_argument("--workspace", default=".")
    select.add_argument("--out", default="artifacts/selection")
    select.add_argument("--per-class", type=int, default=10, dest="per_class")
    select.add_argument("--min-grade", default="D", choices=["S", "A", "B", "C", "D"])
    select.add_argument("--modalities", default="video,audio")
    select.set_defaults(func=_cmd_select)

    demo = sub.add_parser("demo", help="运行合成数据端到端演示")
    demo.add_argument("--out", default="artifacts/demo")
    demo.add_argument("--epochs", type=int, default=40)
    demo.add_argument("--model", default="dualview", choices=["mlp", "dgcnn", "dualview"])
    demo.add_argument("--subjects", type=int, default=8)
    demo.add_argument("--per-class", type=int, default=30, dest="per_class")
    demo.add_argument("--seed", type=int, default=42)
    demo.set_defaults(func=_cmd_demo)

    eeglab = sub.add_parser("eeglab", help="导入 EEGLAB .set/.fdt 并清洗原始 EEG")
    eeglab.add_argument("--input", required=True, help="EEGLAB .set 文件")
    eeglab.add_argument("--out", required=True, help="输出目录")
    eeglab.add_argument("--subject", default="", help="被试编号；留空读 EEG.subject")
    eeglab.add_argument("--bandpass", default="0.1,70", help="带通，例如 0.5,45")
    eeglab.add_argument("--notch", type=float, default=50.0, help="陷波频率；0 表示关闭")
    eeglab.add_argument("--target-fs", type=float, default=200.0, help="重采样目标；0 表示不重采样")
    eeglab.add_argument("--reref", default="car", choices=["none", "car"], help="重参考")
    eeglab.add_argument("--epoch-start", type=float, default=-0.2, help="事件前窗口（秒）")
    eeglab.add_argument("--epoch-end", type=float, default=4.0, help="事件后窗口（秒）")
    eeglab.add_argument("--reject", type=float, default=150.0, help="峰峰值拒绝阈值（µV）")
    eeglab.add_argument("--event-map", default="1=0,2=1,3=2,4=3", help="事件码=类别")
    eeglab.add_argument("--window", type=float, default=1.0, help="DE 窗口（秒）")
    eeglab.add_argument("--ica", action="store_true", help="额外保存 ICA 分解（不自动剔除）")
    eeglab.set_defaults(func=_cmd_eeglab)

    seed_iv = sub.add_parser("seed-iv", help="接入 SEED-IV 官方特征并构建特征数据集")
    seed_iv.add_argument("--root", default="data/SEED_IV", help="SEED-IV 根目录")
    seed_iv.add_argument("--out", default=None, help="输出 features.npz；留空按 aggregate 自动命名")
    seed_iv.add_argument("--feature", default="de_LDS", choices=["de_LDS", "de_movingAve", "psd_LDS", "psd_movingAve"])
    seed_iv.add_argument("--sessions", default="1,2,3", help="逗号分隔，例如 1,2,3")
    seed_iv.add_argument("--subjects", default="", help="逗号分隔，例如 1,2；留空为 1..15")
    seed_iv.add_argument("--aggregate", default="window", choices=["window", "trial"], help="window=保留每个4s窗；trial=每trial取均值")
    seed_iv.add_argument("--audit-only", action="store_true", help="只审计，不写数据集")
    seed_iv.set_defaults(func=_cmd_seed_iv)

    features = sub.add_parser("features", help="从 raw.npz 提取 DE 特征")
    features.add_argument("--raw", required=True)
    features.add_argument("--out", required=True)
    features.add_argument("--fs", type=float, default=None)
    features.add_argument("--target-fs", type=float, default=None)
    features.add_argument("--window", type=float, default=1.0)
    features.add_argument("--step", type=float, default=None)
    features.add_argument("--aggregate", choices=["mean", "std", "concat"], default="mean")
    features.add_argument("--notch", type=float, default=50.0)
    features.add_argument("--no-notch", action="store_true")
    features.set_defaults(func=_cmd_features)

    train = sub.add_parser("train", help="训练并评估特征模型")
    train.add_argument("--data", required=True, help="features.npz")
    train.add_argument("--out", default="artifacts/train")
    train.add_argument("--model", default="dualview", choices=["mlp", "dgcnn", "dualview", "eegnet"])
    train.add_argument("--setting", choices=["loso", "subject-dependent"], default="loso")
    train.add_argument("--epochs", type=int, default=60)
    train.add_argument("--batch-size", type=int, default=32)
    train.add_argument("--lr", type=float, default=1e-3)
    train.add_argument("--weight-decay", type=float, default=1e-4)
    train.add_argument("--patience", type=int, default=12)
    train.add_argument("--seed", type=int, default=42)
    train.add_argument("--device", default="auto")
    train.add_argument("--hidden", type=int, default=32)
    train.add_argument("--dropout", type=float, default=0.25)
    train.add_argument("--prototypes", type=int, default=2)
    train.add_argument("--proto-weight", type=float, default=0.1)
    train.set_defaults(func=_cmd_train)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
