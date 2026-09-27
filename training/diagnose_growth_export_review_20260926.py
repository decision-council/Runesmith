"""Trainer-only function diagnostic; no project or owner-test edits, no inference.

Runs the unchanged candidate function in a controlled namespace, not the full
application. This is a semantic review probe, not an acceptance/production test.
"""
import ast
import builtins
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runesmith.app.workspace import Workspace


def probe(draft, mode):
    content = next(f['content'] for f in draft['files'] if f['path']=='growthhat/cli.py')
    node = next(n for n in ast.parse(content).body if isinstance(n,ast.FunctionDef) and n.name=='cmd_export_recommendations')
    module = types.ModuleType('growthhat.exporting')
    def export(_):
        if mode=='export_error': raise RuntimeError('synthetic export failure')
        return {'recommendations':[]}
    module.export_recommendations=export
    opened=[]
    with tempfile.TemporaryDirectory(prefix='export-review-',dir=Path(__file__).parent/'.tmp') as directory:
        target=Path(directory)/'result.json'
        def competitor():
            if mode=='race' and not target.exists():
                with builtins.open(target,'xb') as handle:handle.write(b'race winner')
        def open_file(*args,**kwargs):
            competitor();return builtins.open(*args,**kwargs)
        def open_fd(*args,**kwargs):
            competitor();fd=os.open(*args,**kwargs);opened.append(fd);return fd
        namespace={'__package__':'growthhat','Path':Path,'Repository':object,'sys':sys,'json':json,
                   'open':open_file,'_os':types.SimpleNamespace(open=open_fd,fdopen=os.fdopen,close=os.close,
                       O_CREAT=os.O_CREAT,O_EXCL=os.O_EXCL,O_WRONLY=os.O_WRONLY)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<retained-candidate-function>','exec'),namespace)
        result={}
        try:
            with patch.dict(sys.modules,{'growthhat.exporting':module}), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                try:result['return_code']=namespace['cmd_export_recommendations'](types.SimpleNamespace(output=str(target)),object())
                except Exception as error:result['error']=type(error).__name__
            result['destination_exists']=target.exists()
            result['competitor_preserved']=target.exists() and target.read_bytes()==b'race winner'
            result['open_descriptors_after']=0
            for fd in opened:
                try:os.fstat(fd);result['open_descriptors_after']+=1
                except OSError:pass
        finally:
            for fd in opened:
                try:os.close(fd)
                except OSError:pass
        return result


if __name__=='__main__':
    ws=Workspace(Path('D:/Runesmith/training/GrowthHat'))
    ids=sys.argv[1:] or ['d202609261957066ca2','d202609262025386e60']
    for did in ids:
        draft=ws._draft(did)
        print(json.dumps({'draft':did,'scope':'trainer function probe, not acceptance',
                          'race':probe(draft,'race'),'export_error':probe(draft,'export_error')}))
