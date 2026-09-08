const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const M = require('../viz/order-panel.js');
const catalog=[{sku_id:'a',name:'A',length:.2,width:.1,height:.1,weight:2},
  {sku_id:'b',name:'B',length:.3,width:.2,height:.1,weight:1}];
const order=M.orderSummary([{sku_id:'a',quantity:2},{sku_id:'b',quantity:1}],catalog);
const box=(id,sku='a')=>({id,sku_id:sku,weight:sku==='a'?2:1,
  dimensions:{width:.2,depth:.1,height:.1},position:{x:.1,y:.05,z:.05}});
const pack=(boxes,stats={})=>({container:{width:.4,depth:.2,height:1},boxes,stats});
test('metric order totals and line quantities are recomputed from catalogue',()=>{
  assert.equal(order.items,3);assert.equal(order.skus,2);assert.equal(order.weight,5);
  assert.ok(Math.abs(order.volume-.010)<1e-12);
  assert.equal(order.rows[0].lineWeight,4);
  assert.ok(Math.abs(order.rows[1].lineVolume-.006)<1e-12);
});
test('missing SKU data is unknown, never a misleading zero',()=>{
  const o=M.orderSummary([{sku_id:'missing',quantity:4}],catalog);
  assert.equal(o.items,4);assert.equal(o.weight,null);assert.equal(o.volume,null);assert.equal(o.missing,1);
});
test('zero is a real total for an empty order, but cannot certify completion',()=>{
  const o=M.orderSummary([],catalog);assert.equal(o.weight,0);assert.equal(o.volume,0);
  const s=M.packStats(pack([]),o);assert.equal(s.complete,false);assert.equal(s.lve,null);
});
test('duplicate order lines contribute quantity but not additional unique SKUs',()=>{
  const o=M.orderSummary([{sku_id:'a',quantity:2},{sku_id:'a',quantity:3}],catalog);
  assert.equal(o.items,5);assert.equal(o.skus,1);assert.equal(o.weight,10);
});
test('invalid quantities are rejected',()=>{
  for(const quantity of [-1,NaN,1.5,'2']) assert.throws(()=>M.orderSummary([{sku_id:'a',quantity}],catalog));
});
test('actual boxes override stale producer counters',()=>{
  const s=M.packStats(pack([box(1)],{placed:99,total:88}),order);
  assert.equal(s.placed,1);assert.equal(s.remaining,2);assert.equal(s.complete,false);assert.equal(s.warnings.length,2);
});
test('duplicate box IDs cannot count as a complete pack',()=>{
  const s=M.packStats(pack([box(1),box(1),box(3,'b')]),order);
  assert.equal(s.complete,false);assert.equal(s.identityValid,false);
  assert.equal(s.remaining,null);
});
test('extra SKU quantities cannot count as a complete pack',()=>{
  assert.equal(M.packStats(pack([box(1),box(2),box(3)]),order).complete,false);
});
test('LVE uses the reported pallet footprint and actual stack height, not ceiling',()=>{
  const s=M.packStats(pack([box(1)]),order);assert.ok(Math.abs(s.lve-4)<1e-10);assert.equal(s.top,.1);
});
test('unknown geometry yields unavailable metrics instead of NaN',()=>{
  const b=box(1);delete b.dimensions.height;
  const s=M.packStats(pack([b]),order);assert.equal(s.volume,null);assert.equal(s.top,null);assert.equal(s.lve,null);
});
test('all seven views have distinct keys and the reranker is retained',()=>{
  assert.equal(M.METHODS.length,7);assert.equal(new Set(M.METHODS.map(m=>m.key)).size,7);
  assert.equal(M.METHODS.find(m=>m.key==='rr').endpoint,'rr-result');
});
test('real published artifacts count geometry without requiring stats metadata',()=>{
  const root=join(__dirname,'..');
  const foundation=JSON.parse(readFileSync(join(root,'results/ORD-19412545.placed.json')));
  const remainder=JSON.parse(readFileSync(join(root,'results/ORD-19412545.remainder.json')));
  const all=[...foundation.boxes,...remainder.boxes], skus=new Map(), quantities=new Map();
  for(const b of all){const d=b.dimensions;skus.set(b.sku_id,{sku_id:b.sku_id,length:d.width,width:d.depth,height:d.height,weight:b.weight});quantities.set(b.sku_id,(quantities.get(b.sku_id)||0)+1);}
  const o=M.orderSummary([...quantities].map(([sku_id,quantity])=>({sku_id,quantity})),[...skus.values()]);
  for(const dir of ['results_ep','results_neat','results_rl','results_rl_reranker']){
    const pf=JSON.parse(readFileSync(join(root,dir,'ORD-19412545.packformation.json')));
    const s=M.packStats(pf,o);assert.equal(s.placed,pf.boxes.length);assert.ok(Number.isFinite(s.lve));
    assert.equal(s.identityValid,true);assert.ok(s.placed<=o.items);
  }
});
