"""Standalone public portal. Does NOT mount the legacy administration backend."""
import json
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from .auth import optional_user, principal, routes as auth_routes
from .config import ROOT, Settings
from .evaluator import VERSION, materialize
from .models import Batch, Pack, RevisionCreate, StrategyCreate
from .store import Problem, Store


class RequestLimits:
    """Limit actual bytes, including chunked requests; never trust Content-Length."""
    def __init__(self, app):
        self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type'] != 'http':
            return await self.app(scope,receive,send)
        if scope['method'] in ('POST','PUT','PATCH'):
            body=bytearray()
            while True:
                part=await receive()
                if part['type']=='http.disconnect':
                    return
                body.extend(part.get('body',b''))
                if len(body)>8*1024*1024:
                    return await JSONResponse({'detail':'Request exceeds the 8 MiB limit.'},413)(scope,receive,send)
                if not part.get('more_body'):
                    break
            sent=False
            async def limited_receive():
                nonlocal sent
                if sent:
                    return await receive()
                sent=True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await self.app(scope,limited_receive,send)
        return await self.app(scope,receive,send)


def create_app(settings=None):
    settings=settings or Settings.from_env()
    store=Store(settings.database)
    app=FastAPI(title='Palletizing Benchmark Competition',version='0.1.0',docs_url=None,redoc_url=None,openapi_url='/api/openapi.json')
    app.state.settings=settings; app.state.store=store
    app.add_middleware(RequestLimits)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=[urlparse(settings.origin).hostname])

    @app.middleware('http')
    async def headers(request,call_next):
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='SAMEORIGIN'
        # Existing Three.js viewer contains inline source; new portal has external scripts.
        script="'self' 'unsafe-inline'" if request.url.path=='/viz' else "'self'"
        response.headers['Content-Security-Policy']=f"default-src 'self'; script-src {script}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'"
        if request.url.path.startswith('/api/auth') or request.cookies or request.headers.get('authorization'):
            response.headers['Cache-Control']='no-store'
        if settings.secure:
            response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    @app.exception_handler(Problem)
    async def problem(request,exc):
        return JSONResponse({'detail':exc.message},exc.status)

    app.include_router(auth_routes(store,settings))

    @app.get('/health')
    def health():
        return {'ok':True,'evaluator_version':VERSION}

    @app.get('/api/benchmarks')
    def benchmarks():
        return store.benchmarks()

    @app.get('/api/benchmarks/{bid}')
    def benchmark(bid:str):
        return store.benchmark(bid)

    @app.get('/api/benchmarks/{bid}/leaderboard')
    def leaderboard(bid:str):
        return store.leaderboard(bid)

    @app.get('/api/benchmarks/{bid}/manifest')
    def manifest(bid:str):
        doc=store.benchmark(bid)
        from .evaluator import digest
        return {k:v for k,v in doc.items() if k not in ('orders','skus')} | {
            'sha256':digest(doc),'orders':len(doc['orders']),'skus':len(doc['skus']),
            'download_url':settings.origin+'/api/benchmarks/'+bid}

    @app.get('/api/benchmarks/{bid}/orders')
    def order_page(bid:str,offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100)):
        doc=store.benchmark(bid);ids=sorted(doc['orders']);page=ids[offset:offset+limit]
        return {'orders':[{'order_id':oid,'boxes':len(doc['orders'][oid]['instances'])} for oid in page],
                'next_offset':offset+limit if offset+limit<len(ids) else None,'total':len(ids)}

    @app.get('/api/benchmarks/{bid}/orders/{oid}')
    def order_document(bid:str,oid:str):
        doc=store.benchmark(bid)
        if oid not in doc['orders']:
            raise Problem(404,'Order not found.')
        order=doc['orders'][oid]
        return {'benchmark_id':bid,'order_id':oid,'container':doc['container'],**order,
                'skus':{it['sku_id']:doc['skus'][it['sku_id']] for it in order['items']}}

    @app.get('/api/schema/pack')
    def schema():
        return Pack.model_json_schema()

    @app.get('/api/mine')
    def mine(request:Request):
        user=principal(request)
        return store.mine(user['id'])

    @app.post('/api/strategies',status_code=201)
    def strategy(request:Request,data:StrategyCreate):
        user=principal(request,'submit');store.limit('write:'+user['id'])
        return store.create_strategy(user['id'],data)

    @app.post('/api/strategies/{sid}/revisions',status_code=201)
    def revision_create(request:Request,sid:str,data:RevisionCreate):
        user=principal(request,'submit');store.limit('write:'+user['id'])
        return store.create_revision(user['id'],sid,data)

    @app.get('/api/revisions/{rid}')
    def revision(request:Request,rid:str):
        user=optional_user(request)
        return store.revision(rid,user['id'] if user else None)

    @app.put('/api/revisions/{rid}/packs')
    def upload(request:Request,rid:str,data:Batch):
        user=principal(request,'submit');store.limit('write:'+user['id'])
        return store.put_packs(user['id'],rid,data.packs)

    @app.post('/api/revisions/{rid}/publish')
    def publish(request:Request,rid:str):
        user=principal(request,'publish');store.limit('write:'+user['id'])
        return store.publish(user['id'],rid)

    @app.get('/api/revisions/{rid}/packs/{oid}')
    def download_pack(request:Request,rid:str,oid:str):
        user=optional_user(request)
        return store.artifact(rid,oid,user['id'] if user else None)

    @app.get('/api/revisions/{rid}/compare/{other}')
    def compare(request:Request,rid:str,other:str):
        user=optional_user(request);owner=user['id'] if user else None
        a,b=store.revision(rid,owner),store.revision(other,owner)
        if a['benchmark_id']!=b['benchmark_id']:
            raise Problem(422,'Compare revisions from the same benchmark.')
        common=sorted(oid for oid,r in a['reports'].items() if r['complete'] and b['reports'].get(oid,{}).get('complete'))
        return {'left':rid,'right':other,'matched_complete_orders':len(common),
                'left_lve':sum(a['reports'][o]['lve'] for o in common)/len(common) if common else None,
                'right_lve':sum(b['reports'][o]['lve'] for o in common)/len(common) if common else None,
                'changed_orders':sorted(o for o in a['reports'].keys()|b['reports'].keys()
                                        if a['reports'].get(o,{}).get('artifact_sha256')!=b['reports'].get(o,{}).get('artifact_sha256'))}

    def viewer_context(request,bid,rid):
        user=optional_user(request)
        revision=store.revision(rid,user['id'] if user else None)
        if revision['benchmark_id']!=bid:
            raise Problem(404,'Revision does not belong to this benchmark.')
        return store.benchmark(bid),revision,user

    @app.get('/viz')
    def viewer(request:Request,benchmark:str,revision:str):
        bench,rev,_=viewer_context(request,benchmark,revision)
        html=(ROOT/'viz/index.html').read_text(encoding='utf-8')
        prefix=json.dumps('/api/view/'+benchmark+'/'+revision).replace('<','\\u003c')
        html=html.replace('const API = "";',f'const API = {prefix};')
        label=json.dumps(rev['strategy_name']+' · revision '+str(rev['number'])).replace('<','\\u003c')
        html=html.replace('ep:"EP Hybrid"',f'ep:{label}')
        return HTMLResponse(html)

    @app.get('/api/view/{bid}/{rid}/viz-api/skus')
    def viewer_skus(request:Request,bid:str,rid:str):
        bench,_,_=viewer_context(request,bid,rid)
        return [dict(s,sku_id=k) for k,s in bench['skus'].items()]

    @app.get('/api/view/{bid}/{rid}/viz-api/orders')
    def viewer_orders(request:Request,bid:str,rid:str):
        bench,_,_=viewer_context(request,bid,rid)
        return [{'order_id':oid,'sku_count':len(o['items']),'total_boxes':len(o['instances'])} for oid,o in bench['orders'].items()]

    @app.get('/api/view/{bid}/{rid}/viz-api/orders/{oid}')
    def viewer_order(request:Request,bid:str,rid:str,oid:str):
        bench,_,_=viewer_context(request,bid,rid)
        if oid not in bench['orders']:
            raise Problem(404,'Order not found.')
        return {'order_id':oid,'items':bench['orders'][oid]['items']}

    @app.get('/api/view/{bid}/{rid}/viz-api/{method}/{oid}')
    def viewer_pack(request:Request,bid:str,rid:str,method:str,oid:str):
        bench,rev,user=viewer_context(request,bid,rid)
        if method!='ep-result' or oid not in rev['reports']:
            return {'available':False,'order_id':oid}
        pack=Pack.model_validate(store.artifact(rid,oid,user['id'] if user else None))
        boxes,_,_,_=materialize(bench,pack)
        return {'available':True,'pack':{'boxes':boxes,'container':bench['container']},'order_id':oid}

    app.mount('/viz-static',StaticFiles(directory=ROOT/'viz'),name='viewer-assets')
    app.mount('/assets',StaticFiles(directory=Path(__file__).parent/'static'),name='competition-assets')

    @app.get('/')
    def index():
        return FileResponse(Path(__file__).parent/'static/index.html')

    return app
