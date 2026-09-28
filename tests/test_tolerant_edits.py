"""Exact edits that differ only by a uniform indentation shift (journey J2: a free model wrote 8 spaces where the
file has 4, and the whole answer was refused). Only that is forgiven; everything else is refused as before."""
import pytest

from runesmith.app.planner import _apply_one_edit, _reindented

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
