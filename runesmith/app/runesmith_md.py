"""RUNESMITH.md: Runesmith's own log of what it did in a project folder.

Every folder the Studio works in gets a ``RUNESMITH.md`` at its top: a short header (what Runesmith is, its mark, the
version) and below it one line for each event, newest last, in plain words: a milestone done, a build applied, checks
approved or withdrawn, the owner's decisions, milestones added or removed, and which model wrote the code.

Rules this module keeps:

* **On by default, off means never touched.** The ``runesmith_md`` setting switches it. Off, and in Observe mode (where
  Runesmith only looks), the file is neither created nor changed.
* **Names and counts only.** Never a prompt, a model's answer, a file's contents, an error dump, a key or a link: every
  line is made from one plain sentence's facts, and whatever looks like a secret (or equals a key the home keeps) is
  replaced before anything is written.
* **Append-only, and bounded.** A new line goes to the end. Only the newest ``MAX_ENTRIES`` lines are kept; a line at
  the top says how many older ones were trimmed.
* **It is Runesmith's own file.** It is never part of the project's source for models, drafts cannot write it, and an
  undo or a restore never touches it (``is_own`` is the one name every such place asks).
* **A log must never break the work.** Every function here swallows its own errors.

A RUNESMITH.md that was not written by Runesmith (no header marker) is left alone.
"""

from __future__ import annotations

import functools
import re
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any

from runesmith import __version__, atomic

FILE_NAME = "RUNESMITH.md"
MAX_ENTRIES = 1000                  # the newest entries kept; the line at the top counts what was trimmed
MAX_LINE = 240                      # characters of one entry's text
MAX_FILES_NAMED = 12
MAX_TITLE = 80

# The mark (a stone block with the R rune carved through it, its leg breaking out of the bottom edge), made from the
# real artwork: the SVG drawn at 240 px, area-averaged to a 24 by 24 grid and every two rows joined into one line of
# █ ▀ ▄ and spaces. The block is the stone, the spaces are the carved rune.
LOGO = (
    " ▄▄██████████████████▄▄",
    "▄█████▀▀▀▀▀████████████▄",
    "██████      ▀███████████",
    "██████        ▀█████████",
    "██████    █▄    ▀███████",
    "██████    ██▀   ▄███████",
    "██████    ▀   ▄█████████",
    "██████      ▄███████████",
    "██████    ▄█████████████",
    "██████     ▀████████████",
    "▀█████▄▄▄▄   ▀█████████▀",
    " ▀▀████████▄   ▀█████▀▀",
)

INTRO = ("Runesmith is an open-source system that plans software as milestones, has AI models write the code and checks "
         "every step. This file is Runesmith's own log of what it did in this folder: one line for each event, newest "
         "last, with no prompts, model answers or file contents. Runesmith writes it, so please leave it alone; you "
         "can turn it off in the Studio's Settings.")
_LOG_HEADING = "\n## Log\n\n"
_ENTRY = re.compile(r"^- \d{4}-\d\d-\d\d \d\d:\d\dZ: ")
_TRIMMED = re.compile(r"^- Older entries were trimmed: (\d+) earlier ")

_LOCK = threading.RLock()           # the worker and the web threads write from different threads


def is_own(path: Any) -> bool:
    """Whether this path (or bare name) is Runesmith's own log. Compared without case: Windows and macOS treat
    ``runesmith.md`` and ``RUNESMITH.md`` as one file. Used wherever a path could reach a model, a draft or a restore."""
    text = str(path or "").replace("\\", "/")
    return PurePosixPath(text).name.lower() == FILE_NAME.lower()


def is_log(path: Any) -> bool:
    """Whether this file is the log Runesmith wrote (its header marker is there), as opposed to a RUNESMITH.md the owner
    wrote himself, which Runesmith leaves alone and the instruction reader still reads."""
    try:
        with open(path, "rb") as stream:
            head = stream.read(4096).decode("utf-8-sig", "replace").replace("\r\n", "\n")
        return head.startswith("# " + FILE_NAME) and _LOG_HEADING in head
    except OSError:
        return False


