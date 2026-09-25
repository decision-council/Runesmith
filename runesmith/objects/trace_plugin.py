"""Pytest plugin: record which source lines execute during a run.

Enabled with ``-p runesmith_trace_plugin``. Only files under
``RUNESMITH_TRACE_ROOT`` are recorded; the result is written as JSON to
``RUNESMITH_TRACE_OUT``. Test source is never recorded or returned.
"""

from __future__ import annotations

import json
import os
import sys
import threading

_ROOT = os.path.normcase(os.path.abspath(os.environ.get("RUNESMITH_TRACE_ROOT", "") or "."))
_OUT = os.environ.get("RUNESMITH_TRACE_OUT")
_HITS: dict[str, set[int]] = {}


def _local(frame, event, arg):
    if event == "line":
        _HITS.setdefault(frame.f_code.co_filename, set()).add(frame.f_lineno)
    return _local


def _global(frame, event, arg):
    filename = frame.f_code.co_filename
    if not filename:
        return None
    norm = os.path.normcase(os.path.abspath(filename))
    if norm.startswith(_ROOT + os.sep):
        _HITS.setdefault(filename, set()).add(frame.f_lineno)
        return _local
    return None


def pytest_configure(config):  # noqa: D401 - pytest hook
    if _OUT:
        sys.settrace(_global)
        threading.settrace(_global)


def pytest_unconfigure(config):
    if not _OUT:
        return
    sys.settrace(None)
    threading.settrace(None)
    result = {}
    for filename, lines in _HITS.items():
        norm = os.path.normcase(os.path.abspath(filename))
        rel = os.path.relpath(norm, _ROOT).replace(os.sep, "/")
        result[rel] = sorted(line for line in lines if line > 0)
    with open(_OUT, "w", encoding="utf-8") as stream:
        json.dump(result, stream)
