"""Text colours are readable in both themes (journey J9-F6: light theme status colours were 1.9-3.5:1).

The colours are read from the stylesheet itself, so a later tweak cannot quietly fall below WCAG AA (4.5:1).
"""
from __future__ import annotations

import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "runesmith" / "app" / "static" / "app.css").read_text(encoding="utf-8")


def block(selector: str) -> dict[str, str]:
    body = CSS.split(selector + " {", 1)[1].split("}", 1)[0]
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", body))


def luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_text_and_status_colours_reach_aa_on_both_themes():
    dark, light = block(":root"), {**block(":root"), **block(':root[data-theme="light"]')}
    for name, theme in (("dark", dark), ("light", light)):
        for fg in ("--text", "--text-2", "--text-3", "--good", "--warn", "--bad"):
            for bg in ("--bg", "--bg-2"):
                assert ratio(theme[fg], theme[bg]) >= 4.5, (name, fg, bg, round(ratio(theme[fg], theme[bg]), 2))


def test_links_are_readable_on_the_light_theme():
    link = re.search(r':root\[data-theme="light"\] a \{ color: (#[0-9a-fA-F]{6}); \}', CSS).group(1)
    light = {**block(":root"), **block(':root[data-theme="light"]')}
    assert ratio(link, light["--bg"]) >= 4.5 and ratio(link, "#ffffff") >= 4.5
