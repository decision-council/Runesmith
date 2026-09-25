"""Capture screenshots of a running Runesmith Studio with headless Chrome (for the website and docs).

    python scripts/studio_shots.py <folder with a running Studio> <out dir> [page ...]

Pages are Studio routes such as ``home``, ``map/environment``, ``work``; ``cinema:N`` captures scene N
of the opening sequence. The Studio's own access link is read from its lock file; nothing is printed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = next((p for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                           r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                           "/usr/bin/google-chrome", "/usr/bin/chromium") if Path(p).exists()), None)
DEFAULT = ["home", "map/environment", "map/self", "map/development", "map/operations", "work", "goals", "inference",
           "improve", "activity/ledger", "cinema:1", "cinema:2", "cinema:4", "cinema:5", "cinema:7"]


def shoot(url: str, out: Path, size: str = "1440,900", budget_ms: int = 9000) -> None:
    profile = Path(tempfile.mkdtemp(prefix="rs-shot-"))
    try:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={size}",
                        f"--user-data-dir={profile}", "--no-first-run", "--force-device-scale-factor=1",
                        f"--virtual-time-budget={budget_ms}", f"--screenshot={out}", url],
                       check=True, capture_output=True, timeout=120)
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def main() -> None:
    folder, out = Path(sys.argv[1]), Path(sys.argv[2])
    pages = sys.argv[3:] or DEFAULT
    if not CHROME:
        raise SystemExit("no Chrome or Edge found")
    lock = json.loads((folder / ".runesmith" / "studio.lock.json").read_text(encoding="utf-8"))
    base = f"http://127.0.0.1:{lock['port']}"
    out.mkdir(parents=True, exist_ok=True)
    for page in pages:
        name = page.replace("/", "-").replace(":", "-")
        if page.startswith("cinema:"):
            url = f"{base}/cinema?scene={page.split(':')[1]}&hold"
        else:
            url = f"{base}/?t={lock['token']}&page={page}&shot=1"
        shoot(url, out / f"{name}.png")
        print("captured", name)


if __name__ == "__main__":
    main()
