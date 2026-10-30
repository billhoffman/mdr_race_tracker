const {test}=require('node:test');
const assert=require('node:assert/strict');
const progress=require('../web/progress.js');
const course={route:{length_m:4000,coordinates:[[0,0],[.01,0],[.02,0],[.03,0],[.04,0]],distance_m:[0,1000,2000,3000,4000]},checkpoints:[{id:'A',distance_m:1000},{id:'B',distance_m:2000},{id:'C',distance_m:3000}]};
const start='2026-10-31T08:00:00Z',stamp=seconds=>new Date(Date.parse(start)+seconds*1000).toISOString();
function runner(bib='1',station='A',seconds=1000,status='on_course'){
 const distance={START:0,A:1000,B:2000,C:3000,FINISH:4000}[station];
 return {bib,name:'Runner '+bib,status,distance_m:distance,position:{station,time:stamp(seconds)},reports:[{kind:'PASS',station,time:stamp(seconds)}]};
}
function state(runners,bounds=[]){return {race:{start_time:start},runners,progress_boundaries:bounds}}
function estimates(s,seconds){return progress.estimate(progress.prepare(s,course),Date.parse(stamp(seconds))/1000)}
test('estimates move between reports without changing the input snapshot',()=>{
 const s=state([runner()]),copy=JSON.stringify(s);
 const first=estimates(s,1100)[0],next=estimates(s,1200)[0];
 assert.equal(first.distance_m,1100);assert.equal(next.distance_m,1200);
 assert.deepEqual(next.coordinates,[.012,0]);assert.equal(JSON.stringify(s),copy);
});
test('a second confirmed station supplies personal segment pace',()=>{
 const r=runner('1','B',1500);r.reports.unshift({kind:'PASS',station:'A',time:stamp(1000)});
 const e=estimates(state([r]),1600)[0];assert.equal(e.distance_m,2200);assert.equal(e.speed_basis,'individual');
});
test('field pace is used for a runner without two individual checkpoints',()=>{
 const r=runner('1','B',1500);r.reports.unshift({kind:'PASS',station:'A',time:stamp(1000)});
 const e=estimates(state([r,runner('2','START',0)]),1000).find(e=>e.bib==='2');
 assert.equal(e.speed_basis,'field');assert.ok(e.distance_m>0&&e.distance_m<1000);
});
test('no report never becomes an inferred starter',()=>{
 const r={...runner(),status:'not_reported',position:null,reports:[],distance_m:null};
 assert.deepEqual(estimates(state([r],[{kind:'CLEARANCE',station:'B',time:stamp(1000)}]),2000),[]);
});
test('DNS withdrawn and finished runners never receive estimated movement',()=>{
 for(const status of ['dns','withdrawn','finished'])assert.deepEqual(estimates(state([runner('1','A',1000,status)]),2000),[]);
});
test('estimates cap before the next checkpoint and never infer a finish',()=>{
 const e=estimates(state([runner()]),10000)[0];assert.equal(e.distance_m,1950);assert.equal(e.capped,true);
 const end=estimates(state([runner('1','C',3000)]),10000)[0];assert.ok(end.distance_m<4000);
});
test('dots fade and change color as time since the last real report increases',()=>{
 const s=state([runner()]),fresh=estimates(s,1010)[0],old=estimates(s,10000)[0];
 assert.ok(old.uncertainty>fresh.uncertainty);assert.ok(old.opacity<fresh.opacity);assert.notEqual(old.color,fresh.color);
});
test('explicit all-passed evidence advances an estimate but not its confirmed anchor',()=>{
 const s=state([runner()],[{kind:'CLEARANCE',station:'B',time:stamp(1600)}]);
 const e=estimates(s,1700)[0];assert.equal(e.distance_m,2100);assert.equal(e.confirmed_distance_m,1000);assert.equal(e.inferred,true);assert.equal(e.boundary.station,'B');
});
test('a newer contradictory individual report overrides an older all-passed inference',()=>{
 const s=state([runner('1','A',1700)],[{kind:'CLEARANCE',station:'B',time:stamp(1600)}]);
 const e=estimates(s,1800)[0];assert.ok(e.distance_m<2000);assert.equal(e.inferred,false);
});
test('future clearance cannot move anyone early and last-runner evidence is weaker',()=>{
 for(const kind of ['CLEARANCE','LAST_RUNNER']){
  const s=state([runner()],[{kind,station:'B',time:stamp(2000)}]);assert.ok(estimates(s,1500)[0].distance_m<2000);
 }
 const s=state([runner()],[{kind:'LAST_RUNNER',station:'B',time:stamp(1100)}]);assert.equal(estimates(s,1200)[0].inferred,false);
});
test('a first-runner time cannot put estimates beyond that checkpoint before it happened',()=>{
 const s=state([runner()],[{kind:'LEADER',station:'B',time:stamp(2500)}]);assert.ok(estimates(s,2400)[0].distance_m<2000);
});
test('race start correction is used and no estimates appear before the start',()=>{
 const s=state([runner()]);assert.deepEqual(estimates(s,-1),[]);
 const a=estimates(s,1200)[0];s.race.start_time=stamp(100);const b=estimates(s,1200)[0];assert.ok(b.distance_m>a.distance_m);
});
test('sweeper GPS never establishes a clearance floor',()=>{
 const s=state([runner()]);s.sweeper={position:{distance_m:3000}};assert.ok(estimates(s,1500)[0].distance_m<2000);
});
test('a future-dated checkpoint does not start estimated movement early',()=>{
 assert.deepEqual(estimates(state([runner('1','A',2000)]),1500),[]);
});
