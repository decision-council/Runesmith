"""Local verification inputs are larger than, and distinct from, a model packet.

The v1 profile covers source/config plus declared text documents and synthetic
fixtures/static assets. It excludes live data and credentials. This is a named,
bounded verification profile, not a claim to capture every possible dependency.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

POLICY = 'local-build-inputs-v1'
# JavaScript modules too (.mjs, .cjs): a node project's `motion.mjs` was "outside the local verification profile",
# so no draft of it could be checked (journey J11-B5). The map already knew them (envmap.NODE_SOURCE_SUFFIXES).
SOURCE_EXTENSIONS = {'.py','.js','.mjs','.cjs','.ts','.mts','.cts','.tsx','.jsx','.html','.css','.toml','.json',
                     '.yaml','.yml','.ini','.cfg'}
EXCLUDED_DIRS = {'.git','.runesmith','.venv','venv','node_modules','__pycache__','.tmp',
                 'var','logs','data','dist','build','secrets','credentials','private','customers'}
LOCAL_ASSETS = {'fixtures','assets','static','templates'}
MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 3000, 2_000_000, 32_000_000
DOCUMENT_SUFFIXES = {'.md','.markdown','.txt','.rst'}


def document_folder(rel):
    """The declared-documents entry that shares every document in rel's folder: "recipes/", or "./" for the top."""
    parent = Path(rel).parent.as_posix()
    return ('.' if parent in ('', '.') else parent) + '/'


class SnapshotUnsupported(RuntimeError):
    pass


def _linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def path_kind(rel, declared=()):
    p=Path(rel)
    parts=[part.lower() for part in p.parts]
    name=parts[-1]
    if any(part in EXCLUDED_DIRS or part.startswith('.') for part in parts):
        return None
    if (p.suffix.lower() in {'.key','.pem','.p12','.pfx','.db','.sqlite','.sqlite3','.log','.jsonl'}
            or any(word in name for word in ('secret','credential','token','private'))
            or name.endswith(('.lock','-lock.json')) or name=='env'):
        return None
    # Asset/fixture bytes stay local, even when they happen to be JSON or text.
    if any(part in LOCAL_ASSETS for part in parts[:-1]):
        return 'local'
    if p.suffix.lower() in SOURCE_EXTENSIONS:
        return 'model'
    # Declared documents: files the owner listed as build paths, or every document in a folder where the owner shared
    # one ("recipes/"). They are verification inputs only: a model sees a document's text only if the owner ticked it.
    if p.suffix.lower() in DOCUMENT_SUFFIXES and (rel in declared or document_folder(rel) in declared):
        return 'local'
    return None


def digest_files(files, declared=()):
    manifest={rel:{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
                   'visibility':path_kind(rel,declared)} for rel,data in sorted(files.items())}
    policy={'profile':POLICY,'declared_documents':sorted(declared)}
    digest=hashlib.sha256(json.dumps({'policy':policy,'files':manifest},sort_keys=True).encode()).hexdigest()
    return {'digest':digest,'policy':policy,'manifest':manifest}


def collect_snapshot(ws):
    declared=tuple(p for p in ws.settings().get('build_paths',[]) if Path(p).suffix.lower() in {'.md','.txt','.rst'})
    # A document the owner shared with models (Goals & plan) shares its folder with the build pipeline, so drafts can
    # edit it or add a page beside it, and the owner's checks run on a copy that holds them (journey J4-G3).
    shared=sorted({document_folder(b['path']) for b in ws.brief().get('blueprints',[]) if isinstance(b,dict) and b.get('path')})
    declared=tuple(sorted(set(declared)|set(shared)))
    files={};total=0
    excluded=[]
    for directory,dirs,names in os.walk(ws.root,followlinks=False):
        parent=Path(directory)
        dirs[:]=sorted(d for d in dirs if d.lower() not in EXCLUDED_DIRS and not d.startswith('.')
                       and not _linked(parent/d) and not (parent/d).resolve().is_relative_to(ws.home))
        for name in sorted(names):
            path=parent/name;rel=path.relative_to(ws.root).as_posix()
            if _linked(path) or not path_kind(rel,declared):
                excluded.append(rel)
                continue
            try:
                if path.stat().st_size>MAX_FILE_BYTES:
                    raise SnapshotUnsupported(f'Local verification input exceeds {MAX_FILE_BYTES} bytes: {rel}')
                data=path.read_bytes()
            except OSError as error:
                raise SnapshotUnsupported(f'Cannot read local verification input: {rel}') from error
            if len(data)>MAX_FILE_BYTES or total+len(data)>MAX_TOTAL_BYTES or len(files)>=MAX_FILES:
                raise SnapshotUnsupported('Local verification snapshot exceeds the declared resource profile.')
            total+=len(data);files[rel]=data
    return dict(digest_files(files,declared),files=files,excluded=excluded)


def freeze_snapshot(ws,snapshot):
    from runesmith.app.workspace import _write_json
    root=ws.home/'build-snapshots'/snapshot['digest']
    marker=root/'MANIFEST.json'
    if marker.exists():
        # Never repair/rewrite an existing sealed directory in place.
        load_snapshot(ws,snapshot['digest'])
        return
    for rel,data in snapshot['files'].items():
        target=root/'files'/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    _write_json(marker,{k:snapshot[k] for k in ('digest','policy','manifest','excluded')})


def load_snapshot(ws,digest):
    from runesmith.app.workspace import _read_json
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise SnapshotUnsupported('Invalid snapshot identity.')
    root=ws.home/'build-snapshots'/digest
    header=_read_json(root/'MANIFEST.json',{})
    files={}
    if header.get('policy',{}).get('profile')!=POLICY:
        raise SnapshotUnsupported('Snapshot profile is missing or changed.')
    for rel,entry in header.get('manifest',{}).items():
        path=root/'files'/rel
        if not path.resolve().is_relative_to((root/'files').resolve()) or _linked(path):
            raise SnapshotUnsupported('Invalid snapshot input path.')
        try:data=path.read_bytes()
        except OSError as error:raise SnapshotUnsupported('Snapshot bytes are missing.') from error
        if hashlib.sha256(data).hexdigest()!=entry['sha256']:
            raise SnapshotUnsupported('Snapshot bytes differ from their manifest.')
        files[rel]=data
    checked=digest_files(files,header['policy'].get('declared_documents',[]))
    if checked['digest']!=digest:
        raise SnapshotUnsupported('Snapshot manifest does not match its identity.')
    return dict(header,files=files)
