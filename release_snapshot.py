#!/usr/bin/env python3
"""Create a versioned inspection release snapshot.

This keeps the project's real source-of-truth state together in one place:
- reviews/
- knowledge/
- data/inspection_memory.db
- models/best.pt

A manifest is written with SHA256 hashes so the exact release state can be
recovered and compared later.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "inspection_state"


def default_source_paths() -> list[str]:
    if STATE_DIR.exists():
        return [
            "inspection_state/reviews",
            "inspection_state/knowledge",
            "inspection_state/data/inspection_memory.db",
            "inspection_state/models/best.pt",
        ]
    return [
        "reviews",
        "knowledge",
        "data/inspection_memory.db",
        "models/best.pt",
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for rel in paths:
        target = ROOT / rel
        if not target.exists():
            continue
        if target.is_dir():
            for child in sorted(target.rglob("*")):
                if child.is_file() and child not in seen:
                    files.append(child)
                    seen.add(child)
        elif target.is_file() and target not in seen:
            files.append(target)
            seen.add(target)
    return sorted(files, key=lambda p: str(p.relative_to(ROOT)).lower())


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def build_manifest(tag: str) -> dict:
    paths = default_source_paths()
    files = iter_files(paths)
    manifest = {
        "release": tag,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": git_commit(),
        "root": str(ROOT.relative_to(ROOT)),
        "source_bundle": paths,
        "files": [],
    }
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        manifest["files"].append({
            "path": rel,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        })
    return manifest


def copy_release_artifacts(tag: str, manifest_path: Path) -> None:
    release_dir = manifest_path.parent
    bundle_dir = release_dir / "bundle"
    archive_path = release_dir / f"{tag}_inspection_state.zip"

    shutil.rmtree(bundle_dir, ignore_errors=True)
    if archive_path.exists():
        archive_path.unlink()
    bundle_dir.mkdir(parents=True, exist_ok=True)

    for rel in default_source_paths():
        src = ROOT / rel
        if not src.exists():
            continue
        dst = bundle_dir / rel
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(release_dir)))

    shutil.rmtree(bundle_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a versioned inspection release snapshot")
    parser.add_argument("--tag", default=None, help="Release tag, e.g. v2026-09-14")
    parser.add_argument("--out-dir", default="releases", help="Directory to store the release snapshot")
    args = parser.parse_args()

    tag = args.tag or datetime.now(timezone.utc).strftime("v%Y-%m-%d-%H%MZ")
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = out_dir / tag
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(tag)
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    copy_release_artifacts(tag, manifest_path)

    print(f"Created release snapshot: {snapshot_dir}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
