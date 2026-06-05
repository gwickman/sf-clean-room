"""Publish: move temp tree into the published path with package.xml LAST.

The published path is the only point at which the consumer-visible directory
is mutated. Old contents are cleared only here; ``package.xml`` is moved last
so its presence is the consumer's signal that the publish completed.
"""
from __future__ import annotations

import shutil
from pathlib import Path

SENTINEL_NAME = "package.xml"


class PublishError(RuntimeError):
    pass


def _clear_directory_contents(directory: Path) -> None:
    """Remove every child of ``directory`` while preserving the directory
    itself. The directory is created if missing."""
    directory.mkdir(parents=True, exist_ok=True)
    for child in directory.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def publish(temp_dir: Path, publish_path: Path, sentinel_name: str = SENTINEL_NAME) -> None:
    """Move every entry in ``temp_dir`` into ``publish_path``, with the sentinel
    file moved last.

    ``sentinel_name`` defaults to ``package.xml`` (v1 / get_metadata); v2 /
    get_records passes ``_field-handling-applied.csv``. Raises ``PublishError``
    if the sentinel is not present in ``temp_dir``.
    """
    temp_dir = temp_dir.resolve()
    publish_path = publish_path.resolve()

    sentinel_src = temp_dir / sentinel_name
    if not sentinel_src.exists():
        raise PublishError(f"temp tree is missing {sentinel_name}; refusing to publish")

    _clear_directory_contents(publish_path)

    for child in sorted(temp_dir.iterdir(), key=lambda p: p.name):
        if child.name == sentinel_name:
            continue
        dest = publish_path / child.name
        shutil.move(str(child), str(dest))

    # Sentinel last.
    shutil.move(str(sentinel_src), str(publish_path / sentinel_name))


def remove_empty_temp(temp_dir: Path) -> None:
    """Remove the per-run temp directory if it is empty. Silent on failure;
    callers should not let cleanup mask a successful publish."""
    try:
        temp_dir.rmdir()
    except OSError:
        pass
