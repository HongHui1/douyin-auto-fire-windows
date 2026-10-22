"""Release boundaries must reject account state even if it is explicitly listed."""
import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("release_guard", Path(__file__).resolve().parents[1] / "scripts/release_guard.py")
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)


@pytest.mark.parametrize("path", [
    "../cookie.json", "config.json", ".env", ".env.account1", ".browser-profile/Preferences",
    "output/playwright/chat.png", "config/accounts.json", "nested/cookie.json", "logs/run.log",
    "C:/private.py", "app/../secret.py", "app//secret.py",
])
def test_private_or_escaping_paths_are_rejected(path):
    with pytest.raises(ValueError):
        guard.validate_path(path)


def test_secret_detection_never_echoes_secret():
    secret = "gh" + "o_" + "A" * 36
    errors = guard.inspect_content("app/example.py", f'token="{secret}"'.encode())
    assert errors and secret not in "\n".join(errors)
    assert guard.inspect_content("config.example.json", b'{"friends": ["example"]}') == []


def test_archive_rejects_additional_hidden_state(tmp_path):
    names = [guard.MANIFEST, "LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"]
    (tmp_path / guard.MANIFEST).write_text("\n".join(names), encoding="utf-8")
    archive_path = tmp_path / "release.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name in names:
            archive.writestr("release/" + name, "example")
        archive.writestr("release/.env", "secret")
    errors = guard.inspect_archive(archive_path, tmp_path)
    assert any(".env" in error for error in errors)


def test_manifest_source_rejects_symlink_outside_project(tmp_path):
    names = [guard.MANIFEST, "LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"]
    (tmp_path / guard.MANIFEST).write_text("\n".join(names), encoding="utf-8")
    outside = tmp_path.parent / (tmp_path.name + "-private")
    outside.write_text("private", encoding="utf-8")
    for name in names[2:]:
        (tmp_path / name).write_text("example", encoding="utf-8")
    try:
        (tmp_path / "LICENSE").symlink_to(outside)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    assert any("LICENSE" in error for error in guard.inspect_source(tmp_path))
