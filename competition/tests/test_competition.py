import copy
import json
import time

import pytest
from fastapi.testclient import TestClient

from competition.app import create_app
from competition.config import Settings
from competition.evaluator import VERSION, digest, evaluate, summarize
from competition.models import Pack, RevisionCreate, StrategyCreate
from competition.store import Problem, Store, token_hash


def benchmark():
    return {'id':'tiny-v1','name':'Test only','evaluator_version':VERSION,'license':'Test fixture',
            'container':{'width':4.,'depth':4.,'height':4.},'stacking_rule':'none',
            'skus':{'a':{'length':1.,'width':1.,'height':1.,'weight':2.,'name':'A'}},
            'orders':{oid:{'items':[{'sku_id':'a','quantity':1}],
                           'instances':[{'id':'a:0000','sku_id':'a'}]} for oid in ('one','two')}}


def pack(oid='one',**changes):
    b={'id':'a:0000','sku_id':'a','rotation':0,'position':{'x':.5,'y':.5,'z':.5}}
    b.update(changes)
    return {'order_id':oid,'boxes':[b]}


@pytest.fixture
def store(tmp_path):
    s=Store(tmp_path/'store.sqlite');s.add_benchmark(benchmark());return s


@pytest.fixture
def client(tmp_path):
    app=create_app(Settings(database=str(tmp_path/'api.sqlite')))
    app.state.store.add_benchmark(benchmark())
    with TestClient(app,base_url='http://127.0.0.1:8769') as c:
        yield c


def login(client,name='Alice',scopes=('submit','publish')):
    store=client.app.state.store
    u=store.user('test',name,name,name+'@example.test')
    raw=store.credential(u['id'],'test',list(scopes),3600)
    return u,{'Authorization':'Bearer '+raw}


def draft(client,headers):
    r=client.post('/api/strategies',json={'name':'Test strategy'},headers=headers)
    assert r.status_code==201,r.text
    sid=r.json()['id']
    r=client.post('/api/strategies/'+sid+'/revisions',json={'benchmark_id':'tiny-v1','notes':'Initial','code_revision':'test-v1'},headers=headers)
    assert r.status_code==201,r.text
    return sid,r.json()['id']


def test_pallet_support_and_fixed_denominator():
    b=benchmark();r=evaluate(b,Pack.model_validate(pack()))
    assert r['valid'] and r['complete'] and r['static_equilibrium']=='balanced'
    assert r['lve']==16 and r['weight_kg']==2
    s=summarize(b,{'one':r})
    assert s['completion_fraction']==.5 and s['orders_missing']==1


@pytest.mark.parametrize('position',[{'x':.5,'y':.5,'z':1.5},{'x':-.1,'y':.5,'z':.5},{'x':4.,'y':.5,'z':.5}])
def test_floating_or_outside_rejected(position):
    r=evaluate(benchmark(),Pack.model_validate(pack(position=position)))
    assert not r['valid'] and r['accepted_boxes']==0 and r['lve'] is None


def test_empty_pack_is_partial_not_failure_or_completion():
    r=evaluate(benchmark(),Pack(order_id='one',boxes=[]))
    assert r['valid'] and not r['complete'] and r['remaining']==1


@pytest.mark.parametrize('field,value',[('weight',.01),('dimensions',{'width':.1,'depth':.1,'height':.1}),('rotation',180)])
def test_client_cannot_invent_dimensions_or_weight(field,value):
    with pytest.raises(ValueError):
        Pack.model_validate(pack(**{field:value}))


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),float('-inf')])
def test_nonfinite_coordinates_rejected(bad):
    with pytest.raises(ValueError):
        Pack.model_validate(pack(position={'x':bad,'y':.5,'z':.5}))


def test_duplicate_and_forged_ids_not_complete():
    p=pack();p['boxes']*=2
    r=evaluate(benchmark(),Pack.model_validate(p));assert not r['valid'] and r['remaining']==1
    r=evaluate(benchmark(),Pack.model_validate(pack(id='invented')));assert not r['valid']
    r=evaluate(benchmark(),Pack.model_validate(pack(sku_id='invented')));assert not r['valid']


