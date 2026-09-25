"""Build the Runesmith website: one self-contained HTML page with the real opening sequence and Studio screenshots.

    python scripts/build_site.py

Reads ``site/src/page.html``, bundles the Studio's genesis engine (``icons.js``, ``core.js``, ``genesis.js`` and
``genesis.css``) into it, inlines the screenshots from ``site/shots/<case>/`` as data URIs (``@SHOT:case/name@``;
WebP when Pillow is installed, which makes the page several times lighter), and writes:

* ``site/dist/runesmith.html``: the page body, for hosts that add their own document shell;
* ``site/dist/index.html``: a complete document, for any static host.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "runesmith" / "app" / "static"
SITE = ROOT / "site"


def bundle_js() -> str:
    parts = []
    for name in ("icons.js", "core.js", "genesis.js"):
        text = (STATIC / "js" / name).read_text(encoding="utf-8")
        text = re.sub(r"^import\s+\{[^}]*\}\s+from\s+'[^']+';\s*$", "", text, flags=re.M)
        text = re.sub(r"^export\s+(?=(async\s+)?(function|const|class|let)\b)", "", text, flags=re.M)
        parts.append(f"// ---- {name}\n{text}")
    body = "\n".join(parts)
    return ("(function () {\n'use strict';\n" + body +
            "\nwindow.RunesmithSite = { runGenesis: runGenesis, iconSvg: iconSvg, LOGO: LOGO, KIND: KIND, "
            "BAND_COLOR: BAND_COLOR, STORIES: STORIES };\n})();")


def data_uri(path: Path) -> str:
    raw = path.read_bytes()
    try:
        from PIL import Image
    except ImportError:
        return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    out = io.BytesIO()
    with Image.open(io.BytesIO(raw)) as image:
        image.convert("RGB").save(out, "WEBP", quality=90, method=6)
    if out.tell() >= len(raw):
        return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    return "data:image/webp;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def build() -> dict[str, int]:
    page = (SITE / "src" / "page.html").read_text(encoding="utf-8")
    css = (STATIC / "genesis.css").read_text(encoding="utf-8")
    js = bundle_js()
    if "</script" in js.lower():
        raise SystemExit("the bundle must not contain a closing script tag")
    page = page.replace("/*@GENESIS_CSS@*/", css).replace("/*@GENESIS_JS@*/", js)
    missing, cache = [], {}

    def shot(match: re.Match) -> str:
        name = match.group(1)
        path = SITE / "shots" / f"{name}.png"
        if not path.exists():
            missing.append(name)
            return ""
        if name not in cache:
            cache[name] = data_uri(path)
        return cache[name]

    page = re.sub(r"@SHOT:([a-z0-9-]+(?:/[a-z0-9-]+)?)@", shot, page)
    if missing:
        raise SystemExit(f"missing screenshots: {sorted(set(missing))} (run scripts/studio_shots.py)")
    out = SITE / "dist"
    out.mkdir(parents=True, exist_ok=True)
    (out / "runesmith.html").write_bytes(page.encode("utf-8"))
    full = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + page.replace("<nav ", "</head>\n<body>\n<nav ", 1) + "\n</body>\n</html>\n")
    (out / "index.html").write_bytes(full.encode("utf-8"))
    return {"bytes": len(page.encode("utf-8")), "bundle": len(js), "screenshots": len(cache)}


if __name__ == "__main__":
    print(build())
