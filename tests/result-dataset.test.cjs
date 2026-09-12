const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {EXPERIMENT, CLUSTER_EXPERIMENT, fromSearch} = require('../viz/result-dataset.js');

test('cluster revision only exposes its own EP data, never a borrowed teacher', () => {
  const d=fromSearch('?dataset='+CLUSTER_EXPERIMENT);
  assert.equal(d.epOnly,true); assert.equal(d.valid,true);
  assert.equal(d.resultUrl('ep','ORD-08511033'),`/viz-api/experiments/${CLUSTER_EXPERIMENT}/ep-result/ORD-08511033`);
  for(const method of ['packed','remainder','neat','rl','rr']) assert.equal(d.resultUrl(method,'ORD-08511033'),null);
  const M=require('../viz/order-panel.js');
  assert.deepEqual(M.revisionMethods({dataset:CLUSTER_EXPERIMENT}).map(m=>m.key),['ep','schematic']);
});

test('published views keep their existing endpoints and labels', () => {
  const d = fromSearch('?order=ORD-08511033');
  assert.equal(d.valid, true); assert.equal(d.experimental, false);
  assert.equal(d.api, '/viz-api'); assert.equal(d.labels.packed, 'Phase 1+2');
  for (const [key, route] of Object.entries({packed:'result',ep:'ep-result',neat:'neat-result',rl:'rl-result',rr:'rr-result'})) {
    assert.equal(d.resultUrl(key, 'ORD-08511033'), `/viz-api/${route}/ORD-08511033`);
  }
});
test('experimental teacher and EP stay isolated from historical methods', () => {
  const d = fromSearch('?dataset=' + EXPERIMENT);
  assert.equal(d.valid, true); assert.equal(d.experimental, true);
  assert.equal(d.resultUrl('packed','ORD-08511033'), `/viz-api/experiments/${EXPERIMENT}/result/ORD-08511033`);
  assert.equal(d.resultUrl('ep','ORD-08511033'), `/viz-api/experiments/${EXPERIMENT}/ep-result/ORD-08511033`);
  for (const key of ['neat','rl','rr']) assert.equal(d.resultUrl(key,'ORD-08511033'), null);
  assert.equal(d.labels.packed, 'P1+2 teacher audit');
  assert.equal(d.labels.ep, 'EP Sep 10 experiment');
});
test('unknown datasets never silently select historical results', () => {
  const d = fromSearch('?dataset=other');
  assert.equal(d.valid, false);
  assert.throws(() => d.resultUrl('ep','ORD-08511033'));
});
test('switching libraries preserves the selected order and uses same-origin URLs', () => {
  const pub = fromSearch('');
  const exp = fromSearch('?dataset=' + EXPERIMENT);
  assert.equal(new URL(pub.switchUrl('ORD-08511033'), 'https://test').searchParams.get('dataset'), EXPERIMENT);
  assert.equal(new URL(exp.switchUrl('ORD-08511033'), 'https://test').searchParams.get('order'), 'ORD-08511033');
  assert.equal(new URL(exp.switchUrl('ORD-08511033'), 'https://test').searchParams.get('dataset'), null);
  assert.ok(pub.resultUrl('ep', '../inputs').endsWith('..%2Finputs'));
});
test('viewer keeps datasets separate without adding a second browsing workflow', () => {
  const html = readFileSync(join(__dirname,'../viz/index.html'),'utf8');
  assert.ok(html.includes('DATASET.valid && !DATASET.experimental'));
  assert.ok(html.includes('DATASET.resultUrl(method, orderId)'));
  assert.ok(html.includes('Suite code revision'));
  assert.ok(html.includes('not a shared foundation and completion'));
  assert.ok(!readFileSync(join(__dirname,'../serve.py'),'utf8').includes('Browse Sep 10 results'));
  assert.ok(!html.includes('id="datasetLink"'));
  // Parse every inline script, including the viewer, without needing WebGL.
  for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new Function(match[1]);
});
