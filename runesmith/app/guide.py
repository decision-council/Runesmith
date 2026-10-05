"""Where the guide lives, for the few places the Studio points at it.

``GUIDE_URL`` is where the guide is published, the same address as the README's "Read the guide" link. Without an
address the Studio names the chapter in words and shows no link, rather than a link that goes nowhere. The chapter's
anchor is the id the published guide gives the chapter ("chapter-4" on aithinklab.com/guide/, as of the 1.0 release).
"""
from __future__ import annotations

GUIDE_URL = "https://aithinklab.com/guide/"
FREE_INFERENCE_WORDS = "Chapter 4 of the guide, \u201cThinking power: where to get a model for free, and how to connect it\u201d,"
FREE_INFERENCE_CHAPTER = "#chapter-4"


def free_inference_url() -> str:
    """The guide's chapter on free thinking power (where to get a second free provider), or "" before the guide has an address."""
    return GUIDE_URL + FREE_INFERENCE_CHAPTER if GUIDE_URL.startswith(("http://", "https://")) else ""
