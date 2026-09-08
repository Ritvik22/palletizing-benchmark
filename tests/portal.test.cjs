'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function harness(){
 const elements=new Map(),requests=[];
 const element=()=>({children:[],attributes:{},hidden:false,
  append(...children){this.children.push(...children);},
  replaceChildren(...children){this.children=children;},
  setAttribute(name,value){this.attributes[name]=value;}});
 const document={getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},
  querySelectorAll(){return [];},createElement:element};
 const context=vm.createContext({document,fetch(url){
  // Leave startup account requests pending; exercise the real leaderboard function.
  return new Promise((resolve,reject)=>requests.push({url,resolve,reject}));
 }});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../competition/static/portal.js'),'utf8'),context);
 const select=id=>vm.runInContext('state.benchmark={id:'+JSON.stringify(id)+'};leaderboard()',context);
 const reply=(id,rows)=>requests.find(r=>r.url==='/api/benchmarks/'+id+'/leaderboard').resolve({ok:true,json:async()=>rows});
 return {elements,requests,select,reply};
}
const entry={rank:1,name:'Current strategy',display_name:'Researcher',number:1,published:'2026-09-08T12:00:00Z',id:'revision',
 summary:{orders_complete:2,orders_expected:2,orders_missing:0,orders_invalid:0,lve_complete_mean:1.5,lve_n:2}};

test('late previous benchmark response cannot clear the current leaderboard',async()=>{
 const h=harness(),old=h.select('full'),latest=h.select('preview');
 h.reply('preview',[entry]);await latest;
 h.reply('full',[]);await old;
 assert.equal(h.elements.get('leaderboard').children.length,1);
 assert.equal(h.elements.get('empty-results').hidden,true);
 assert.equal(h.elements.get('leaderboard').attributes['aria-busy'],'false');
});

test('stale errors are ignored but current request errors remain visible',async()=>{
 const h=harness(),old=h.select('full'),latest=h.select('preview');
 h.requests.find(r=>r.url.endsWith('/full/leaderboard')).reject(new Error('Old request failed'));
 await old;
 assert.equal(h.elements.get('leaderboard').attributes['aria-busy'],'true');
 h.requests.find(r=>r.url.endsWith('/preview/leaderboard')).reject(new Error('Current request failed'));
 await assert.rejects(latest,/Current request failed/);
 assert.equal(h.elements.get('leaderboard').attributes['aria-busy'],'false');
});
