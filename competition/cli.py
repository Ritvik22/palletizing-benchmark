"""Explicit operator commands; startup never changes datasets or creates users."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sqlite3

from .config import ROOT, Settings
from .evaluator import VERSION
from .models import Dimensions, Pack, RevisionCreate, StrategyCreate
from .store import Store


def import_dataset(store,source,bid,name,order_ids=None,license_name='Not specified',stacking_rule='none'):
    source=Path(source).resolve()
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        skus={s['sku_id']:dict(s) for s in db.execute('SELECT sku_id,name,length,width,height,weight FROM skus')}
        lines=db.execute('SELECT order_id,sku_id,quantity FROM order_items ORDER BY order_id,sku_id').fetchall()
    for s in skus.values():
        for k in ('length','width','height','weight'):
            if not isinstance(s[k],(int,float)) or not math.isfinite(s[k]) or s[k]<=0:
                raise ValueError('Invalid SKU '+s['sku_id'])
    mean_weight=sum(s['weight'] for s in skus.values())/len(skus)
    for s in skus.values():
        s['stack_class']='heavy' if s['weight']>=mean_weight else 'light'
    orders={}
    for row in lines:
        oid,sku,quantity=row['order_id'],row['sku_id'],row['quantity']
        if order_ids and oid not in order_ids:
            continue
        if sku not in skus or not isinstance(quantity,int) or quantity<=0:
            raise ValueError('Invalid order item '+oid)
        order=orders.setdefault(oid,{'items':[],'instances':[]})
        prior=sum(it['quantity'] for it in order['items'] if it['sku_id']==sku)
        order['items'].append({'sku_id':sku,'quantity':quantity})
        order['instances'].extend({'id':f'{sku}:{i:04d}','sku_id':sku} for i in range(prior,prior+quantity))
    if order_ids and set(orders)!=set(order_ids):
        raise ValueError('Requested preview orders are missing.')
    if any(len(o['instances'])>1000 for o in orders.values()):
        raise ValueError('Orders over 1000 boxes require a separate capacity track.')
    doc={'schema_version':1,'id':bid,'name':name,'evaluator_version':VERSION,
         'license':license_name,'source':'Synthetic dataset shipped with palletizing-benchmark',
         'container':Dimensions(width=.8,depth=1.2,height=2.).model_dump(),'skus':skus,'orders':orders,
         'stacking_rule':stacking_rule,'weight_class_threshold_kg':mean_weight,
         'weight_class_note':'Unweighted mean across SKU master; proxy only, not measured crush strength.',
         'rules':{'coordinates':'centres in metres, x/y horizontal, z up','mass':'kg from immutable SKU master',
                  'rotations':[0,90],'tolerance_m':1e-6,'completion':'all canonical box IDs valid and statically balanced',
                  'ranking':'full benchmark completion required; mean LVE ascending',
                  'stability':'nonnegative vertical contact reactions and per-box force/moment equilibrium',
                  'not_modelled':['friction','dynamic tipping','box deformation','robot reachability','placement sequence']}}
    store.add_benchmark(doc)
    return doc


def convert_legacy(benchmark,oid,artifact):
    """Conversion refuses altered dimensions/mass instead of silently correcting them."""
    counters=Counter();boxes=[];seen=set()
    for b in artifact['boxes']:
        if str(b['id']) in seen:
            raise ValueError('Duplicate legacy box ID')
        seen.add(str(b['id']))
        sku=b['sku_id'];s=benchmark['skus'][sku];d=b['dimensions']
        if abs(b['weight']-s['weight'])>1e-6 or abs(d['height']-s['height'])>1e-6:
            raise ValueError('Legacy mass/height mismatch')
        if abs(d['width']-s['length'])<1e-6 and abs(d['depth']-s['width'])<1e-6:
            rotation=0
        elif abs(d['width']-s['width'])<1e-6 and abs(d['depth']-s['length'])<1e-6:
            rotation=90
        else:
            raise ValueError('Legacy dimensions mismatch')
        boxes.append({'id':f'{sku}:{counters[sku]:04d}','sku_id':sku,'position':b['position'],'rotation':rotation})
        counters[sku]+=1
    return Pack.model_validate({'order_id':oid,'boxes':boxes})


def seed_baselines(store,benchmark,root=ROOT):
    user=store.user('system','published-baselines','Published baseline artifacts','')
    for directory,label in [('results_ep','EP published baseline'),('results_neat','NEAT published baseline'),
                             ('results_rl','RL published baseline'),('results_rl_reranker','RL + ReRanker published baseline')]:
        if any(s['name']==label for s in store.mine(user['id'])):
            continue
        artifacts=[]
        for oid in benchmark['orders']:
            path=root/directory/(oid+'.packformation.json')
            if path.exists():
                artifacts.append(convert_legacy(benchmark,oid,json.loads(path.read_text())))
        if not artifacts:
            continue
        sid=store.create_strategy(user['id'],StrategyCreate(name=label,description='Previously published geometry, revalidated by this competition evaluator. Not evidence of a current trained model.'))['id']
        rid=store.create_revision(user['id'],sid,RevisionCreate(benchmark_id=benchmark['id'],
            notes='Imported from '+directory+'. Canonical IDs assigned per SKU; sizes and weights checked against the frozen dataset. Unavailable orders remain missing.',
            code_revision='Original generating code revision not recorded',model_revision='Original checkpoint not recorded',
            config={'artifact_source':directory,'converted_ids':True}))['id']
        for start in range(0,len(artifacts),25):
            store.put_packs(user['id'],rid,artifacts[start:start+25])
        store.publish(user['id'],rid)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('import-dataset')
    p.add_argument('--source',default=str(ROOT/'backend/palletizer.db'))
    p.add_argument('--id',default='synthetic-1000-v1');p.add_argument('--name',default='Synthetic packing benchmark · v1')
    p.add_argument('--license',default='Not specified');p.add_argument('--preview',action='store_true')
    p.add_argument('--stacking-rule',choices=['none','heavy-not-on-light'],default='none')
    p=commands.add_parser('import-baselines');p.add_argument('benchmark_id')
    commands.add_parser('serve')
    args=parser.parse_args();settings=Settings.from_env();store=Store(settings.database)
    if args.command=='import-dataset':
        doc=import_dataset(store,args.source,args.id,args.name,
                           {'ORD-19412545','ORD-00178905'} if args.preview else None,args.license,args.stacking_rule)
        print('Imported',doc['id'],'with',len(doc['orders']),'orders.')
    elif args.command=='import-baselines':
        seed_baselines(store,store.benchmark(args.benchmark_id));print('Available baseline artifacts imported and evaluated.')
    else:
        import uvicorn
        from urllib.parse import urlparse
        from .app import create_app
        parsed=urlparse(settings.origin)
        # Production reverse proxy owns TLS; explicitly choose bind host in deployment.
        import os
        bind_host=os.getenv('BIND_HOST','127.0.0.1')
        if settings.local_admin_login and bind_host not in ('127.0.0.1','localhost','::1'):
            raise ValueError('Local admin preview must bind to a loopback address.')
        uvicorn.run(create_app(settings),host=bind_host,port=int(os.getenv('PORT',parsed.port or 8769)),
                    access_log=False,proxy_headers=not settings.local_admin_login)


if __name__=='__main__':
    main()
