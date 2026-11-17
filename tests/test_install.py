from __future__ import annotations

from pathlib import Path

from tool_update_49.install import install


def test_install_copies_and_sets_mode(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"binary")
    bin_dir = tmp_path / "bin"

    destination = install(source, "tool", bin_dir)

    assert destination == bin_dir / "tool"
    assert destination.read_bytes() == b"binary"
    assert destination.stat().st_mode & 0o777 == 0o755
    assert list(bin_dir.iterdir()) == [destination]


def test_install_replaces_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"new")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    existing = bin_dir / "tool"
    existing.write_bytes(b"old")

    destination = install(source, "tool", bin_dir)

    assert destination.read_bytes() == b"new"
    assert list(bin_dir.iterdir()) == [destination]
