"""Journey J11-B17: the owner acceptance run grew with the plan and stopped every build.

Every done milestone's checks judge each build. The footer of an approved file left its loop variable naming the test
class, so unittest loaded the class twice and every check ran twice (188 runs of 94 checks); and a fixed 120 s limit
was passed once 41 milestones had checks.
"""
import json

from runesmith.app import acceptance_proposals, building

CHECKS = '''import unittest


class OwnerExamples(unittest.TestCase):
    def test_one(self):
        self.assertTrue(True)

    def test_two(self):
        self.assertTrue(True)
'''

# The footer approved files carry until this fix; files already approved keep it (their digests are bound).
OLD_FOOTER = '''

import unittest as _acceptance_unittest
for _case in [v for v in list(globals().values()) if isinstance(v, type) and v.__module__ == __name__
              and issubclass(v, _acceptance_unittest.TestCase)]:
    _case.PUBLIC_CRITERIA = {_name: ["check." + _name] for _name in dir(_case) if _name.startswith("test")}
'''


def _run(tmp_path, *texts):
    stage = tmp_path / 'stage'
    stage.mkdir()
    paths = []
    for index, text in enumerate(texts):
        path = tmp_path / f'acceptance-m{index}.py'
        path.write_text(text, encoding='utf-8', newline='\n')
        paths.append(str(path))
    return building._run_checks(stage, json.dumps(paths), tmp_path / 'log.txt', timeout_s=120)


def test_a_file_with_the_old_footer_runs_each_check_once(tmp_path):
    result = _run(tmp_path, CHECKS + OLD_FOOTER)
    assert result['ok'] is True
    assert result['ran'] == 2
    assert result['progress']['planned'] == 2


def test_a_file_with_the_new_footer_runs_each_check_once_and_keeps_its_criteria(tmp_path):
    failing = CHECKS.replace('self.assertTrue(True)\n\n    def test_two', 'self.assertTrue(False)\n\n    def test_two')
    result = _run(tmp_path, failing + acceptance_proposals.FOOTER)
    assert result['ran'] == 2 and result['failures'] == 1
    # A failing check still reaches the builder by its sentence's id, never by its assertion.
    assert result['failure_details'][0]['criteria'] == ['check.test_one']


def test_the_new_footer_leaves_no_second_name_for_the_class():
    namespace = {'__name__': 'owner_acceptance_0'}
    exec(compile(CHECKS + acceptance_proposals.FOOTER, 'm.py', 'exec'), namespace)
    import unittest
    names = [name for name, value in namespace.items() if isinstance(value, type) and issubclass(value, unittest.TestCase)]
    assert names == ['OwnerExamples']
    assert namespace['OwnerExamples'].PUBLIC_CRITERIA == {'test_one': ['check.test_one'], 'test_two': ['check.test_two']}


def test_several_files_and_classes_each_run_once(tmp_path):
    second = CHECKS.replace('OwnerExamples', 'MoreExamples') + '\n\nAlias = MoreExamples\n'
    result = _run(tmp_path, CHECKS + OLD_FOOTER, second + acceptance_proposals.FOOTER)
    assert result['ran'] == 4


def test_the_owner_limit_grows_with_the_number_of_checks():
    def bundle(tests):
        return {'m1.py': b'class A:\n' + b''.join(b'    def test_%d(self):\n        pass\n' % i for i in range(tests))}
    assert building.owner_check_limit({}) == building.CHECK_TIMEOUT_S
    assert building.owner_check_limit(bundle(10)) == building.CHECK_TIMEOUT_S
    assert building.owner_check_limit(bundle(94)) == 60 + 2 * 94          # J11 on 2026-10-01: 248 s, not 120 s
    assert building.owner_check_limit(bundle(1000)) == building.OWNER_LIMIT_S
    # Split across files, and a name that merely starts with "test" outside a class body is not counted.
    split = {'a.py': bundle(50)['m1.py'], 'b.py': bundle(44)['m1.py'] + b'def test_helper():\n    pass\n'}
    assert building.owner_check_limit(split) == 60 + 2 * 94


