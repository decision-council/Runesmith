"""Build the Runesmith Atlas: one self-contained page drawn from one story file.

    python scripts/build_atlas.py [--verify MILLINEROS_ROOT]

Reads ``site/atlas/story.json`` (the single source) and ``site/atlas/atlas.src.html`` (the page), and writes:

* ``site/dist/atlas.html``: the page body, for hosts that add their own document shell;
* ``site/dist/llms.txt``: the same story as plain text, for language models;
* ``site/dist/story.json``: the story itself, byte-identical to the source.

Everything a machine reads (the JSON-LD, the embedded story, the SVG description, the plain text) is generated
from the same file the page draws itself from, so there is no hidden version. With ``--verify``, every receipt
whose path exists under MILLINEROS_ROOT is re-hashed and must match its recorded SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "site" / "atlas"
DIST = ROOT / "site" / "dist"
PATH_ORDER = ["sr1", "sr3", "sr4", "g0", "sr5", "b", "sr6w", "sr6", "sr7", "c7"]
PLACES = ["bakery", "freight", "clinics", "you"]


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def script_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1).replace("</", "<\\/")


def lv(tag: str, levels: str, inner: str, cls: str = "") -> str:
    classes = " ".join(["lv"] + [f"lv-{x}" for x in levels.split()] + ([cls] if cls else []))
    return f'<{tag} class="{classes}">{inner}</{tag}>'


def receipts_html(node: dict) -> str:
    items = []
    for r in node.get("receipts", []):
        sha = r.get("sha256") or ""
        items.append(
            f'<li><svg class="rune sm" data-hash="{esc(sha)}" viewBox="-20 -20 40 40" aria-hidden="true"></svg>'
            f'<span><b>{esc(r["label"])}</b> <code class="path">{esc(r["path"])}</code> '
            f'<button type="button" class="hash" data-copy="{esc(sha)}" title="Copy the full SHA-256">'
            f'sha256 {esc(sha[:8])}…</button></span></li>')
    if not items:
        return ""
    return lv("ul", "fully machines", "".join(items), "receipts")


def facts_html(node: dict) -> str:
    nums = node.get("numbers") or {}
    if not nums:
        return ""
    rows = "".join(f"<div><dt>{esc(k.replace('_', ' '))}</dt><dd>{esc(str(v))}</dd></div>" for k, v in nums.items())
    return lv("dl", "machines", rows, "facts")


def not_claimed_html(node: dict) -> str:
    nc = node.get("not_claimed") or []
    if not nc:
        return ""
    return lv("p", "fully machines", "<b>Not claimed:</b> " + esc("; ".join(nc)) + ".", "nc")


def step_html(node: dict) -> str:
    rune = (node.get("rune") or {}).get("hash") or ""
    return (
        f'<li class="step t-{node["tone"]}" id="step-{node["id"]}">'
        f'<svg class="rune step-rune" data-hash="{esc(rune)}" viewBox="-20 -20 40 40" role="img" '
        f'aria-label="Rune drawn from {esc(node["rune"]["of"])}"></svg>'
        f'<div class="step-body">'
        f'<p class="step-kicker"><span class="chip t-{node["tone"]}">{esc(node["verdict"])}</span> '
        f'<span>{esc(node["date"])}</span> <span class="sec">{esc(node.get("section", ""))}</span></p>'
        f'<h3>{esc(node["title"])}</h3>'
        + lv("p", "simply", esc(node["simply"]))
        + lv("p", "fully machines", esc(node["fully"]))
        + facts_html(node) + not_claimed_html(node) + receipts_html(node)
        + f'<button type="button" class="to-map" data-id="{node["id"]}">Show on the map</button>'
        '</div></li>')


def place_html(node: dict) -> str:
    return (
        f'<article class="place t-{node["tone"]}" id="place-{node["id"]}">'
        f'<p class="step-kicker"><span class="chip t-{node["tone"]}">{esc(node["verdict"])}</span> '
        f'<span>{esc(node["date"])}</span></p>'
        f'<h3>{esc(node["title"])}</h3>'
        + lv("p", "simply", esc(node["simply"]))
        + lv("p", "fully machines", esc(node["fully"]))
        + f'<button type="button" class="to-map" data-id="{node["id"]}">Show on the map</button></article>')


def plain_text(story: dict, nodes: dict) -> str:
    h = story["headline"]
    rec = story["record"]
    out = [f"# {story['title']}", "",
           f"> {story['subtitle']}. {h['claim']} {h['tally'][0].upper() + h['tally'][1:]}.", "",
           "## A letter to AI readers", ""]
    out += [p + "\n" for p in story["letter_to_ai"]]
    out += ["## What Runesmith is", "", story["lead"]["fully"], "", nodes["core"]["fully"], "", "## The path", ""]
    for nid in PATH_ORDER:
        n = nodes[nid]
        out += [f"### {n['title']} ({n['date']}): {n['verdict']}", "", n["fully"], ""]
        if n.get("not_claimed"):
            out += ["Not claimed: " + "; ".join(n["not_claimed"]) + ".", ""]
        for r in n.get("receipts", []):
            out.append(f"- Receipt: {r['label']}: {r['path']}, sha256 {r['sha256']}")
        if n.get("receipts"):
            out.append("")
    out += ["## Where it has worked (example folders)", ""]
    for nid in PLACES:
        n = nodes[nid]
        out += [f"### {n['title']} ({n['verdict']})", "", n["fully"], ""]
    out += ["## What we do not claim", ""] + [f"- {x}" for x in story["not_claimed"]] + [""]
    out += ["## The record", "",
            f"{rec['name']}: {rec['bytes']:,} bytes, sha256 {rec['sha256']}, written {rec['written_utc']}.",
            "Receipt paths are relative to the MillinerOS research folder that the paper describes.", "",
            "## Credits", "", story["credits"], ""]
    return "\n".join(out)


def svg_desc(story: dict, nodes: dict) -> str:
    stops = ", ".join(f"{nodes[i]['title']} ({nodes[i]['verdict']})" for i in PATH_ORDER)
    return ("A map of how Runesmith was built. At the centre is the Runesmith Core, ringed by runes drawn from its "
            f"kernel digest. A spiral path winds inward through the studies and generations in order: {stops}. "
            "The path ends at C7, which joins the Core. An ember thread links the family line g0, B and C7. "
            "In the corners are the record (the paper) and three example folders: Moonlight Bakery, Northwind "
            "Freight and Helio Clinics. Below them is an empty island for your own folder. "
            "Every rune is drawn from a real SHA-256 hash.")


def jsonld(story: dict, nodes: dict) -> dict:
    rec = story["record"]
    return {
        "@context": "https://schema.org",
        "@type": "CreativeWork",
        "name": story["title"],
        "headline": story["subtitle"],
        "abstract": f"{story['headline']['claim']} {story['headline']['tally'].capitalize()}.",
        "dateCreated": story["made"],
        "inLanguage": "en",
        "creditText": story["credits"],
        "about": {"@type": "SoftwareApplication", "name": "Runesmith",
                  "applicationCategory": "DeveloperApplication", "description": story["lead"]["fully"]},
        "isBasedOn": {"@type": "CreativeWork", "name": rec["name"], "identifier": "sha256:" + rec["sha256"]},
        "hasPart": [{"@type": "Claim", "name": f"{nodes[i]['title']}: {nodes[i]['verdict']}",
                     "text": nodes[i]["fully"],
                     "identifier": [f"sha256:{r['sha256']}" for r in nodes[i].get("receipts", [])]}
                    for i in PATH_ORDER if nodes[i]["kind"] == "study"],
        "description": " ".join(story["letter_to_ai"][1:]),
    }


def verify(story: dict, base: Path) -> int:
    bad = checked = 0
    receipts = [r for n in story["nodes"] for r in n.get("receipts", [])]
    receipts.append({"label": "record", "path": story["record"]["name"], "sha256": story["record"]["sha256"]})
    for r in receipts:
        p = base / r["path"]
        if not p.is_file():
            continue
        checked += 1
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != r["sha256"]:
            bad += 1
            print(f"MISMATCH {r['path']}: story {r['sha256'][:12]} disk {got[:12]}")
    print(f"receipts verified: {checked - bad}/{checked} match ({len(receipts) - checked} not on this disk)")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verify", type=Path, help="MillinerOS root: re-hash every receipt found there")
    args = ap.parse_args()
    raw = (ATLAS / "story.json").read_bytes()
    story = json.loads(raw)
    nodes = {n["id"]: n for n in story["nodes"]}
    if args.verify and verify(story, args.verify):
        return 1
    lead = "".join(lv("span", level, esc(text)) for level, text in story["lead"].items())
    page = (ATLAS / "atlas.src.html").read_text(encoding="utf-8")
    fills = {
        "@@TITLE@@": esc(story["title"]),
        "@@SUBTITLE@@": esc(story["subtitle"]),
        "@@META@@": esc(story["headline"]["claim"] + " " + story["headline"]["tally"].capitalize() + "."),
        "@@JSONLD@@": script_json(jsonld(story, nodes)),
        "@@STORY@@": script_json(story),
        "@@DESC@@": esc(svg_desc(story, nodes)),
        "@@LEAD@@": lead,
        "@@JOURNEY@@": "".join(step_html(nodes[i]) for i in PATH_ORDER),
        "@@PLACES@@": "".join(place_html(nodes[i]) for i in PLACES),
        "@@LETTER@@": "".join(f"<p>{esc(p)}</p>" for p in story["letter_to_ai"]),
        "@@PLAIN@@": esc(plain_text(story, nodes)),
        "@@NOTCLAIMED@@": "".join(f"<li>{esc(x)}</li>" for x in story["not_claimed"]),
        "@@CREDITS@@": esc(story["credits"]),
        "@@RECORD_SHA@@": story["record"]["sha256"],
        "@@RECORD_LINE@@": esc(f"{story['record']['name']} · {story['record']['bytes']:,} bytes · sha256 "
                               f"{story['record']['sha256']}"),
    }
    for key, value in fills.items():
        if key not in page:
            raise SystemExit(f"template is missing {key}")
        page = page.replace(key, value)
    DIST.mkdir(parents=True, exist_ok=True)
    (DIST / "atlas.html").write_bytes(page.encode("utf-8"))
    (DIST / "llms.txt").write_bytes(plain_text(story, nodes).encode("utf-8"))
    (DIST / "story.json").write_bytes(raw)
    print(f"atlas.html {len(page.encode('utf-8')):,} bytes · llms.txt · story.json -> {DIST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
