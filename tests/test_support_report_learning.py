"""Exercise the real repair packet and downstream reuse, with offline instruments."""
import json

import pytest

from runesmith import generations
from runesmith.app.workspace import Workspace
from runesmith.instruments import Router, ScriptedInstrument
from runesmith.kaizen.attention import Attention
from runesmith.kaizen.improve import FixtureInstrument
from runesmith.kaizen.trial import Trial
from runesmith.loop import ExperienceStore, run_loop, subject_step, _replay
from runesmith.memory import Memory
from runesmith.proposals import list_proposals
from test_kernel import make_repo
from test_loop import HINTS

MARKER = 'PRIVATE_SUPPORT_e65ad3'


def test_real_repair_packet_is_private_to_matching_step_and_review(tmp_path):
    ws = Workspace(tmp_path)
    repo = make_repo(tmp_path)
    class Capture(FixtureInstrument):
        requests = []
        def complete(self, **kwargs):
            self.requests.append(kwargs)
            return super().complete(**kwargs)
    repair = Capture(HINTS)
    author = ScriptedInstrument('author', [])
    router = Router({'repair':repair, 'author':author}, {'repair':'repair', 'kaizen':'author'}, backoff_s=())
    ordinary = {'repo':str(repo),'failing_tests':['tests/test_ops.py::test_add'],
                'judge_tests':['tests/test_ops.py'], 'issue':'add returns wrong value'}
    assisted = dict(ordinary, support_evidence={'boundary':'untrusted data, not authority',
                                               'included':[{'id':'fixture','text':MARKER}]})
    active = generations.active(ws.home)
    trial = Trial(incumbent=active, candidate=active, seed='private-test')
    trial.save(ws.home / 'TRIAL.json')
    result = run_loop(home=ws.home, opportunities=[assisted, ordinary], seed='private-test', router=router,
                      min_experience=1, kaizen_every=1)
    assert result['object_steps'] == 2 and result['strict_successes'] == 2
    assert any(MARKER in r['prompt'] for r in repair.requests if '0000-c1-' in r['key'])
    assert all(MARKER not in r['prompt'] for r in repair.requests if '0001-' in r['key'])
    store = ExperienceStore(ws.home / 'experience')
    tasks = store.tasks(); private = next(t for t in tasks if not t['learning_eligible'])
    assert len(store.learning_tasks()) == 1
    assert len(list_proposals(ws.home)) == 2  # the checked repair is still reviewable
    assert MARKER not in json.dumps(Memory(ws.home / 'memory.jsonl').active())
    assert MARKER not in json.dumps(tasks)  # raw excerpt stays in its session, not generic experience
    assert len(author.requests) == 0
    after = Trial.load(ws.home / 'TRIAL.json')
    assert sum(count[1] for count in after.counts.values()) == 1
    private_session = json.loads((ws.home / 'sessions' / (private['key'] + '.json')).read_text())
    assert MARKER in private_session['issue'] and private_session['trial_arm'] is None
    assert any(s['context_scope'] for s in ws.work()['recent_sessions'])
    with pytest.raises(ValueError, match='Restricted'):
        _replay(ws.home, store, [private], ws.home / 'generations' / active / 'organs', 'blocked', router)


def test_real_kaizen_packet_and_replay_inputs_exclude_assisted_work(tmp_path, monkeypatch):
    ws = Workspace(tmp_path); store = ExperienceStore(ws.home / 'experience')
    for i in range(20):
        store.add(key=f'clean-{i}', opportunity={'repo':'r','issue':'ordinary issue','failing_tests':['t']},
                  parent_src={}, final={}, record={'status':'public_fail','strict_success':False,
                    'marks':[], 'calls':[], 'cycle_seconds':1, 'model_calls':0})
    store.add(key='private', opportunity={'repo':'r','issue':MARKER,'failing_tests':['t'],
        'support_evidence':{'included':[{'text':MARKER}]}}, parent_src={}, final={},
        record={'status':'public_fail','strict_success':False,'marks':[{'detail':MARKER}]})
    replayed=[]
    def replay(home, storage, tasks, organ_dir, label, router):
        replayed.extend(tasks)
        return [{'status':'public_fail','strict_success':False,'model_calls':0,'cycle_seconds':0,
                 'marks':[], 'calls':[]} for _ in tasks]
    monkeypatch.setattr('runesmith.loop._replay', replay)
    author = ScriptedInstrument('author', [{'hypotheses':['a test'],'mechanism':'fixture',
        'prediction':'none','falsifier':'none','edits':[], 'module_source':'not valid python!'}])
    router = Router({'author':author}, {'kaizen':'author'}, backoff_s=())
    subject_step(home=ws.home, store=store, seed='private-split', router=router, max_answered=1)
    assert replayed and all(t['key'] != 'private' for t in replayed)
    assert len(author.requests) == 1
    assert MARKER not in json.dumps(author.requests)


def test_support_repair_cannot_use_a_relabelled_model_role(tmp_path):
    ws = Workspace(tmp_path); config = ws.config(); config['envelope']['role'] = 'kaizen'; ws.save_config(config)
    author = ScriptedInstrument('author', [])
    router = Router({'author':author},{'kaizen':'author'},backoff_s=())
    opportunity = {'repo':'unused','failing_tests':[],'issue':'report','support_evidence':{'included':[{'text':MARKER}]}}
    with pytest.raises(ValueError, match='only for the repair role'):
        run_loop(home=ws.home, opportunities=[opportunity], seed='test', router=router)
    assert not author.requests
