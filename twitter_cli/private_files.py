from __future__ import annotations

import os
from pathlib import Path

STATE_DIR = Path.home() / ".twitter-cli"


def write_private_text(path: Path, text: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent == STATE_DIR:
        os.chmod(STATE_DIR, 0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o600)
