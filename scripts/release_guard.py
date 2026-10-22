"""Check an explicit release manifest; never print matched secret values."""
from __future__ import annotations

import argparse
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "release-files.txt"
FORBIDDEN_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".browser-profile", "browser-profile", "storage_state", "artifacts",
    "logs", "output", "diag", "dist",
}
SAFE_DOTFILES = {".env.example", ".env.account.example", ".gitignore", ".gitattributes"}
SAFE_SUFFIXES = {".py", ".md", ".json", ".ps1", ".txt", ".yml", ".ini"}
SECRET_PATTERNS = {
    "GitHub access token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "credential in URL": re.compile(r"https?://[^\s/:@]+:[^\s/@]+@[A-Za-z0-9.-]+"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE" + r" KEY-----"),
    "Windows user path": re.compile(r"\b[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+", re.I),
}


def validate_path(name: str) -> None:
    path = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or path.is_absolute() or any(p in {"", ".", ".."} for p in name.split("/")):
        raise ValueError("unsafe relative path")
    if any(part.lower() in FORBIDDEN_DIRS for part in path.parts):
        raise ValueError("private/runtime directory")
    lower = path.name.lower()
    if lower not in SAFE_DOTFILES:
        if lower.startswith((".env", "cookie", ".douyin-cookie", "storage")):
            raise ValueError("credential filename")
        if lower in {"config.json", "accounts.json", "tasks.json", "history.json", "last-success.txt"}:
            raise ValueError("local configuration/history")
        if path.suffix.lower() not in SAFE_SUFFIXES and name not in {"LICENSE"}:
            raise ValueError("file type not allowed")


def load_manifest(root: Path = ROOT) -> list[str]:
    names = [line.strip() for line in (root / MANIFEST).read_text(encoding="utf-8-sig").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(names) != len(set(names)):
        raise ValueError("duplicate release path")
    if not {MANIFEST, "LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"}.issubset(names):
        raise ValueError("manifest must include itself, license, README and attribution")
    for name in names:
        validate_path(name)
    return names


def inspect_content(name: str, data: bytes) -> list[str]:
    try:
        validate_path(name)
        text = data.decode("utf-8-sig")
    except (ValueError, UnicodeError) as exc:
        return [f"{name}: {type(exc).__name__} (path/type/encoding)"]
    if "\x00" in text:
        return [f"{name}: unexpected binary content"]
    return [f"{name}: {label}" for label, pattern in SECRET_PATTERNS.items() if pattern.search(text)]


def inspect_source(root: Path = ROOT, *, tracked: bool = False) -> list[str]:
    names = load_manifest(root)
    errors = []
    for name in names:
        path = root / name
        ancestors = [root / rel for rel in [PurePosixPath(name), *PurePosixPath(name).parents]]
        if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()) for p in ancestors):
            errors.append(f"{name}: symlink/junction not allowed")
        elif not path.resolve().is_relative_to(root.resolve()):
            errors.append(f"{name}: path outside project")
        elif not path.is_file():
            errors.append(f"{name}: missing release file")
        else:
            errors.extend(inspect_content(name, path.read_bytes()))
    if tracked:
        result = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True)
        actual = set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) - {""}
        errors.extend(f"{name}: tracked but not in manifest" for name in sorted(actual - set(names)))
        errors.extend(f"{name}: manifest file not tracked" for name in sorted(set(names) - actual))
    return errors


def inspect_archive(path: Path, root: Path = ROOT) -> list[str]:
    expected = set(load_manifest(root))
    errors = []
    seen = set()
    prefixes = set()
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            parts = info.filename.split("/", 1)
            if len(parts) != 2 or not parts[0] or info.is_dir():
                errors.append("archive must contain files under exactly one top-level directory")
                continue
            prefix, name = parts
            prefixes.add(prefix)
            if name not in expected or name in seen:
                errors.append(f"{name}: unexpected/duplicate archive member")
            seen.add(name)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                errors.append(f"{name}: archive symlink not allowed")
            errors.extend(inspect_content(name, archive.read(info)))
    if len(prefixes) != 1 or any(p in {".", ".."} or "\\" in p or ":" in p for p in prefixes):
        errors.append("invalid archive root")
    errors.extend(f"{name}: missing from archive" for name in sorted(expected - seen))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracked", action="store_true", help="also require Git paths to exactly match manifest")
    parser.add_argument("--zip", type=Path, help="also inspect final archive")
    args = parser.parse_args()
    try:
        errors = inspect_source(tracked=args.tracked)
        if args.zip:
            errors.extend(inspect_archive(args.zip))
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f"Release check failed: {type(exc).__name__}")
        return 1
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Release privacy check passed: {len(load_manifest())} allowlisted files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
