"""Offline Studio catalog integration: no model inference or live provider calls."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from runesmith.app import providers
from runesmith.app.server import api_models
from runesmith.app.workspace import Workspace


@pytest.mark.parametrize('base', ['http://gateway.test', 'http://gateway.test/v1/'])
def test_milliner_catalog_uses_qualified_free_call_names(monkeypatch, base):
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return 200, {'models': [
            {'call_name': 'cline:stealth/pixel-canary'},
            {'provider': 'cline', 'model_id': 'cline-free/gemini-3.8-flash'},
            {'call_name': 'cline:stealth/pixel-canary'}, None, {'call_name': 7}, {}]}
    monkeypatch.setattr(providers, '_get_json', get)
    result = providers.list_models(base, 'synthetic-token', kind='milliner')
    assert calls[0][0] == 'http://gateway.test/v1/models?free=true&profiles=false&limit=500'
    assert calls[0][1]['headers'] == {'Authorization': 'Bearer synthetic-token'}
    assert result['models'] == ['cline:cline-free/gemini-3.8-flash', 'cline:stealth/pixel-canary']
    assert result['count'] == 2 and 'does not confirm' in result['detail']
    assert 'synthetic-token' not in str(result)


def test_openai_catalog_keeps_its_existing_endpoint(monkeypatch):
    def get(url, **kwargs):
        assert url == 'https://provider.test/v1/models'
        return 200, {'data': [{'id': 'b'}, {'id': 'a'}, {'id': 'a'}, {'id': 9}, None]}
    monkeypatch.setattr(providers, '_get_json', get)
    assert providers.list_models('https://provider.test/v1/')['models'] == ['a', 'b']


def test_provider_filter_reaches_actual_studio_route_before_catalog_limit(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    def get(url, **kwargs):
        assert url == 'http://gateway.test/v1/models?free=true&profiles=false&limit=500&provider=opencode'
        return 200, {'models': [{'call_name': 'opencode:longcat-2.5-preview-free'}]}
    monkeypatch.setattr(providers, '_get_json', get)
    response = api_models(SimpleNamespace(ws=ws), {}, {'preset': 'milliner',
        'base_url': 'http://gateway.test', 'provider': 'opencode'})
    assert response['models'] == ['opencode:longcat-2.5-preview-free']
    assert response['provider'] == 'opencode'
    ui = (Path(__file__).parents[1]/'runesmith/app/static/js/views/inference.js').read_text(encoding='utf-8')
    assert 'Catalog provider filter' in ui and 'providerFilter.value.trim().toLowerCase()' in ui


@pytest.mark.parametrize('value', ['opencode&free=false', '../opencode', 'opencode:model', ['opencode'], None])
def test_invalid_provider_filter_refuses_without_network(monkeypatch, value):
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid provider must not reach the network')
    monkeypatch.setattr(providers, '_get_json', forbidden)
    response = providers.list_models('http://gateway.test', kind='milliner', provider=value)
    assert not response['ok'] and 'bare provider' in response['detail']


@pytest.mark.parametrize('status,body', [(401, {'error': 'unauthorized'}), (200, {}), (200, {'models': 'invalid'})])
def test_bad_catalog_is_not_reported_as_success(monkeypatch, status, body):
    monkeypatch.setattr(providers, '_get_json', lambda *a, **k: (status, body))
    result = providers.list_models('http://gateway.test', kind='milliner')
    assert not result['ok'] and result['models'] == []


def test_actual_studio_route_uses_milliner_preset_and_explicit_token(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    seen = []
    def get(url, **kwargs):
        seen.append(url)
        assert kwargs['headers']['Authorization'] == 'Bearer synthetic-input'
        return 200, {'models': [{'call_name': 'cline:stealth/pixel-canary'}]}
    monkeypatch.setattr(providers, '_get_json', get)
    response = api_models(SimpleNamespace(ws=ws), {}, {'preset': 'milliner',
        'base_url': 'http://gateway.test', 'key': 'synthetic-input'})
    assert response['ok'] and len(seen) == 1 and '/v1/models?' in seen[0]
    assert 'synthetic-input' not in str(response)


def test_saved_milliner_environment_token_is_resolved_for_catalog(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    monkeypatch.setenv('RUNESMITH_TEST_GATEWAY_TOKEN', 'synthetic-environment')
    config = ws.config()
    config['instruments']['gateway'] = {'kind': 'milliner', 'model': 'test:model',
        'base_url': 'http://gateway.test', 'token_env': 'RUNESMITH_TEST_GATEWAY_TOKEN'}
    ws.save_config(config)
    def get(url, **kwargs):
        assert kwargs['headers']['Authorization'] == 'Bearer synthetic-environment'
        return 200, {'models': []}
    monkeypatch.setattr(providers, '_get_json', get)
    assert ws.list_models(name='gateway')['ok']
    # A caller cannot redirect a saved credential by changing only the address.
    assert not ws.list_models(name='gateway', base_url='https://elsewhere.test')['ok']


def test_saved_secret_and_empty_catalog_do_not_expose_credentials(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ws.save_instrument('gateway', {'kind': 'milliner', 'model': 'test:model',
        'base_url': 'http://gateway.test'}, key_value='synthetic-saved-token')
    def get(url, **kwargs):
        assert kwargs['headers']['Authorization'] == 'Bearer synthetic-saved-token'
        return 200, {'models': []}
    monkeypatch.setattr(providers, '_get_json', get)
    result = ws.list_models(name='gateway')
    assert result['ok'] and result['count'] == 0
    assert 'synthetic-saved-token' not in str(result)
    ui = (Path(__file__).parents[1]/'runesmith/app/static/js/views/inference.js').read_text(encoding='utf-8')
    assert "post('/api/inference/models'" in ui
    assert 'catalog entries shown' in ui and 'r.detail' in ui
