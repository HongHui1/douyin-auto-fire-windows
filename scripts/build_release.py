"""Build a source-only ZIP from the reviewed manifest, excluding local state."""
from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from pathlib import Path

from release_guard import ROOT, inspect_archive, inspect_source, load_manifest


def build(version: str = "v1.0.0", root: Path = ROOT) -> Path:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("expected version such as v1.0.0")
    errors = inspect_source(root)
    if errors:
        raise ValueError("release check failed:\n" + "\n".join(errors))
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    name = f"douyin-auto-fire-windows-{version}"
    archive_path = dist / f"{name}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel in sorted(load_manifest(root)):
            info = zipfile.ZipInfo(f"{name}/{rel}", date_time=(2026, 10, 22, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (root / rel).read_bytes())
    errors = inspect_archive(archive_path, root)
    if errors:
        raise ValueError("archive check failed:\n" + "\n".join(errors))
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (dist / "SHA256SUMS.txt").write_text(f"{checksum}  {archive_path.name}\n", encoding="utf-8")
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v1.0.0")
    args = parser.parse_args()
    path = build(args.version)
    print(f"Built dist/{path.name} ({path.stat().st_size} bytes); SHA256SUMS.txt created")


if __name__ == "__main__":
    main()
