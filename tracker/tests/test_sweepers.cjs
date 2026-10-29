const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
function status(sweeper){const box={window:{},performance:{now:()=>0},result:null};vm.runInNewContext(source.slice(0,source.indexOf('function svg('))+'\nresult=sweeperStatus('+JSON.stringify(sweeper)+',Date.parse("2026-10-31T14:00:00Z"));',box);return box.result}
test('broom waits for a race-day GPS report',()=>{assert.equal(status({enabled:true}).showMarker,false);assert.match(status({enabled:true}).text,/Waiting for a race-day/)});
test('old GPS stays visible but faded and labelled outdated',()=>{const s=status({enabled:true,position:{time:'2026-10-31T13:00:00Z',distance_m:1609.344}});assert.equal(s.stale,true);assert.equal(s.showMarker,true);assert.match(s.text,/60 min ago/);assert.match(s.text,/outdated/)});
test('a fresh point uses its report age, not its latest fetch age',()=>{const s=status({enabled:true,last_success:'2026-10-31T14:00:00Z',position:{time:'2026-10-31T13:55:00Z',distance_m:1609.344}});assert.equal(s.stale,false);assert.match(s.text,/5 min ago/)});
test('off-course and ambiguous positions do not invent course progress',()=>{assert.equal(status({enabled:true,off_course:true}).showMarker,false);assert.match(status({enabled:true,position:{time:'2026-10-31T13:55:00Z',distance_m:null}}).text,/distance uncertain/)});
test('disabled tracking does not draw a broom',()=>{assert.equal(status({enabled:false}).visible,false)});
