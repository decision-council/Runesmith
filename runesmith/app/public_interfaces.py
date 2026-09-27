"""Small author-visible JSON interface declarations, not executable acceptance.

Flat object fields or fields of each object in an array. Nested shape and
behavior belong in descriptions/owner checks; this is not arbitrary JSON Schema.
"""
import json
import re

from runesmith.app.workspace import WorkspaceError

TYPES = ('string', 'integer', 'number', 'boolean', 'object', 'array')


def clean_interfaces(rows, criterion_ids):
    if not isinstance(rows, list) or len(rows) > 16:
        raise WorkspaceError('Use at most 16 public interfaces.')
    result, ids = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'id', 'invocation', 'description', 'criterion_ids', 'response_type', 'fields'}:
            raise WorkspaceError('An interface has unsupported fields.')
        key = row.get('id')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', key) or key in ids:
            raise WorkspaceError('Public interface IDs must be unique.')
        ids.add(key)
        invocation, description = row.get('invocation'), row.get('description', '')
        if not isinstance(invocation, str) or not invocation.strip() or len(invocation) > 400 or not isinstance(description, str) or len(description) > 1200:
            raise WorkspaceError('Describe the public command/API and response within the field limits.')
        linked = row.get('criterion_ids')
        if not isinstance(linked, list) or not linked or any(not isinstance(v, str) or v not in criterion_ids for v in linked) or len(set(linked)) != len(linked):
            raise WorkspaceError('Link each interface to existing unique public criterion IDs.')
        if row.get('response_type') not in ('object', 'array'):
            raise WorkspaceError('The response must be an object or an array of objects.')
        fields, names = row.get('fields'), set()
        if not isinstance(fields, list) or not 1 <= len(fields) <= 40:
            raise WorkspaceError('Describe 1–40 fields per public interface.')
        clean = []
        for field in fields:
            if not isinstance(field, dict) or set(field) - {'name', 'type', 'required', 'nullable', 'unit', 'description'}:
                raise WorkspaceError('An interface field has unsupported attributes.')
            name = field.get('name')
            if not isinstance(name, str) or not name.strip() or len(name) > 100 or name in names:
                raise WorkspaceError('Response field names must be nonempty and unique.')
            names.add(name)
            if field.get('type') not in TYPES or type(field.get('required')) is not bool or type(field.get('nullable')) is not bool:
                raise WorkspaceError('Each response field needs a supported type and explicit required/nullable switches.')
            if any(not isinstance(field.get(k, ''), str) or len(field.get(k, '')) > limit
                   for k, limit in (('unit', 80), ('description', 1200))):
                raise WorkspaceError('Response field descriptions or units exceed their limits.')
            clean.append({k: field.get(k, '') for k in ('name', 'type', 'required', 'nullable', 'unit', 'description')})
        result.append({'id': key, 'invocation': invocation.strip(), 'description': description.strip(),
                       'criterion_ids': linked, 'response_type': row['response_type'], 'fields': clean})
    if len(json.dumps(result).encode()) > 24000:
        raise WorkspaceError('Public interfaces exceed the 24000-byte author-packet allowance.')
    return result
