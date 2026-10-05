"""Smaller findings of the newcomer path (2026-10-05): what the Overview says after files exist, and how it says it."""
import subprocess
from pathlib import Path
from types import SimpleNamespace

from runesmith.app.workspace import Workspace

VIEWS = Path(__file__).resolve().parent.parent / 'runesmith/app/static/js/views'


def test_the_overview_stops_calling_the_folder_empty_once_files_were_written(tmp_path):
    ws = Workspace(tmp_path)
    ws.map_environment() if hasattr(ws, 'map_environment') else None       # the map made at the start says "empty"
    assert ws.state()['workspace']['empty'] is True
    (tmp_path / 'readinglog.py').write_text('print(1)\n', encoding='utf-8')          # the first files were written
    assert ws.state()['workspace']['empty'] is False                          # without mapping again
    only_own = tmp_path / 'sub'
    only_own.mkdir()
    own = Workspace(only_own)
    (only_own / 'RUNESMITH.md').write_text('log\n', encoding='utf-8')               # Runesmith's own log is not the owner's file
    assert own.state()['workspace']['empty'] is True


def test_a_long_error_is_cut_at_a_word_and_a_full_stop_so_the_next_sentence_does_not_run_on(tmp_path):
    source = (VIEWS / 'home.js').read_text(encoding='utf-8')
    start = source.index('function sentenceEnd(')
    function = source[start:source.index('\n}\n', start) + 3]
    script = tmp_path / 'cut.mjs'
    script.write_text(function + """
const long = 'the model is busy: ' + 'Spikes in demand are usually temporary. '.repeat(8);
const cut = sentenceEnd(long, 180);
console.log(JSON.stringify({ cut, long, short: sentenceEnd('Nothing came back', 180), ended: sentenceEnd('Done.', 180) }));
""", encoding='utf-8')
    import json
    out = json.loads(subprocess.run(['node', str(script)], capture_output=True, text=True, encoding='utf-8', check=True).stdout)
    assert len(out['cut']) <= 181 and out['cut'].endswith('…')
    long = out['long']
    words = set(long.replace('.', ' ').replace(':', ' ').split())
    assert out['cut'].rstrip('…').rstrip('.').split()[-1] in words                  # a whole word, never "Spikes i"
    assert out['short'] == 'Nothing came back.' and out['ended'] == 'Done.'


def test_with_one_model_the_autopilot_says_it_needs_a_second_and_offers_one_click_approval():
    source = (VIEWS / 'goals.js').read_text(encoding='utf-8')
    assert "/no second model/i.test(p.autopilot.reason" in source
    assert 'needs a second model to cross-check' in source and 'Approve them myself' in source
    assert "'data-act': 'use-checks'" in source and '[data-act="use-checks"]' in source
    # The reason it reacts to is the one the autopilot itself gives with a single model.
    from runesmith.app import acceptance_autopilot
    assert 'no second model' in Path(acceptance_autopilot.__file__).read_text(encoding='utf-8')