def header() -> str:
    """Everything above the log: the title, three plain sentences, the mark and the version."""
    return (f"# {FILE_NAME}\n\n{INTRO}\n\n```text\n" + "\n".join(LOGO) + f"\n```\n\n**Runesmith {__version__}**\n"
            + _LOG_HEADING)


# ----------------------------------------------------------------------------------------------- cleaning --

_SECRETS = [re.compile(p) for p in (
    r"https?://\S+",                                                       # a link may carry a key in its address
    r"(?i)\b(?:authorization|api[_-]?key|access[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*(?:bearer\s+)?\S+",
    r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{8,}",
    r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{6,}",
    r"\bAIza[0-9A-Za-z_\-]{16,}",
    r"\b(?:gsk|nvapi|hf|ghp|gho|ghs|ghu|glpat|xox[abprs])[_\-][A-Za-z0-9_\-]{10,}",
    r"\bgithub_pat_[A-Za-z0-9_]{10,}",
    r"\b(?:AKIA|ASIA)[A-Z0-9]{12,}",
    r"\beyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}(?:\.[A-Za-z0-9_\-]*)?",    # a signed token
    r"\b[A-Fa-f0-9]{32,}\b",                                                # a long run of hex
)]
_OPAQUE = re.compile(r"[A-Za-z0-9_\-+=]{28,}")


def _opaque(match: re.Match) -> str:
    run = match.group(0)
    return "[removed]" if any(c.isdigit() for c in run) and any(c.isalpha() for c in run) else run


def scrub(ws: Any, text: Any) -> str:
    """One plain line: no line breaks or backticks, nothing that looks like a secret, no key the home keeps."""
    out = re.sub(r"\s+", " ", str(text if text is not None else "")).replace("`", "'").strip()
    out = "".join(c for c in out if c.isprintable())
    try:
        for name in ws.keys.names():                                     # the exact values of saved keys
            value = ws.keys.supplier(name)()
            if len(value) >= 6:
                out = out.replace(value, "[removed]")
    except Exception:
        pass
    for pattern in _SECRETS:
        out = pattern.sub("[removed]", out)
    out = _OPAQUE.sub(_opaque, out)
    out = re.sub(r"(?i)milliner\w*", "router", out)                      # an internal name, never in a user's folder
    return out if len(out) <= MAX_LINE else out[:MAX_LINE - 1].rstrip() + "…"


# --------------------------------------------------------------------------------------------- the writer --

def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%MZ", time.gmtime())


def _enabled(ws: Any) -> bool:
    settings = ws.settings()
    return bool(settings.get("runesmith_md", True)) and settings.get("autonomy") != "observe"


