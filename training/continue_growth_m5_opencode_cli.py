"""One genuine OpenCode CLI author session, no tools or direct project writes."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.acceptance_contracts import expectation_digest
from runesmith.app.author_recovery import pending_authors
from runesmith.app.planner import draft_files, source_context
from runesmith.app.server import InstanceLock, _existing
from runesmith.app.workspace import Workspace, _now, _read_json, _write_json
from runesmith.config import build_instrument
from runesmith.instruments import Instrument, CallOutcome, Router, parse_json_answer

TRAINING = Path(__file__).resolve().parent
MODEL = 'longcat-2.5-preview-free'
CLI = TRAINING / '.tools/opencode/node_modules/opencode-windows-x64/bin/opencode.exe'
WORK = TRAINING / '.tmp/opencode-longcat-cli'


def cli_environment(token):
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE',
        'NUMBER_OF_PROCESSORS', 'PROCESSOR_ARCHITECTURE', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY'}}
    for kind in ('CACHE', 'DATA', 'CONFIG', 'STATE'):
        env['XDG_' + kind + '_HOME'] = str(TRAINING / '.tmp/opencode-xdg' / kind.lower())
    env.update(TEMP=str(TRAINING / '.tmp'), TMP=str(TRAINING / '.tmp'),
        OPENCODE_CONFIG=str(WORK / 'opencode.json'), OPENCODE_CONFIG_DIR=str(WORK),
        OPENCODE_API_KEY=token, OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX='12000')
    for name in ('CLAUDE_CODE', 'AUTOUPDATE', 'DEFAULT_PLUGINS', 'LSP_DOWNLOAD', 'AUTOCOMPACT'):
        env['OPENCODE_DISABLE_' + name] = 'true'
    return env


class CLIInstrument(Instrument):
    kind = 'opencode-cli-trial'

    def __init__(self, token, receipt, path):
        super().__init__('opencode-cli-longcat', MODEL)
        self.token, self.receipt, self.path = token, receipt, path

    def complete(self, *, prompt, system, schema, max_tokens, key, reasoning_effort=None):
        if self.receipt['cli_invocations'] or max_tokens > 12000:
            raise RuntimeError('CLI trial invocation/token bound exceeded')
        packet = {'system': system, 'output_schema': schema, 'author_packet': prompt}
        if self.token in json.dumps(packet):raise RuntimeError('Credential appeared in packet')
        packet_path = WORK / 'AUTHOR_PACKET.json'
        _write_json(packet_path, packet)
        self.receipt.update(state='cli_started', cli_invocations=1, request_key=key,
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(), prompt_bytes=len(prompt.encode()),
            cli_sha256=hashlib.sha256(CLI.read_bytes()).hexdigest(),
            config_sha256=hashlib.sha256((WORK / 'opencode.json').read_bytes()).hexdigest())
        _write_json(self.path, self.receipt)
        args = [str(CLI), '--pure', 'run', '--format', 'json', '--model', 'opencode/' + MODEL,
            '--agent', 'runesmith-author', '--title', 'Runesmith GrowthHat m5 LongCat author trial',
            '--file', str(packet_path), '--dir', str(WORK),
            'Use only the attached Runesmith author packet. Return the complete JSON candidate matching its schema. No tools.']
        started = time.monotonic()
        proc = subprocess.Popen(args, cwd=WORK, env=cli_environment(self.token),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.receipt['pid'] = proc.pid
        _write_json(self.path, self.receipt)
        timed_out = False
        try:
            out, err = proc.communicate(timeout=420)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            out, err = proc.communicate()
        stdout = out.decode('utf-8', errors='replace').replace(self.token, '[redacted]')
        stderr = err.decode('utf-8', errors='replace').replace(self.token, '[redacted]')
        journal = self.path.with_suffix('')
        _write_json(journal / 'CLI_OUTPUT.json', {'stdout': stdout, 'stderr': stderr,
            'exit_code': proc.returncode, 'timed_out': timed_out})
        rows, text_parts, finishes, errors = [], [], [], []
        for line in stdout.splitlines():
            try: row = json.loads(line)
            except ValueError: continue
            if not isinstance(row, dict):continue
            rows.append(row)
            if row.get('type') == 'text':text_parts.append((row.get('part') or {}).get('text', ''))
            if row.get('type') == 'step_finish':finishes.append(row.get('part') or {})
            if row.get('type') == 'error':errors.append(row.get('error') or row)
        latency = round(time.monotonic() - started, 3)
        session_ids = sorted({r['sessionID'] for r in rows if isinstance(r.get('sessionID'), str)})
        self.receipt.update(exit_code=proc.returncode, timed_out=timed_out, latency_s=latency,
            session_ids=session_ids, observed_completed_steps=len(finishes),
            step_receipts=finishes, cli_errors=errors, text_chars=sum(map(len, text_parts)))
        _write_json(self.path, self.receipt)
        api_receipt = {'provider': 'opencode', 'model': MODEL, 'route': 'genuine_cli',
            'cli_session_ids': session_ids, 'gateway_job_id': None,
            'observed_completed_steps': len(finishes), 'usage_coverage': 'CLI step receipts only; no provider invoice'}
        if len(finishes) == 1:
            usage = finishes[0].get('tokens') or {}
            api_receipt.update(tokens_in=usage.get('input'), tokens_out=usage.get('output'),
                cli_reported_cost=finishes[0].get('cost'))
        text = ''.join(text_parts)
        if timed_out or proc.returncode or errors or len(finishes) != 1:
            return CallOutcome(False, text=text, error_kind='output',
                error='CLI run did not produce exactly one clean completed step; inspect retained journal.',
                latency_s=latency, receipt=api_receipt)
        try: data = parse_json_answer(text, tolerant=True)
        except ValueError as error:
            return CallOutcome(False, text=text, error_kind='output', error=str(error)[:300],
                latency_s=latency, receipt=api_receipt)
        return CallOutcome(True, data=data, text=text, latency_s=latency, receipt=api_receipt)


def main():
    root = TRAINING / 'GrowthHat'
    home = root / '.runesmith'
    if _existing(home):raise RuntimeError('Resident Studio found; use its queue')
    lock = InstanceLock(home)
    if not lock.acquire():raise RuntimeError('Another writer owns this home')
    try:
        ws = Workspace(root, home)
        path = home / 'trainer-trials/opencode-cli-longcat-m5-20260926.json'
        if path.exists():
            print(json.dumps({'already_used': True, 'state': _read_json(path, {}).get('state', 'unknown')}))
            return
        if not _now().startswith('2026-09-26'):raise RuntimeError('Dated free-price review expired')
        if pending_authors(ws):raise RuntimeError('Reconcile pending author first')
        prior = _read_json(home / 'trainer-trials/opencode-direct-longcat-m5-20260926.json', {})
        if prior.get('http_status') != 403 or prior.get('api_calls') != 1:
            raise RuntimeError('Direct trial is not the reviewed terminal product restriction')
        if (home / 'trainer-trials/opencode-longcat-m5-20260926.json').exists():
            raise RuntimeError('Gateway trial exists; reconcile first')
        if any(d.get('milestone') == 'm5' and d.get('state') in ('waiting', 'applied') for d in ws.drafts()):
            raise RuntimeError('m5 already has a candidate')
        before = source_context(ws)['snapshot_digest']
        public = expectation_digest(ws, 'm5')
        if before != prior['source_digest'] or public != prior['public_acceptance_digest']:
            raise RuntimeError('Source or public criteria changed')
        direct = build_instrument('direct-opencode-longcat', ws.config()['instruments']['direct-opencode-longcat'], home)
        token = direct._api_key()
        if not token:raise RuntimeError('Existing credential unavailable')
        receipt = {'state': 'prepared', 'utc': _now(), 'route': 'genuine_cli', 'cli_version': '1.18.32',
            'model': 'opencode/' + MODEL, 'source_digest': before, 'public_acceptance_digest': public,
            'cli_invocations': 0, 'max_agent_steps': 1, 'max_output_tokens': 12000,
            'wall_limit_s': 420, 'provider_timeout_s': 240, 'automatic_outer_retry': False,
            'tools_allowed': [], 'paid_fallback': False, 'title_summary_compaction_disabled': True,
            'gateway_job_id': None, 'estimated_cost_usd': 0.0, 'billing_verified': False,
            'estimate_basis': 'Official Zen free listing; CLI step usage is retained separately.',
            'transport_attempt_coverage': 'Only CLI-visible steps/errors; internal network retries may not be fully observable.',
            'trainer_assistance': 'External trainer supplied isolated official-CLI transport and existing public/hidden acceptance. No project edits by trainer.'}
        _write_json(path, receipt)
        events = []
        def record(event):events.append(event); ws.record_call(event)
        router = Router({'cli': CLIInstrument(token, receipt, path)}, {'plan': ['cli']}, backoff_s=(), on_call=record)
        print(json.dumps({'state': 'starting_genuine_cli_author', 'model': receipt['model'],
            'tools_allowed': [], 'wall_limit_s': 420, 'gateway_job_id': None}), flush=True)
        try:
            draft = draft_files(ws, router, 'm5')
            receipt.update(state='admitted', draft=draft['id'], authored_by=draft.get('drafted_by'),
                paths=[f['path'] for f in draft['files']])
        except Exception as error:
            receipt.update(state='refused_or_unresolved',
                error=(type(error).__name__ + ': ' + str(error)).replace(token, '[redacted]')[:600])
        receipt.update(finished=_now(), calls=events, source_unchanged=source_context(ws)['snapshot_digest'] == before)
        _write_json(path, receipt)
        ws.ledger.append('trainer.cli_author_trial', receipt)
        print(json.dumps(receipt, ensure_ascii=True))
    finally:
        if lock.handle:lock.handle.close()


if __name__ == '__main__':main()
