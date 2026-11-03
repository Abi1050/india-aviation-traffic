"""Read-only registry of the notebook's existing output files.

Milestone prefixes in file names (``review2_``, ``review3_`` or a bare leading
``_``) are hidden: each file is shown under a plain display name. Files on disk
are never renamed, moved or modified.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import settings

_PREFIX = re.compile(r"^(review\d*_|_)+", re.IGNORECASE)


def display_name(filename: str) -> str:
    if filename in settings.ARTIFACT_ALIASES:
        return settings.ARTIFACT_ALIASES[filename]
    return _PREFIX.sub("", filename) or filename


def list_artifacts(output_dir: Path = settings.OUTPUT_DIR) -> pd.DataFrame:
    """One row per display name; where several files map to the same name the most recent is used."""
    columns = ["Display name", "Type", "Description", "Size (KB)", "Modified", "Source file", "Also stored as", "Path"]
    if not output_dir.exists():
        return pd.DataFrame(columns=columns)
    rows = []
    for path in sorted(output_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in (".csv", ".png"):
            continue
        stat = path.stat()
        rows.append({"Display name": display_name(path.name), "Type": path.suffix[1:].upper(),
                     "Size (KB)": round(stat.st_size / 1024, 1), "mtime": stat.st_mtime,
                     "Modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                     "Source file": path.name, "Path": str(path)})
    if not rows:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(rows).sort_values("mtime", ascending=False)
    others = df.groupby("Display name")["Source file"].apply(list)
    df = df.drop_duplicates("Display name").copy()
    df["Also stored as"] = [", ".join(f for f in others[n] if f != src) for n, src in zip(df["Display name"], df["Source file"])]
    df["Description"] = df["Display name"].map(settings.ARTIFACT_DESCRIPTIONS).fillna("")
    return df.sort_values(["Type", "Display name"])[columns].reset_index(drop=True)


def find(display: str, output_dir: Path = settings.OUTPUT_DIR) -> Path | None:
    df = list_artifacts(output_dir)
    match = df[df["Display name"] == display]
    return Path(match["Path"].iloc[0]) if not match.empty else None


def read_csv(display: str, output_dir: Path = settings.OUTPUT_DIR) -> pd.DataFrame | None:
    path = find(display, output_dir)
    if path is None:
        return None
    try:
        return pd.read_csv(path)
    except (OSError, ValueError, pd.errors.ParserError):
        return None
