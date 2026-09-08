"""Local provider shortcut must never become a public authentication bypass."""
import pytest
from fastapi.testclient import TestClient

from competition.app import create_app
from competition.config import Settings
from competition.tests.test_competition import benchmark, draft, login

ORIGIN='http://127.0.0.1:8769'
LOGIN={'username':'admin','password':'admin'}
HEADERS={'Origin':ORIGIN}


@pytest.fixture
def local_client(tmp_path):
    app=create_app(Settings(database=str(tmp_path/'local.sqlite'),local_admin_login=True))
    app.state.store.add_benchmark(benchmark())
    with TestClient(app,base_url=ORIGIN,client=('127.0.0.1',12345)) as client:
        yield client


def test_local_admin_sign_in_session_and_logout(local_client):
    c=local_client
    assert c.get('/api/auth/options').json()['local_admin'] is True
    response=c.post('/api/auth/local-admin',json=LOGIN,headers=HEADERS)
    assert response.status_code==200
    assert 'HttpOnly' in response.headers['set-cookie']
    assert c.get('/api/auth/me').json()['user']['name']=='Local admin'
    assert c.post('/api/strategies',json={'name':'Local test'},headers=HEADERS).status_code==201
    assert c.get('/api/mine').json()[0]['name']=='Local test'
    assert c.post('/api/auth/logout',headers=HEADERS).status_code==200
    assert c.get('/api/auth/me').json()['user'] is None


def test_local_admin_does_not_bypass_revision_ownership(local_client):
    c=local_client
    _,other=login(c,'Other researcher');_,rid=draft(c,other)
    assert c.post('/api/auth/local-admin',json=LOGIN,headers=HEADERS).status_code==200
    assert c.get('/api/revisions/'+rid).status_code==404
    assert c.post('/api/revisions/'+rid+'/publish',headers=HEADERS).status_code==404


def test_login_requires_exact_credentials_origin_and_rate_limit(local_client):
    c=local_client
    assert c.post('/api/auth/local-admin',json=LOGIN).status_code==403
    assert c.post('/api/auth/local-admin',json=LOGIN,headers={'Origin':'https://unrelated.example'}).status_code==403
    for i in range(10):
        assert c.post('/api/auth/local-admin',json={'username':'admin','password':'wrong'},headers=HEADERS).status_code==401
    assert c.post('/api/auth/local-admin',json=LOGIN,headers=HEADERS).status_code==429


@pytest.mark.parametrize('origin',[ORIGIN,'https://palletizing-benchmark.org'])
def test_admin_disabled_without_explicit_opt_in(tmp_path,origin):
    app=create_app(Settings(database=str(tmp_path/'disabled.sqlite'),origin=origin))
    with TestClient(app,base_url=origin,client=('127.0.0.1',12345)) as c:
        assert not c.get('/api/auth/options').json()['local_admin']
        assert c.post('/api/auth/local-admin',json=LOGIN,headers={'Origin':origin}).status_code==404


def test_public_origin_cannot_enable_admin():
    with pytest.raises(ValueError,match='loopback'):
        Settings(origin='https://palletizing-benchmark.org',local_admin_login=True)


@pytest.mark.parametrize('peer,forwarded',[
    ('192.0.2.10',{}),
    ('127.0.0.1',{'X-Forwarded-For':'127.0.0.1'}),
    ('127.0.0.1',{'Forwarded':'for=127.0.0.1'}),
])
def test_nonlocal_and_forwarded_requests_cannot_use_admin(tmp_path,peer,forwarded):
    app=create_app(Settings(database=str(tmp_path/'network.sqlite'),local_admin_login=True))
    with TestClient(app,base_url=ORIGIN,client=(peer,12345)) as c:
        assert not c.get('/api/auth/options',headers=forwarded).json()['local_admin']
        assert c.post('/api/auth/local-admin',json=LOGIN,headers=HEADERS|forwarded).status_code==404


def test_local_sessions_and_tokens_rejected_after_disable_and_on_production(local_client):
    c=local_client
    assert c.post('/api/auth/local-admin',json=LOGIN,headers=HEADERS).status_code==200
    token=c.post('/api/auth/tokens',json={'name':'Local MCP'},headers=HEADERS).json()['token']
    assert c.get('/api/mine',headers={'Authorization':'Bearer '+token}).status_code==200
    session=c.cookies.get('competition_session')
    c.app.state.settings.local_admin_login=False
    assert c.get('/api/mine').status_code==401
    assert c.get('/api/mine',headers={'Authorization':'Bearer '+token}).status_code==401
    app=create_app(Settings(database=str(c.app.state.store.path),origin='https://palletizing-benchmark.org'))
    with TestClient(app,base_url='https://palletizing-benchmark.org',client=('127.0.0.1',12345)) as prod:
        prod.cookies.set('competition_session',session)
        assert prod.get('/api/mine').status_code==401
        assert prod.get('/api/mine',headers={'Authorization':'Bearer '+token}).status_code==401


def test_env_opt_in(monkeypatch):
    monkeypatch.setenv('LOCAL_ADMIN_LOGIN','1')
    monkeypatch.setenv('PUBLIC_ORIGIN',ORIGIN)
    assert Settings.from_env().local_admin_login
