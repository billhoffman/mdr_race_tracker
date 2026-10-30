/* Exercise the real app against a small DOM surface, including timer redraws. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const geometry=require('../web/course-geometry.js'),progress=require('../web/progress.js');
class Element{
 constructor(){this.children=[];this.attributes={};this.listeners={};this.style={};this.textContent='';this.value='';this.hidden=false;this.parent=null;this.classList={toggle(){},add(){}}}
 append(...nodes){for(const n of nodes){if(n.parent)n.remove();this.children.push(n);n.parent=this}}
 replaceChildren(...nodes){for(const n of this.children)n.parent=null;this.children=[];this.append(...nodes)}
 setAttribute(k,v){this.attributes[k]=String(v)}getAttribute(k){return this.attributes[k]}
 addEventListener(k,fn){(this.listeners[k]??=[]).push(fn)}remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);this.parent=null}
}
async function app(){
 const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8'),html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
 const nodes=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
 const selectors=new Map(['footer','aside','.review','details','.layout'].map(k=>[k,new Element()]));
 const course={route:{length_m:3000,coordinates:[[-73,43,100],[-72.99,43,200],[-72.98,43,150],[-72.97,43,100]],distance_m:[0,1000,2000,3000]},checkpoints:[{id:'A',coordinates:[-72.99,43],distance_m:1000},{id:'B',coordinates:[-72.98,43],distance_m:2000}]};
 const runner={bib:'101',name:'Alex Demo',status:'on_course',place:null,elapsed_seconds:null,distance_m:1000,last:{station:'A',time:'2026-10-31T09:10:00Z'},position:{station:'A',time:'2026-10-31T09:10:00Z'},reports:[{kind:'PASS',station:'A',time:'2026-10-31T09:10:00Z'}]};
 const snapshot={race:{name:'Demo',test_mode:true,start_time:'2026-10-31T09:00:00Z',clock:'2026-10-31T09:15:00Z',clock_mode:'live',elapsed_seconds:900,timezone:'UTC'},runners:[runner],counts:{on_course:1,finished:0,withdrawn:0,dns:0},source:{mode:'file',last_success:'2026-10-31T09:15:00Z'},revision:1,history:[],issues:[],anomalies:[],sweeper:{enabled:false},progress_boundaries:[]};
 const original=JSON.stringify(snapshot),timers=[];let now=1000;
 const box={window:{CourseGeometry:geometry,RaceProgress:progress},URLSearchParams,performance:{now:()=>now},setTimeout:()=>{},setInterval:fn=>timers.push(fn),fetch:async url=>({ok:true,json:async()=>url==='/api/state'?snapshot:course}),document:{getElementById:id=>nodes.get(id),querySelector:selector=>selectors.get(selector),createElement:()=>new Element(),createElementNS:()=>new Element(),createTextNode:text=>Object.assign(new Element(),{textContent:text})}};
 vm.createContext(box);await vm.runInContext(source,box);
 return {box,nodes,snapshot,original,advance:seconds=>{now+=seconds*1000;timers[0]()},read:expression=>vm.runInContext(expression,box)};
}
test('real app draws labelled estimates, keeps confirmed counts and moves on its clock',async()=>{
 const a=await app();assert.equal(a.read('mapCache.estimateMarkers.size'),1);
 assert.match(a.nodes.get('estimate-note').textContent,/ESTIMATED PROGRESS/);
 const before=a.read('mapCache.estimateMarkers.get("101").g.getAttribute("transform")');a.advance(10);
 assert.notEqual(a.read('mapCache.estimateMarkers.get("101").g.getAttribute("transform")'),before);
 assert.match(a.read('mapCache.estimateMarkers.get("101").title.textContent'),/Last confirmed A/);
 assert.equal(JSON.stringify(a.snapshot),a.original);
});
test('confirmed-only toggle hides estimates and selection exposes the real anchor',async()=>{
 const a=await app();a.nodes.get('confirmed-view').listeners.click[0]();
 assert.equal(a.read('mapCache.estimates.getAttribute("display")'),'none');
 assert.match(a.nodes.get('estimate-note').textContent,/CONFIRMED CHECKPOINTS/);
 a.nodes.get('estimated-view').listeners.click[0]();
 a.read('mapCache.estimateMarkers.get("101").g.listeners.click[0]()');
 assert.match(a.nodes.get('estimate-detail').textContent,/Last confirmed A/);
});
