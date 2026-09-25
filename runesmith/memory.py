"""Episodic and negative memory with exact, auditable lexical retrieval.

Memories are appended, never rewritten: retiring a memory appends a retirement
record, so history survives while the memory stops being eligible. Retrieval is
deterministic BM25 over tokens, after hard filters on kind and status. Each
retrieval returns the ids it exposed, so the effect of a memory on later work
can be measured instead of assumed.

Kinds: ``episode`` (what happened on an opportunity), ``negative`` (an approach
that failed and why — a guard against repeating it), and ``note`` (anything an
organ or operator wants retained).
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from runesmith.canon import digest

TOKEN = re.compile(r"[a-z0-9_]+")
KINDS = ("episode", "negative", "note")


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if len(t) > 1]


class Memory:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def add(self, kind: str, text: str, *, tags: Iterable[str] = (), source: dict | None = None) -> str:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        item = {"kind": kind, "text": text[:20_000], "tags": sorted(set(tags)), "source": source or {},
                "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        item["id"] = "mem-" + digest(item)[7:19]
        with self._lock, open(self.path, "a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        return item["id"]

    def retire(self, memory_id: str, reason: str) -> None:
        with self._lock, open(self.path, "a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps({"retire": memory_id, "reason": reason,
                                     "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")

    def active(self, kinds: Iterable[str] | None = None) -> list[dict[str, Any]]:
        rows = self._rows()
        retired = {row["retire"] for row in rows if "retire" in row}
        wanted = set(kinds) if kinds else set(KINDS)
        return [row for row in rows if "id" in row and row["id"] not in retired and row["kind"] in wanted]

    def recall(self, query: str, k: int = 5, *, kinds: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """Top-k active memories by BM25 (k1=1.2, b=0.75); ties break on id for determinism."""
        items = self.active(kinds)
        if not items:
            return []
        docs = [tokens(item["text"] + " " + " ".join(item["tags"])) for item in items]
        avg = sum(len(d) for d in docs) / len(docs) or 1.0
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        scored = []
        for item, doc in zip(items, docs, strict=True):
            tf = Counter(doc)
            score = 0.0
            for term in set(tokens(query)):
                if term not in tf:
                    continue
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * tf[term] * 2.2 / (tf[term] + 1.2 * (0.25 + 0.75 * len(doc) / avg))
            if score > 0:
                scored.append((-score, item["id"], item))
        scored.sort(key=lambda row: (row[0], row[1]))
        return [{"id": item["id"], "kind": item["kind"], "text": item["text"], "tags": item["tags"],
                 "score": round(-neg, 4)} for neg, _, item in scored[:max(0, min(k, 20))]]