def fixture_pack(specs):
    b=benchmark();b['skus']={};instances=[];boxes=[]
    for i,(x,y,z,w,d,h,weight) in enumerate(specs):
        sku=str(i);b['skus'][sku]={'length':w,'width':d,'height':h,'weight':weight}
        instances.append({'id':sku,'sku_id':sku})
        boxes.append({'id':sku,'sku_id':sku,'position':{'x':x,'y':y,'z':z}})
    b['orders']={'one':{'instances':instances,'items':[{'sku_id':str(i),'quantity':1} for i in range(len(specs))]}}
    return b,Pack.model_validate({'order_id':'one','boxes':boxes})


def test_overlap_rejected():
    b,p=fixture_pack([(.5,.5,.5,1,1,1,1),(.5,.5,.5,1,1,1,1)])
    r=evaluate(b,p);assert not r['valid'] and any('Overlap' in s for s in r['errors'])


def test_bridge_transfers_load_to_both_supports():
    b,p=fixture_pack([(.1,.5,.1,.2,1,.2,1),(.9,.5,.1,.2,1,.2,1),(.5,.5,.3,1,1,.2,10)])
    r=evaluate(b,p);assert r['complete'],r
    assert len([e for e in r['support_contacts'] if e['upper']=='2'])==2


def test_top_load_can_destabilize_lower_interface():
    b,p=fixture_pack([(.4,.5,.1,.2,1,.2,1),(.4,.5,.3,.8,1,.2,1),(.65,.5,.5,.2,1,.2,100)])
    r=evaluate(b,p);assert not r['valid'] and r['static_equilibrium']=='unstable'


def test_weight_class_gate_is_explicit():
    b,p=fixture_pack([(.5,.5,.1,1,1,.2,1),(.5,.5,.3,1,1,.2,10)])
    b['skus']['0']['stack_class']='light';b['skus']['1']['stack_class']='heavy'
    assert evaluate(b,p)['valid']
    b['stacking_rule']='heavy-not-on-light'
    assert not evaluate(b,p)['valid']


def test_wrong_evaluator_rejected():
    b=benchmark();b['evaluator_version']='future'
    with pytest.raises(ValueError):evaluate(b,Pack.model_validate(pack()))


def test_benchmark_cannot_change_in_place(store):
    b=benchmark();store.add_benchmark(b)
    b['skus']['a']['weight']=.1
    with pytest.raises(Problem) as exc:store.add_benchmark(b)
    assert exc.value.status==409


def test_full_submission_revision_flow(client):
    u,h=login(client);sid,rid=draft(client,h)
    r=client.put(f'/api/revisions/{rid}/packs',json={'packs':[pack(),pack('two')]},headers=h)
    assert r.status_code==200 and all(v['complete'] for v in r.json().values()),r.text
    pub=client.post(f'/api/revisions/{rid}/publish',headers=h)
    assert pub.status_code==200,pub.text
    assert client.post(f'/api/revisions/{rid}/publish',headers=h).json()==pub.json()
    board=client.get('/api/benchmarks/tiny-v1/leaderboard').json()
    assert board[0]['rank']==1 and board[0]['summary']['orders_complete']==2
    r=client.put(f'/api/revisions/{rid}/packs',json={'packs':[pack()]},headers=h)
    assert r.status_code==409
    child=client.post(f'/api/strategies/{sid}/revisions',headers=h,json={
        'benchmark_id':'tiny-v1','parent_id':rid,'notes':'Better version','code_revision':'v2'}).json()['id']
    inherited=client.get('/api/revisions/'+child,headers=h).json()
    assert inherited['summary']['orders_complete']==2 and inherited['parent_id']==rid
    client.put(f'/api/revisions/{child}/packs',headers=h,json={'packs':[{'order_id':'two','boxes':[]}]})
    assert client.get('/api/revisions/'+rid).json()['summary']['orders_complete']==2
    assert client.get('/api/revisions/'+child,headers=h).json()['summary']['orders_complete']==1
    delta=client.get(f'/api/revisions/{rid}/compare/{child}',headers=h).json()
    assert delta['changed_orders']==['two'] and delta['matched_complete_orders']==1