def _write(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(text.encode("utf-8"))                          # LF, UTF-8, whatever the platform
    atomic.replace(temporary, path)


def record(ws: Any, text: Any) -> None:
    """Add one line to the log (creating the file with its header on the first). Never raises."""
    try:
        if not _enabled(ws):
            return
        body = scrub(ws, text)
        if not body:
            return
        line = f"- {_stamp()}: {body}"
        path = Path(ws.root) / FILE_NAME
        with _LOCK:
            if path.is_symlink() or path.is_dir():
                return                                                   # never write through a link
            if not path.exists():
                _write(path, header() + line + "\n")
                return
            raw = path.read_bytes()
            text_lf = raw.decode("utf-8-sig").replace("\r\n", "\n")
            at = text_lf.find(_LOG_HEADING)
            if at < 0 or not text_lf.startswith("# " + FILE_NAME):
                return                                                   # not Runesmith's file: left alone
            head, rest = text_lf[:at + len(_LOG_HEADING)], text_lf[at + len(_LOG_HEADING):]
            lines = rest.split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            trimmed, kept = 0, []
            for existing in lines:
                found = _TRIMMED.match(existing)
                if found:
                    trimmed += int(found.group(1))
                else:
                    kept.append(existing)
            kept.append(line)
            entries = [i for i, row in enumerate(kept) if _ENTRY.match(row)]
            excess = max(0, len(entries) - MAX_ENTRIES)
            if excess:
                drop = set(entries[:excess])
                kept = [row for i, row in enumerate(kept) if i not in drop]
                trimmed += excess
            current = header()
            if not excess and head == current and b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf"):
                with path.open("ab") as stream:                          # the usual case: only a line is added
                    stream.write((("" if raw.endswith(b"\n") else "\n") + line + "\n").encode("utf-8"))
                return
            note = [f"- Older entries were trimmed: {trimmed} earlier events are no longer listed here."] if trimmed else []
            _write(path, current + "".join(row + "\n" for row in note + kept))
    except Exception:
        return                                                           # a log never breaks the work


def _safe(function):
    @functools.wraps(function)
    def run(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            return None
    return run


# ------------------------------------------------------------------------------------------ small helpers --

def model_name(ws: Any, by: Any) -> str | None:
    """The instrument's display name for a model id the work was answered by (its label, as Thinking power shows it),
    else the id as it came."""
    by = str(by or "").strip()
    if not by or by.startswith(("(", "owner", "Runesmith (no model")):
        return None
    try:
        from runesmith.app.providers import PRESET_BY_ID
        for name, spec in (ws.config().get("instruments") or {}).items():
            if by in (name, spec.get("model")) or by in (spec.get("fallback_models") or []):
                if spec.get("kind") == "milliner":
                    return by
                label = spec.get("label") or (PRESET_BY_ID.get(spec.get("preset") or "") or {}).get("label") or name
                return label if by in (name, label) else f"{label} ({by})"
    except Exception:
        pass
    return by


def _milestone(ws: Any, milestone_id: Any) -> str:
    for row in (ws.plan() or {}).get("milestones", []):
        if row.get("id") == milestone_id and str(row.get("title") or "").strip():
            title = str(row["title"]).strip()
            return f"the milestone \"{title if len(title) <= MAX_TITLE else title[:MAX_TITLE - 1] + '…'}\""
    return "a milestone"


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]                                   # not str.capitalize(): it lowercases the title


def _names(files: Any) -> str:
    names = [str(f) for f in (files or []) if f and not is_own(f)]
    shown = ", ".join(names[:MAX_FILES_NAMED])
    return shown + (f" and {len(names) - MAX_FILES_NAMED} more" if len(names) > MAX_FILES_NAMED else "")


def _by(ws: Any, by: Any) -> str:
    name = model_name(ws, by)
    return f" Code by {name}." if name else ""


def _titles(rows: list[str]) -> str:
    shown = [f"\"{t if len(t) <= MAX_TITLE else t[:MAX_TITLE - 1] + '…'}\"" for t in rows[:5]]
    return ", ".join(shown) + (f" and {len(rows) - 5} more" if len(rows) > 5 else "")


# ------------------------------------------------------------------------------------------------ events --
# One function for each thing that happens, called right beside the ledger entry of the same event.

@_safe
def milestone_added(ws: Any, title: str) -> None:
    record(ws, f"The milestone \"{title.strip()[:MAX_TITLE]}\" was added.")


@_safe
def milestone_status(ws: Any, milestone_id: str, status: str) -> None:
    if status == "done":
        record(ws, f"{_sentence(_milestone(ws, milestone_id))} was marked done.")
    elif status == "dropped":
        record(ws, f"{_sentence(_milestone(ws, milestone_id))} was dropped from the plan.")


@_safe
def plan_saved(ws: Any, previous: dict | None, body: dict) -> None:
    now = [str(m.get("title") or "") for m in body.get("milestones", [])]
    who = model_name(ws, body.get("drafted_by"))
    by = f" by {who}" if who else ""
    if not previous:
        record(ws, f"A plan was drafted{by} with {len(now)} milestone{'' if len(now) == 1 else 's'}: {_titles(now)}.")
        return
    before = [str(m.get("title") or "") for m in previous.get("milestones", [])]     # ids are positional: compare titles
    added = [t for t in now if t not in before]
    removed = [t for t in before if t not in now]
    if added or removed:
        parts = ([f"added {_titles(added)}"] if added else []) + ([f"removed {_titles(removed)}"] if removed else [])
        record(ws, f"The plan was redrafted{by}: {'; '.join(parts)}.")


@_safe
def draft_applied(ws: Any, draft: dict, files: list[str]) -> None:
    where = f" for {_milestone(ws, draft.get('milestone'))}" if draft.get("milestone") else ""
    record(ws, f"You approved a draft{where}; its files were written: {_names(files)}.{_by(ws, draft.get('drafted_by'))}")


@_safe
def build_done(ws: Any, milestone_id: str, draft: dict, files: list[str], passed: int, total: int,
               earlier: int = 0) -> None:
    """`earlier`: the finished milestones whose checks judged this build too (their checks are in `total`)."""
    counted = (f" (this milestone's and those of the {earlier} finished milestone{'' if earlier == 1 else 's'} before it)"
               if earlier else "")
    record(ws, f"Runesmith built {_milestone(ws, milestone_id)}: {passed} of {total} checks passed{counted}, its files "
               f"were applied ({_names(files)}) and the milestone is done.{_by(ws, draft.get('drafted_by'))}")


@_safe
def draft_undone(ws: Any, draft: dict, files: list[str]) -> None:
    where = f" for {_milestone(ws, draft.get('milestone'))}" if draft.get("milestone") else ""
    record(ws, f"You undid a draft{where}; its files were put back: {_names(files)}.")


@_safe
def draft_rejected(ws: Any, draft: dict) -> None:
    where = f" for {_milestone(ws, draft.get('milestone'))}" if draft.get("milestone") else ""
    record(ws, f"You turned down a draft{where}.{_by(ws, draft.get('drafted_by'))}")


@_safe
def fix_applied(ws: Any, files: list[str]) -> None:
    record(ws, f"You approved a repair Runesmith proposed; its files were written: {_names(files)}.")


@_safe
def fix_undone(ws: Any, files: list[str]) -> None:
    record(ws, f"You undid a repair; its files were put back: {_names(files)}.")


@_safe
def fix_rejected(ws: Any) -> None:
    record(ws, "You turned down a repair Runesmith proposed.")


@_safe
def checks_approved(ws: Any, milestone_id: str, count: int, by: str, proposed_by: Any) -> None:
    who = "you" if by == "owner" else "Runesmith's check autopilot"
    record(ws, f"Checks for {_milestone(ws, milestone_id)} were approved by {who}: {count} checks."
               f"{(' Proposed by ' + model_name(ws, proposed_by) + '.') if model_name(ws, proposed_by) else ''}")


@_safe
def checks_withdrawn(ws: Any, milestone_id: str) -> None:
    record(ws, f"You withdrew the approved checks for {_milestone(ws, milestone_id)}.")


@_safe
def checks_discarded(ws: Any, milestone_id: str) -> None:
    record(ws, f"You discarded the proposed checks for {_milestone(ws, milestone_id)}.")


@_safe
def split_adopted(ws: Any, milestone_id: str, steps: int, by: str) -> None:
    who = "you" if by == "owner" else "Runesmith"
    record(ws, f"{_sentence(_milestone(ws, milestone_id))} was split into {steps} smaller steps (adopted by {who}).")


@_safe
def split_rejected(ws: Any, milestone_id: str) -> None:
    record(ws, f"You turned down a proposed split of {_milestone(ws, milestone_id)}.")


@_safe
def restart_decision(ws: Any, decision: str, by: str, jobs: int) -> None:
    what = "keep the waiting work" if decision == "keep" else "set the waiting work aside"
    if by == "owner":
        record(ws, f"After a restart, you chose to {what} ({jobs} jobs).")
    else:
        record(ws, f"After a restart, Runesmith chose to {what} ({jobs} jobs), as your setting says.")


# What the owner asked for when he pressed a button that tries something again (the jobs the Studio's route queues).
RETRIES = {
    "escalate": "You asked for one more try, with another model, for the milestones whose tries were used up.",
    "resume_author": "You asked Runesmith to retrieve a model's saved answer after an interruption (no new model call).",
    "readmit": "You asked Runesmith to check a kept model answer again (no new model call).",
    "readmit_answer": "You asked Runesmith to check a kept model answer again (no new model call).",
    "resume_check": "You asked Runesmith to run a check that had timed out once more.",
}


@_safe
def retry_asked(ws: Any, kind: str = "escalate") -> None:
    if kind in RETRIES:
        record(ws, RETRIES[kind])
