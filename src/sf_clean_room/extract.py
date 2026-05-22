"""Safe zip extraction to the per-run temp directory.

Guarantees:

* Zip-slip prevention: any entry whose resolved destination escapes the target
  is silently dropped (rare; happens only with maliciously crafted zips).
* Windows long-path support via the ``\\\\?\\`` prefix on the destination path.
* Filename sanitisation: characters illegal on Windows replaced; trailing
  dots / spaces stripped; over-long path components shortened with a stable
  hash suffix.
* A ``_path_renames.csv`` is written into the target directory recording every
  rename so the consumer can reconstruct the original layout if needed.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import sys
import zipfile
from pathlib import Path

_ILLEGAL_CHARS = set('<>:"|?*')
_MAX_COMPONENT_LEN = 120


def _win_longpath_str(p: Path) -> str:
    s = str(p.resolve())
    if sys.platform != "win32":
        return s
    if s.startswith("\\\\?\\"):
        return s
    if s.startswith("\\\\"):
        return "\\\\?\\UNC\\" + s[2:]
    return "\\\\?\\" + s


def _sanitize_component(name: str) -> str:
    cleaned = "".join(c if c not in _ILLEGAL_CHARS else "_" for c in name)
    cleaned = cleaned.rstrip(" .")
    return cleaned or "_"


def _shorten_component(name: str, maxlen: int = _MAX_COMPONENT_LEN) -> str:
    if len(name) <= maxlen:
        return name
    stem, dot, ext = name.partition(".")
    if not dot:
        ext = ""
    h = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    # Suffix is "_" + 8-char hash, plus "." + ext when an extension exists.
    suffix_len = 1 + 8 + (1 + len(ext) if ext else 0)
    keep = max(10, maxlen - suffix_len)
    return f"{stem[:keep]}_{h}{('.' + ext) if ext else ''}"


def _safe_relpath(rel: str) -> Path:
    parts = []
    for comp in Path(rel.lstrip("/")).parts:
        parts.append(_shorten_component(_sanitize_component(comp)))
    return Path(*parts)


def extract_zip_to(zip_b64: str, out_dir: Path) -> list[tuple[str, str]]:
    """Extract a base64-encoded zip into ``out_dir``. Returns the list of
    (original, written) path pairs for any entry whose path was rewritten.

    Also writes ``_path_renames.csv`` into ``out_dir`` containing the same
    pairs, so consumers reading the published folder can recover originals.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_resolved = out_dir.resolve()
    renames: list[tuple[str, str]] = []

    zbytes = base64.b64decode(zip_b64)
    with zipfile.ZipFile(io.BytesIO(zbytes), "r") as z:
        for zi in z.infolist():
            if zi.filename.endswith("/"):
                continue
            original = Path(zi.filename).as_posix().lstrip("/")
            safe_rel = _safe_relpath(original)
            dest = (out_dir / safe_rel).resolve()
            try:
                dest.relative_to(out_resolved)
            except ValueError:
                # zip-slip attempt: destination escapes out_dir
                continue
            os.makedirs(_win_longpath_str(dest.parent), exist_ok=True)
            with z.open(zi, "r") as src, open(_win_longpath_str(dest), "wb") as dst:
                dst.write(src.read())
            written = safe_rel.as_posix()
            if written != original:
                renames.append((original, written))

    if renames:
        log = out_dir / "_path_renames.csv"
        with open(_win_longpath_str(log), "w", encoding="utf-8", newline="") as f:
            f.write("original,extracted\n")
            for o, n in renames:
                f.write(f"{o},{n}\n")
    return renames