def test_missing_and_invalid_orders_never_rank(client):
    _,h=login(client);_,rid=draft(client,h)
    client.put(f'/api/revisions/{rid}/packs',headers=h,json={'packs':[pack()]})
    client.post(f'/api/revisions/{rid}/publish',headers=h)
    entry=client.get('/api/benchmarks/tiny-v1/leaderboard').json()[0]
    assert entry['rank'] is None and entry['summary']['completion_fraction']==.5


def test_anonymous_and_other_owner_cannot_access_drafts(client):
    _,a=login(client);_,b=login(client,'Bob');sid,rid=draft(client,a)
    assert client.get('/api/revisions/'+rid).status_code==404
    assert client.get('/api/revisions/'+rid,headers=b).status_code==404
    assert client.put(f'/api/revisions/{rid}/packs',headers=b,json={'packs':[pack()]}).status_code==404
    assert client.post(f'/api/revisions/{rid}/publish',headers=b).status_code==404
    assert client.post('/api/strategies',json={'name':'Forbidden'}).status_code==401


def test_upload_only_token_cannot_publish_or_mint_tokens(client):
    _,h=login(client,scopes=['submit']);_,rid=draft(client,h)
    assert client.post(f'/api/revisions/{rid}/publish',headers=h).status_code==403
    assert client.post('/api/auth/tokens',headers=h,json={'name':'escalate'}).status_code==401


def test_cookie_write_requires_same_origin(client):
    u,_=login(client);token=client.app.state.store.credential(u['id'],'session',['session','submit'],60)
    client.cookies.set('competition_session',token)
    assert client.post('/api/strategies',json={'name':'Blocked'}).status_code==403
    assert client.post('/api/strategies',json={'name':'Allowed'},headers={'Origin':'http://127.0.0.1:8769'}).status_code==201


def test_auth_disabled_by_default_and_no_legacy_admin(client):
    assert client.get('/api/auth/options').json()=={'google':False,'email':False,'local_admin':False,'configured':False}
    assert client.get('/api/auth/google').status_code==503
    assert client.post('/api/auth/email',json={'email':'test@example.test'}).status_code==503
    assert client.get('/admin/orders').status_code==404
    assert client.get('/auth/users').status_code==404


def test_expired_and_revoked_credentials(store):
    u=store.user('test','one','One','one@example.test')
    token=store.credential(u['id'],'token',['submit'],-1)
    assert store.authenticate(token) is None
    token=store.credential(u['id'],'token',['submit'],60)
    assert store.authenticate(token)
    with store.connect(True) as db:db.execute('DELETE FROM credentials WHERE hash=?',(token_hash(token),))
    assert store.authenticate(token) is None


def test_login_ticket_one_use_expiring_and_browser_bound(store):
    t=store.ticket('email',{'binding':token_hash('browser'),'email':'test@example.test'})
    with pytest.raises(Problem):store.consume_ticket('email',t,'wrong-browser')
    assert store.consume_ticket('email',t,'browser')['email']=='test@example.test'
    with pytest.raises(Problem):store.consume_ticket('email',t,'browser')
    t=store.ticket('email',{'binding':token_hash('browser')},-1)
    with pytest.raises(Problem):store.consume_ticket('email',t,'browser')


def test_bad_batch_rolls_back(client):
    _,h=login(client);_,rid=draft(client,h)
    response=client.put(f'/api/revisions/{rid}/packs',headers=h,json={'packs':[pack(),pack('unknown')]})
    assert response.status_code==422
    assert client.get('/api/revisions/'+rid,headers=h).json()['reports']=={}
    assert client.put(f'/api/revisions/{rid}/packs',headers=h,json={'packs':[pack(),pack()]}).status_code==422


def test_viewer_reads_frozen_dataset_not_mutable_master(client):
    _,h=login(client);_,rid=draft(client,h)
    client.put(f'/api/revisions/{rid}/packs',headers=h,json={'packs':[pack()]})
    assert client.get(f'/viz?benchmark=tiny-v1&revision={rid}').status_code==404
    response=client.get(f'/viz?embed=1&benchmark=tiny-v1&revision={rid}',headers=h)
    assert response.status_code==200 and '/api/view/tiny-v1/'+rid in response.text
    d=client.get(f'/api/view/tiny-v1/{rid}/viz-api/ep-result/one',headers=h).json()
    assert d['pack']['boxes'][0]['weight']==2


