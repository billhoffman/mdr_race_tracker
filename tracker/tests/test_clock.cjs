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
