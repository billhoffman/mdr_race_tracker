// Optional frontend unit checks; Node is not needed to run the Python publisher.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
const functions=source.slice(0,source.indexOf('function svg('));
function clock(race,age=0){
 const output={textContent:''};
 const sandbox={window:{},document:{getElementById:()=>output},performance:{now:()=>5000}};
 vm.runInNewContext(functions+'\nstate='+JSON.stringify({race})+';clockReceived=4000;clockAge='+age+';tickClock();',sandbox);
 return output.textContent;
}
test('live clock includes the age of a published snapshot and ticks between updates',()=>{
 assert.equal(clock({clock_mode:'live',clock:'2026-10-31T09:10:00-04:00',start_time:'2026-10-31T09:00:00-04:00'},60),'00:11:01');
});
test('fictional report clock stays at the latest report time',()=>{
 assert.equal(clock({clock_mode:'latest_report',elapsed_seconds:600},90),'00:10:00');
});
test('live clock stays at zero before the race start',()=>{
 assert.equal(clock({clock_mode:'live',clock:'2026-10-31T08:30:00-04:00',start_time:'2026-10-31T09:00:00-04:00'},60),'00:00:00');
});
test('a withdrawal with unknown location keeps its last confirmed marker',()=>{
 const sandbox={window:{},performance:{now:()=>0},result:null};
 const prefix=source.slice(0,source.indexOf('function countMarker('));
 vm.runInNewContext(prefix+'\nstate={runners:[{bib:"101",last:{station:null},position:{station:"B"}},{bib:"102",last:{station:null},position:null}]};result=JSON.stringify(runnerGroups());',sandbox);
 const groups=JSON.parse(sandbox.result);
 assert.deepEqual(Object.keys(groups),['B']);
 assert.equal(groups.B[0].bib,'101');
});
test('a failed director source remains visible when radio reads succeed',()=>{
 const sandbox={window:{},performance:{now:()=>0},result:null};
 const prefix=source.slice(0,source.indexOf('function svg('));
 vm.runInNewContext(prefix+'\nresult=sourceStatus({mode:"google",last_success:"2026-10-31T10:00:00Z",director:{last_success:"2026-10-31T10:00:00Z",error:"Director update failed"}},Date.parse("2026-10-31T10:00:10Z"));',sandbox);
 assert.equal(sandbox.result.error,true);
 assert.match(sandbox.result.text,/Radio log connected/);
 assert.match(sandbox.result.text,/RD log: Director update failed/);
});