def test_body_size_limit(client):
    r=client.post('/api/strategies',content=b'x'*(8*1024*1024+1),headers={'Content-Type':'application/json'})
    assert r.status_code==413


def test_rate_limit_persists(store):
    store.limit('key',1,60)
    with pytest.raises(Problem) as exc:Store(store.path).limit('key',1,60)
    assert exc.value.status==429


def test_blank_required_metadata_rejected():
    with pytest.raises(ValueError):StrategyCreate(name='   ')
    with pytest.raises(ValueError):RevisionCreate(benchmark_id='tiny-v1',notes=' ',code_revision='test')


def test_evaluation_capacity_is_bounded_and_released_after_errors(client):
    _,h=login(client);_,rid=draft(client,h);store=client.app.state.store
    assert store.evaluation_slots.acquire(blocking=False)
    assert store.evaluation_slots.acquire(blocking=False)
    try:
        assert client.put(f'/api/revisions/{rid}/packs',headers=h,json={'packs':[pack()]}).status_code==503
    finally:
        store.evaluation_slots.release();store.evaluation_slots.release()
    # Failed validation must not leak a slot and eventually block all uploads.
    for _ in range(3):
        assert client.put(f'/api/revisions/{rid}/packs',headers=h,json={'packs':[pack('unknown')]}).status_code==422
    assert client.put(f'/api/revisions/{rid}/packs',headers=h,json={'packs':[pack()]}).status_code==200


def test_google_state_and_pkce_setup(tmp_path):
    app=create_app(Settings(database=str(tmp_path/'google.sqlite'),google_client_id='test-id',google_client_secret='test-only'))
    with TestClient(app,base_url='http://127.0.0.1:8769') as c:
        r=c.get('/api/auth/google',follow_redirects=False)
        from urllib.parse import urlparse,parse_qs
        args=parse_qs(urlparse(r.headers['location']).query)
        assert args['scope']==['openid email profile'] and args['code_challenge_method']==['S256']
        assert len(args['state'][0])>30 and len(args['nonce'][0])>30
        assert args['redirect_uri']==['http://127.0.0.1:8769/api/auth/google/callback']
        assert c.get('/api/auth/google/callback?state=invalid&code=test').status_code==400


def test_email_flow_with_mock_delivery(tmp_path,monkeypatch):
    sent=[]
    monkeypatch.setattr('competition.auth.send_mail',lambda settings,email,link:sent.append((email,link)))
    app=create_app(Settings(database=str(tmp_path/'mail.sqlite'),smtp_host='example.test',smtp_username='test',smtp_password='test',mail_from='sender@example.test'))
    with TestClient(app,base_url='http://127.0.0.1:8769') as c:
        h={'Origin':'http://127.0.0.1:8769'}
        r=c.post('/api/auth/email',headers=h,json={'email':'alice@example.test'})
        assert r.status_code==200 and 'token' not in r.text
        token=sent[0][1].split('#sign-in=')[1]
        assert c.post('/api/auth/email/finish',headers=h,json={'token':token}).status_code==200
        assert c.get('/api/auth/me').json()['user']['name']=='alice'
        assert c.post('/api/auth/email/finish',headers=h,json={'token':token}).status_code==400
        issued=c.post('/api/auth/tokens',headers=h,json={'name':'MCP'}).json()['token']
        entries=c.get('/api/auth/tokens').json();assert entries[0]['scopes']==['submit']
        assert app.state.store.authenticate(issued)
        assert c.delete('/api/auth/tokens/'+entries[0]['id'],headers=h).status_code==200
        assert app.state.store.authenticate(issued) is None


@pytest.mark.parametrize('origin',['http://example.com','https://name:password@example.com','https://example.com/path'])
def test_insecure_configuration_rejected(origin):
    with pytest.raises(ValueError):Settings(origin=origin)