def test_a_module_with_its_own_load_tests_and_the_old_footer_runs_each_check_once(tmp_path):
    # Review of J11-B17: a module with load_tests took the unchanged path, which loads classes by every name, the old
    # footer's _case included, so its checks still ran twice and the time limit was doubled with them.
    returning = CHECKS + '\n\ndef load_tests(loader, tests, pattern):\n    return tests\n' + OLD_FOOTER
    result = _run(tmp_path, returning)
    assert result['ok'] is True and result['ran'] == 2 and result['progress']['planned'] == 2
    own = (CHECKS + '\n\ndef load_tests(loader, tests, pattern):\n    suite = unittest.TestSuite()\n'
           '    suite.addTests(loader.loadTestsFromTestCase(OwnerExamples))\n    return suite\n' + OLD_FOOTER)
    again = tmp_path / 'again'
    again.mkdir()
    assert _run(again, own)['ran'] == 2
    raising = CHECKS + '\n\ndef load_tests(loader, tests, pattern):\n    raise RuntimeError("no suite")\n' + OLD_FOOTER
    broken = tmp_path / 'broken'
    broken.mkdir()
    result = _run(broken, raising)
    assert result['ran'] == 1 and result['errors'] == 1                       # still reported, as unittest does


def test_the_limit_counts_checks_as_the_runner_finds_them():
    # Review of J11-B17: a frozen project suite is embedded in one line with escaped newlines, and async tests were not
    # counted either, so such a bundle got the old fixed 120 s although every check of it ran.
    body = ''.join(f'    def test_{n}(self):\n        pass\n\n' for n in range(200))
    plain = ('import unittest\n\n\nclass A(unittest.TestCase):\n' + body).encode()
    assert building.owner_check_limit({'a.py': plain}) == 460
    frozen = ('FROZEN = ' + repr({'tests/test_a.py': plain.decode()})).encode()
    assert b'\n' not in frozen and building.owner_check_limit({'frozen.py': frozen}) == 460
    asyncs = ('import unittest\n\n\nclass A(unittest.IsolatedAsyncioTestCase):\n' + body.replace('def', 'async def')).encode()
    assert building.owner_check_limit({'a.py': asyncs}) == 460
    assert building.owner_check_limit({}) == building.CHECK_TIMEOUT_S


BIG = 'import unittest\nfrom app import answer\n\n\nclass Acceptance(unittest.TestCase):\n' + ''.join(
    f'    def test_c{i}(self):\n        self.assertEqual(answer(), 42)\n' for i in range(200))


def test_the_one_time_extension_gives_the_owner_phase_what_an_ordinary_build_gets(tmp_path, monkeypatch):
    # Review of J11-B17: the extension gave the owner phase 240 s, less than the 460 s an ordinary build gives a
    # 200-check bundle; it is used once, so a bundle the ordinary limit lets finish could time out inside it. Journey
    # J11-G44: twice the ordinary limit, at most 600 s (920 s for this bundle, so 600).
    from runesmith.app.verification_resume import resume_status, resume_verification
    from test_build_steps import setup, enable
    ws = setup(tmp_path, acceptance=True)
    enable(ws)
    (ws.home / 'acceptance' / 'm1.py').write_text(BIG, encoding='utf-8', newline='\n')
    seen = []

    def timeout(stage, kind, logs, **kwargs):
        seen.append((kind if kind == 'project' else 'owner', kwargs.get('timeout_s')))
        return {'status': 'timeout', 'ok': False, 'elapsed_s': 120, 'limit_s': 120, 'output': 'unfinished'}

    def passed(stage, kind, logs, **kwargs):
        seen.append((kind if kind == 'project' else 'owner', kwargs.get('timeout_s')))
        return {'status': 'passed', 'ok': True, 'ran': 1, 'elapsed_s': 1, 'limit_s': kwargs.get('timeout_s')}
    monkeypatch.setattr(building, '_run_checks', timeout)
    first = building.build_step(ws, ws.router())
    assert first['verification']['status'] == 'inconclusive'
    status = resume_status(ws, ws._draft(first['draft']))
    assert status['timeout_s'] == 240 and status['owner_timeout_s'] == 600          # said before it is granted (the dialog)
    seen.clear()
    monkeypatch.setattr(building, '_run_checks', passed)
    resume_verification(ws, first['draft'], 'One extension')
    assert seen == [('project', 240), ('owner', 600)]
