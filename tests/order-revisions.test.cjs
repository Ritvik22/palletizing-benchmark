'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const D = require('../viz/result-dataset.js');
const M = require('../viz/order-panel.js');
const latest = {id:D.EXPERIMENT, dataset:D.EXPERIMENT, date:'2026-09-11T06:25:31Z', label:'Sep 10–11 audit', note:'Separate runs'};
const older = {id:'published', dataset:null, date:'2026-09-04T12:00:00Z', label:'Published results'};
const oid = 'ORD-19412545';

test('revision dates are sorted newest first without mutating the API list', () => {
  const original = [older, latest];
  assert.equal(M.revisionsNewestFirst(original)[0], latest);
  assert.equal(original[0], older);
  assert.equal(M.revisionsNewestFirst([{id:'unknown',date:null},older])[0], older);
});
test('each embedded pack keeps the selected order, method and date', () => {
  for (const revision of [latest, older]) {
    const url = new URL(M.viewerUrl(revision,oid,'ep'), 'https://example.test');
    assert.equal(url.pathname, '/viz');
    assert.equal(url.searchParams.get('order'), oid);
    assert.equal(url.searchParams.get('embed'), '1');
    assert.equal(url.searchParams.get('view'), 'ep');
    assert.equal(url.searchParams.get('dataset'), revision.dataset);
  }
  assert.throws(() => M.viewerUrl({dataset:'unrecognized'}, oid, 'ep'));
});
test('the teacher is never labeled as the EP foundation', () => {
  const methods = M.revisionMethods(latest);
  assert.equal(methods.find(m=>m.key==='packed').label, 'P1+2 teacher audit');
  assert.match(methods.find(m=>m.key==='remainder').description, /Not an EP remainder/);
  assert.equal(M.revisionMethods(older), M.METHODS);
});

// Small DOM harness runs the real popup code, including requests, selectors,
// iframe URLs and out-of-order completions. No browser/React dependency needed.
function harness() {
  class Element {
    constructor(tag) { this.tag=tag; this.children=[]; this.attributes={}; this.dataset={}; this.listeners={}; this.hidden=false; this.disabled=false; this.isConnected=true; this.text='';
      if(tag==='iframe') this.contentWindow={postMessage(){}};
    }
    append(...nodes) { nodes.forEach(n=>{n.parent=this;this.children.push(n);}); }
    prepend(...nodes) { nodes.forEach(n=>{n.parent=this;});this.children.unshift(...nodes); }
    replaceChildren(...nodes) { this.children=[];this.text='';this.append(...nodes); }
    set textContent(text) { this.text=String(text);this.children=[]; }
    get textContent() { return this.text + this.children.map(c=>c.textContent).join(' '); }
    setAttribute(k,v) { this.attributes[k]=String(v); }
    getAttribute(k) { return this.attributes[k] ?? null; }
    set src(v) { this.setAttribute('src',v); }
    get src() { return this.getAttribute('src'); }
    remove() { if(this.parent) this.parent.children=this.parent.children.filter(n=>n!==this);this.isConnected=false; }
    addEventListener(k,f) { this.listeners[k]=f; }
    matches(selector) {
      if(selector.startsWith('.')) return (this.className||'').split(' ').includes(selector.slice(1));
      if(selector.startsWith('[data-key=')) return this.dataset.key === selector.match(/"([^"]+)"/)[1];
      return selector===this.tag;
    }
    querySelectorAll(selector) { return this.children.flatMap(c=>[...(c.matches(selector)?[c]:[]),...c.querySelectorAll(selector)]); }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  }
  const modal=new Element('div'),body=new Element('div'),title=new Element('div');
  body.className='modal-body'; title.className='modal-title'; modal.append(title,body);
  const requests=[],window={PalletResultDataset:D,addEventListener(){}};
  const context=vm.createContext({window,URLSearchParams,AbortController,location:{origin:'https://example.test'},
    document:{createElement:tag=>new Element(tag),querySelectorAll:()=>[modal]},
    fetch(url,options){return new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}));}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../viz/order-panel.js'),'utf8'),context);
  const respond=(request,data)=>request.resolve({ok:true,json:async()=>data});
  const tick=()=>new Promise(resolve=>setImmediate(resolve));
  function replyBatch(pending, n) {
    const boxes=Array.from({length:n},(_,id)=>({id,sku_id:'a',weight:1,position:{x:.1,y:.1,z:.05},dimensions:{width:.2,depth:.2,height:.1}}));
    const pack={container:{width:.8,depth:1.2,height:2},boxes};
    for(const r of pending) {
      if(r.url.endsWith('/skus')) respond(r,[{sku_id:'a',length:.2,width:.2,height:.1,weight:1}]);
      else if(r.url.endsWith('/orders/'+oid)) respond(r,{order_id:oid,items:[{sku_id:'a',quantity:3}]});
      else if(r.url.includes('/result/')) respond(r,{available:true,placed:pack,remainder:{...pack,boxes:[]}});
      else respond(r,{available:true,pack});
    }
  }
  async function ready() {
    const promise=window.PalletOrderPanel.attach(modal,oid);
    respond(requests[0],{order_id:oid,revisions:[older,latest]});
    await tick(); replyBatch(requests.slice(1),1); await promise;
  }
  const choose = revision => { const select=body.querySelector('select');select.value=revision.id;return select.onchange(); };
  return {modal,body,requests,ready,choose,replyBatch,tick};
}

