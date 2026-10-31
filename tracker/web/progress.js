/* Display-only estimation. Never writes observations, status or finishing places. */
(function(root){
 'use strict';
 const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
 function median(values){const s=[...values].sort((a,b)=>a-b);return s.length?(s[(s.length-1)>>1]+s[s.length>>1])/2:null}
 function prepare(state,course){
  const stations={START:0,FINISH:course.route.length_m};for(const c of course.checkpoints)stations[c.id]=c.distance_m;
  const checkpoints=[...new Set([0,...Object.values(stations)])].sort((a,b)=>a-b),start=Date.parse(state.race.start_time)/1000;
  const rows=[],field=[];
  for(const runner of state.runners){
   const reports=runner.reports.filter(r=>r.kind==='PASS'&&Number.isFinite(stations[r.station])).map(r=>({distance:stations[r.station],time:Date.parse(r.time)/1000})).sort((a,b)=>a.time-b.time);
   const speeds=[];for(let i=1;i<reports.length;i++){const d=reports[i].distance-reports[i-1].distance,t=reports[i].time-reports[i-1].time;if(d>=50&&t>=30&&d/t>=0.15&&d/t<=5)speeds.push(d/t)}
   const first=reports.find(r=>r.distance>0&&r.time>start);if(first){const speed=first.distance/(first.time-start);if(speed>=0.15&&speed<=5)field.push(speed)}
   field.push(...speeds);rows.push({runner,reports,speed:median(speeds.slice(-3))});
  }
  const fieldSpeed=median(field)||1.25;
  const bounds=(state.progress_boundaries||[]).filter(b=>Number.isFinite(stations[b.station])).map(b=>({...b,distance:stations[b.station],time:Date.parse(b.time)/1000}));
  const coordinates=course.route.coordinates;let distances=course.route.distance_m;
  if(!distances||distances.length!==coordinates.length){distances=[0];for(let i=1;i<coordinates.length;i++){const a=coordinates[i-1],b=coordinates[i],lat=(a[1]+b[1])*Math.PI/360;distances.push(distances.at(-1)+Math.hypot((b[0]-a[0])*111320*Math.cos(lat),(b[1]-a[1])*111320))}const factor=course.route.length_m/(distances.at(-1)||1);distances=distances.map(d=>d*factor)}
  function pointAt(distance){let lo=0,hi=distances.length-1;while(lo+1<hi){const mid=(lo+hi)>>1;if(distances[mid]<=distance)lo=mid;else hi=mid}const span=distances[hi]-distances[lo],t=span>0?clamp((distance-distances[lo])/span,0,1):0;return [coordinates[lo][0]+t*(coordinates[hi][0]-coordinates[lo][0]),coordinates[lo][1]+t*(coordinates[hi][1]-coordinates[lo][1])]}
  return {rows,stations,checkpoints,bounds,start,fieldSpeed,fieldAvailable:field.length>0,pointAt,length:course.route.length_m};
 }
 function estimate(model,now){
  const result=[];
  for(const row of model.rows){
   const runner=row.runner;
   const position=runner.position||(runner.started?{station:'START',time:new Date(model.start*1000).toISOString()}:null);
   const knownDistance=runner.distance_m??(runner.started?0:null);
   if(runner.status!=='on_course'||!position||!Number.isFinite(knownDistance)||now<model.start)continue;
   const confirmedDistance=knownDistance,confirmedTime=Date.parse(position.time)/1000;
   if(now<confirmedTime)continue;
   let distance=confirmedDistance,anchorTime=confirmedTime,boundary=null;
   // An all-passed report can infer progress for a known on-course runner. A
   // newer individual report behind it is contradictory and takes precedence.
   for(const b of model.bounds){if(b.kind==='CLEARANCE'&&b.time<=now&&b.time>=confirmedTime&&b.distance>distance){distance=b.distance;anchorTime=b.time;boundary=b}}
   const next=model.checkpoints.find(d=>d>distance+0.01);if(next===undefined)continue;
   const speed=row.speed||model.fieldSpeed,age=Math.max(0,now-anchorTime),leg=next-distance;
   // Stop 5% short of an unconfirmed checkpoint, including FINISH.
   let cap=Math.max(distance,next-Math.max(1,leg*0.05));
   // A future first-runner timestamp cannot support estimates past that station.
   for(const b of model.bounds)if(b.kind==='LEADER'&&b.time>now&&b.distance>distance)cap=Math.min(cap,b.distance-1);
   const estimated=clamp(distance+speed*age,distance,cap),expected=leg/speed;
   const uncertainty=clamp(Math.max((now-confirmedTime)/Math.max(60,expected*2),boundary?0.55:0),0,1);
   result.push({bib:runner.bib,name:runner.name,distance_m:estimated,coordinates:model.pointAt(estimated),
    confirmed_distance_m:confirmedDistance,confirmed_time:position.time,confirmed_station:position.station,
    speed_basis:row.speed?'individual':(model.fieldAvailable?'field':'fallback'),
    uncertainty,inferred:!!boundary,boundary:boundary?{station:boundary.station,time:new Date(boundary.time*1000).toISOString()}:null,
    capped:estimated>=cap-0.01,opacity:0.85-uncertainty*0.5,color:`hsl(${140-uncertainty*105},65%,62%)`});
  }
  return result;
 }
 const api={prepare,estimate};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.RaceProgress=api;
})(typeof window!=='undefined'?window:globalThis);
