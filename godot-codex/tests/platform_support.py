import os
from pathlib import Path
import tempfile

def can_symlink():
    if not hasattr(os, "symlink"):
        return False
    with tempfile.TemporaryDirectory(prefix="godot-symlink-probe-") as folder:
        root=Path(folder)
        (root/"target").write_text("probe",encoding="utf-8")
        try:
            (root/"link").symlink_to(root/"target")
        except OSError:
            return False
        return (root/"link").is_symlink()

SYMLINK_AVAILABLE=can_symlink()
