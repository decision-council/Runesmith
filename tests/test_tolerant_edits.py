"""Exact edits that differ only by a uniform indentation shift (journey J2: a free model wrote 8 spaces where the
file has 4, and the whole answer was refused), and the same edit given once for each place its text occurs (J2-G3).
Only these are forgiven; everything else is refused as before."""
import pytest

from runesmith.app.planner import PlannerUnavailable, _apply_one_edit, _reindented, admit_answer_files, source_context
from runesmith.app.workspace import Workspace

SOURCE = ('def main(argv=None):\n'
          '    args = parse(argv)\n'
          '    if args.command == "months":\n'
          '        try:\n'
          '            books = load_books(path)\n'
          '        except ValueError as e:\n'
          '            print(e, file=sys.stderr)\n'
          '            return 2\n'
          '    return 2\n')


def test_the_journey_edit_is_applied_at_the_file_s_own_indentation():
    edit = {"old_text": '        if args.command == "months":\n            try:\n                books = load_books(path)',
            "new_text": '        if args.command == "search":\n            return search(args)\n'
                        '        if args.command == "months":\n            try:\n                books = load_books(path)'}
    result = _apply_one_edit(SOURCE, edit, "readinglog/cli.py")
    assert '    if args.command == "search":\n        return search(args)\n    if args.command == "months":\n        try:' in result
    assert result.endswith('            return 2\n    return 2\n')          # the rest of the file is untouched
    compile(result, "cli.py", "exec")


def test_a_shift_the_other_way_works_too():
    edit = {"old_text": 'if args.command == "months":\n    try:', "new_text": 'if args.command in ("months", "m"):\n    try:'}
    assert '    if args.command in ("months", "m"):\n        try:' in _apply_one_edit(SOURCE, edit, "cli.py")


@pytest.mark.parametrize("old,new", [
    ("  return 2", "  return 3"),                                            # two places once shifted: ambiguous
    ('        if args.command == "months":\n          try:', 'x\ny'),        # lines shifted by different amounts
    ('\tif args.command == "months":', "\tpass"),                             # tabs are never guessed
    ('    if args.command == "month":', "    pass"),                          # different text, not indentation
])
def test_anything_but_one_uniform_shift_is_still_refused(old, new):
    assert _reindented(SOURCE, old, new) is None
    with pytest.raises(ValueError, match="exactly once"):
        _apply_one_edit(SOURCE, {"old_text": old, "new_text": new}, "cli.py")


def test_an_exact_edit_is_applied_exactly_as_before():
    edit = {"old_text": 'def main(argv=None):', "new_text": 'def main(argv=None):  # entry point'}
    assert _apply_one_edit(SOURCE, edit, "cli.py").startswith('def main(argv=None):  # entry point\n    args')


def admitted(tmp_path, text, edits):
    ws = Workspace(tmp_path)
    (tmp_path / "cli.py").write_bytes(text.encode("utf-8"))
    return admit_answer_files(ws, source_context(ws), [{"path": "cli.py", "purpose": "storage", "edits": edits}])


def test_the_same_edit_given_once_for_each_place_changes_every_place(tmp_path):
    # Journey J2-G3: for m8 a free model gave this edit four times, once per place, with other edits between them.
    text = SOURCE + 'def export(path):\n    books = load_books(path)\n'
    same = {"old_text": "books = load_books(path)", "new_text": "books = load_books(storage)"}
    other = {"old_text": "def export(path):", "new_text": "def export(storage):"}
    content = admitted(tmp_path, text, [same, other, dict(same)])[0]["content"]
    assert content.count("load_books(storage)") == 2 and "load_books(path)" not in content
    assert "def export(storage):" in content


def test_the_same_edit_given_a_different_number_of_times_is_still_refused(tmp_path):
    text = SOURCE + 'def export(path):\n    books = load_books(path)\n    books = load_books(path)\n'
    same = {"old_text": "books = load_books(path)", "new_text": "books = load_books(storage)"}
    with pytest.raises(PlannerUnavailable, match="given 2 times, but its old_text occurs 3 times"):
        admitted(tmp_path, text, [same, dict(same)])
    with pytest.raises(PlannerUnavailable, match="exactly once"):
        admitted(tmp_path, text, [same])


def test_an_edit_labelled_with_its_purpose_is_applied(tmp_path):
    # Journey J11-G13: every edit of the SVG milestone's answer carried a "purpose"; the answer was refused as an
    # invalid edit schema.
    labelled = {"old_text": "def main(argv=None):", "new_text": "def main(argv=None):  # entry point", "purpose": "label it"}
    assert _apply_one_edit(SOURCE, labelled, "cli.py").startswith('def main(argv=None):  # entry point')
