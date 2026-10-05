"""Where the guide lives, for the few places the Studio points at it.

``GUIDE_URL`` is the address the README's "Read the guide" link gets at release (the placeholder there is ``GUIDE_URL``;
fill both). Until it is set, the Studio names the chapter in words and shows no link, rather than a link that goes nowhere.
The chapter's anchor is its heading's slug ("# Chapter 4: Thinking power: where to get a model for free, and how to
connect it"); check it against how the guide is published.
"""
from __future__ import annotations

GUIDE_URL = ""
FREE_INFERENCE_WORDS = "Chapter 4 of the guide, \u201cThinking power: where to get a model for free, and how to connect it\u201d,"
FREE_INFERENCE_CHAPTER = "#chapter-4-thinking-power-where-to-get-a-model-for-free-and-how-to-connect-it"


def free_inference_url() -> str:
    """The guide's chapter on free thinking power (where to get a second free provider), or "" before the guide has an address."""
    return GUIDE_URL.rstrip("/") + FREE_INFERENCE_CHAPTER if GUIDE_URL.startswith(("http://", "https://")) else ""