test('opening an order defaults to its newest date inside the same popup', async () => {
  const h=harness();await h.ready();
  assert.equal(h.body.querySelector('select').value,latest.id);
  assert.match(h.body.querySelector('iframe').src, /dataset=baseline-library/);
  assert.match(h.body.textContent,/P1\+2 teacher audit/);
  assert.match(h.body.textContent,/Not in this run/);
  assert.equal(h.requests.filter(r=>/neat-result|rl-result|rr-result/.test(r.url)).length,0);
  assert.equal(h.body.querySelectorAll('iframe').length,1);
});
test('switching dates updates the frame and all results without navigating the order list', async () => {
  const h=harness();await h.ready();const start=h.requests.length;
  const done=h.choose(older);
  assert.equal(h.body.querySelector('iframe'),null); // No old geometry under the new date.
  h.replyBatch(h.requests.slice(start),2);await done;
  assert.equal(h.body.querySelector('select').value,'published');
  assert.ok(!h.body.querySelector('iframe').src.includes('dataset='));
  assert.match(h.body.textContent,/2 \/ 3 placed/);
  assert.ok(h.requests.slice(start).every(r=>!r.url.includes('/experiments/')));
  assert.equal(h.modal.dataset.orderPanel,oid);
});
test('late older-date responses cannot overwrite the date selected most recently', async () => {
  const h=harness();await h.ready();let start=h.requests.length;
  const old=h.choose(older), oldRequests=h.requests.slice(start);start=h.requests.length;
  const current=h.choose(latest);h.replyBatch(h.requests.slice(start),1);await current;
  h.replyBatch(oldRequests,3);await old;
  assert.equal(h.body.querySelector('select').value,latest.id);
  assert.match(h.body.querySelector('iframe').src,/dataset=baseline-library/);
  assert.match(h.body.textContent,/1 \/ 3 placed/);
  assert.ok(!h.body.textContent.includes('3 / 3 placed'));
});
test('a failed selected date never substitutes an older successful pack', async () => {
  const h=harness();await h.ready();const start=h.requests.length;
  const failed=h.choose(older);
  h.requests[start].reject(new Error('Offline'));
  // First requests are strategy-specific: fail order/catalog too so this is a
  // whole-revision load failure, not a single unavailable strategy.
  h.requests.find((r,i)=>i>=start && r.url.includes('/orders/')).reject(new Error('Offline'));
  await failed;
  assert.equal(h.body.querySelector('iframe'),null);
  assert.match(h.body.textContent,/No older pack has been substituted/);
  assert.equal(h.body.querySelector('select').value,'published');
});
