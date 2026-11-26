"""Create and verify a portable workspace backup, or restore into a new directory.

Run with collection and training paused so database and external files describe
the same research state. SQLite backup includes committed WAL transactions.
"""
from __future__ import annotations

from contextlib import closing
import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verify(directory):
    root = Path(directory).resolve()
    manifest = json.loads((root / "backup.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or digest(path) != expected:
            raise ValueError(f"备份文件缺失或校验失败 {relative}")
    db = (root / "database.sqlite3").as_uri() + "?mode=ro"
    with closing(sqlite3.connect(db, uri=True)) as connection:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("数据库完整性检查失败")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("数据库外键检查失败")
    return manifest


def backup(database, roots, destination):
    destination = Path(destination).resolve()
    for source in roots.values():
        if destination.is_relative_to(Path(source).resolve()):
            raise ValueError("备份输出应位于源数据目录外")
    destination.mkdir(parents=True, exist_ok=False)
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(destination / "database.sqlite3")) as target:
            source.backup(target)
    excluded = {Path(str(database) + suffix).resolve() for suffix in ("", "-wal", "-shm")}
    for label, source in roots.items():
        source = Path(source).resolve()
        if not source.exists():
            continue
        for path in source.rglob("*"):
            if not path.is_file() or path.resolve() in excluded:
                continue
            if path.is_symlink():
                raise ValueError(f"请先核实符号链接的备份范围 {path}")
            before = digest(path)
            target = destination / label / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            if before != digest(target) or before != digest(path):
                raise ValueError(f"备份期间文件发生变化 {path}")
    files = {p.relative_to(destination).as_posix(): digest(p)
             for p in destination.rglob("*") if p.is_file()}
    (destination / "backup.json").write_text(json.dumps({
        "version": 1, "created_at": datetime.now().astimezone().isoformat(),
        "source_roots": {k: str(Path(v).resolve()) for k, v in roots.items()},
        "files": files,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    verify(destination)
    return destination


def restore(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    verify(source)
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("恢复目录与备份目录必须独立")
    shutil.copytree(source, destination)
    verify(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "verify", "restore"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.action == "backup":
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from webapp.db import database_path
        from eeg_emostudio.paths import DATA_DIR, ARTIFACTS_DIR, DELIVERABLES_DIR
        if args.out is None:
            parser.error("backup需要--out")
        print(backup(database_path(), {"data": DATA_DIR, "artifacts": ARTIFACTS_DIR,
                                      "deliverables": DELIVERABLES_DIR}, args.out))
    elif args.action == "restore":
        if args.source is None or args.out is None:
            parser.error("restore需要--source和--out")
        print(restore(args.source, args.out))
    else:
        if args.source is None:
            parser.error("verify需要--source")
        manifest = verify(args.source)
        print(f"校验通过 {len(manifest['files'])} 个文件")


if __name__ == "__main__":
    main()
