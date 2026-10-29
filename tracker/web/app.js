'use strict';
const $=id=>document.getElementById(id);
const NS='http://www.w3.org/2000/svg';
let course=null,state=null,selected=null;
const settings=window.TRACKER_SETTINGS||{stateUrl:'/api/state',courseUrl:'/api/course',static:false};
let loadedCourseUrl=null,clockAge=0;
let clockReceived=performance.now();
function tickClock(){if(!state)return;const seconds=state.race.clock_mode==='live'?(new Date(state.race.clock)-new Date(state.race.start_time))/1000+clockAge+(performance.now()-clockReceived)/1000:state.race.elapsed_seconds;$('clock').textContent=elapsed(seconds)}
function elapsed(value){const n=Math.max(0,Math.floor(value));return [Math.floor(n/3600),Math.floor(n/60)%60,n%60].map(v=>String(v).padStart(2,'0')).join(':')}
function time(value){return value?new Date(value).toLocaleTimeString('en-US',{timeZone:state?.race.timezone||'America/New_York',hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—'}
function sourceStatus(health,now=Date.now()){
 const describe=(h,label)=>{const stale=!h.last_success||now-new Date(h.last_success)>Math.max(45,(h.expected_interval_seconds||15)*2.5)*1000;return {error:Boolean(h.error)||stale,text:h.error?`${label}: ${h.error}`:h.last_success?`${label} ${stale?'delayed':'connected'} · Last read ${time(h.last_success)}`:`${label}: waiting for first read`}};
 const radio=describe(health,health.mode==='file'?'Local log':'Radio log');
 const rd=health.director?describe(health.director,'RD log'):null;
 return {error:radio.error||Boolean(rd?.error),text:radio.text+(rd?' | '+rd.text:'')};
}
function sweeperStatus(sweeper,now=Date.now()){
 if(!sweeper?.enabled)return {visible:false,showMarker:false,text:'',stale:false};
 const p=sweeper.position;
 if(!p)return {visible:true,showMarker:false,stale:false,text:(sweeper.error?sweeper.error+' ':'')+(sweeper.off_course?'Sweep team · Latest GPS report is outside the course area.':'Sweep team · Waiting for a race-day GPS report near the course.')};
 const age=Math.max(0,(now-new Date(p.time))/1000),stale=age>(sweeper.stale_after_seconds||1800);
 const miles=p.distance_m===null?' · Course distance uncertain':` · Approx. mile ${(p.distance_m/1609.344).toFixed(1)}`;
 return {visible:true,showMarker:true,stale,text:(sweeper.error?sweeper.error+' ':'')+`Sweep team · GPS ${time(p.time)} · ${Math.floor(age/60)} min ago${stale?' · Position may be outdated':''}${miles}`};
}
function svg(tag,attrs,parent){const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);parent.append(e);return e}
function label(parent,x,y,text,color,size=15){const e=svg('text',{x,y,fill:color,'font-size':size,'font-weight':600,'paint-order':'stroke',stroke:'#0e2026','stroke-width':4},parent);e.textContent=text;return e}
let mapMode='satellite',mapCache=null,elevationCache=null;
function runnerGroups(){const groups={};for(const r of state.runners){const position=r.position??r.last;if(!position?.station)continue;(groups[position.station]??=[]).push(r)}return groups}
function countMarker(parent,x,y,runners,estimated=false){
 const marked=runners.some(r=>r.bib===selected);
 svg('circle',{cx:x,cy:y,r:marked?19:15,fill:'#a4e4bc',stroke:marked?'#fff':estimated?'#f5b369':'#0b171c','stroke-width':3},parent);
 const e=svg('text',{x,y:y+5,'text-anchor':'middle',fill:'#0b171c','font-size':14,'font-weight':800},parent);e.textContent=runners.length;
 const title=svg('title',{},e);title.textContent=runners.map(r=>r.bib+' '+r.name).join(', ')+(estimated?' · Elevation interpolated across missing track data':'');
}
function broomMarker(parent,x,y,stale=false,scale=1){
 const color=stale?'#a6bebc':'#f5b369',g=svg('g',{transform:`translate(${x},${y}) scale(${scale})`,'aria-label':'Sweep team last reported GPS position'},parent);
 svg('circle',{cx:0,cy:0,r:24,fill:'#12252c',stroke:color,'stroke-width':2,'stroke-dasharray':stale?'4 3':'none'},g);
 svg('line',{x1:12,y1:-17,x2:-3,y2:5,stroke:color,'stroke-width':5,'stroke-linecap':'round'},g);
 svg('path',{d:'M-7,0 L2,6 L-4,19 L-22,7 Z',fill:color,stroke:'#0b171c','stroke-width':1},g);
 for(const [a,b,c,d] of [[-5,6,-12,12],[-1,8,-7,15],[-10,3,-17,9]])svg('line',{x1:a,y1:b,x2:c,y2:d,stroke:'#493c2b','stroke-width':1.3},g);
 svg('title',{},g).textContent='Sweep team · '+time(state.sweeper.position.time)+(stale?' · Last position is outdated':' · Last reported GPS position');
}
function drawSweeper(){
 const status=sweeperStatus(state.sweeper),note=$('sweeper-status');note.hidden=!status.visible;note.textContent=status.text;note.classList.toggle('stale',status.stale||Boolean(state.sweeper?.error));
 if(!mapCache)return;
 mapCache.sweepers.replaceChildren();
 if(!status.showMarker)return;
 const p=state.sweeper.position,[x,y]=mapCache.project([p.longitude,p.latitude]);
 if(x>=0&&x<=1000&&y>=0&&y<=580)broomMarker(mapCache.sweepers,x,y,status.stale);
 else note.textContent+=' · Latest position is outside this map view.';
}
function drawMap(){
 if(!course||!state)return;
 const root=$('course-map'),route=course.route.coordinates;
 if(!mapCache||mapCache.course!==course||mapCache.mode!==mapMode){
  root.replaceChildren();
  const projection=window.CourseGeometry.mapProjection(route),project=projection.project;
  const locations={};
  for(let x=50;x<1000;x+=75)svg('line',{x1:x,y1:0,x2:x,y2:580,stroke:'#193139','stroke-width':1},root);
  for(let y=40;y<580;y+=75)svg('line',{x1:0,y1:y,x2:1000,y2:y,stroke:'#193139','stroke-width':1},root);
  $('imagery-status').textContent='';
  $('imagery-attribution').hidden=mapMode!=='satellite';
  if(mapMode==='satellite'){
   const image=svg('image',{x:0,y:0,width:1000,height:580,href:window.CourseGeometry.imageryUrl(projection.bbox),preserveAspectRatio:'none',opacity:0.83},root);
   image.addEventListener('error',()=>{if(mapMode==='satellite')$('imagery-status').textContent='Satellite imagery is unavailable. The course, checkpoints and elevation still work.'});
  }
  const path=route.filter((_,i)=>i%5===0||i===route.length-1).map((p,i)=>(i?'L':'M')+project(p).join(',')).join(' ');
  svg('path',{d:path,fill:'none',stroke:'#061015','stroke-width':8,'stroke-linejoin':'round'},root);
  svg('path',{d:path,fill:'none',stroke:'#bef3c5','stroke-width':3.2,'stroke-linejoin':'round'},root);
  label(root,935,35,'N ↑','#eff7f0',16);
  for(const c of course.checkpoints){const [x,y]=project(c.coordinates);locations[c.id]=[x,y];
   if(c.aid_station)svg('rect',{x:x-7,y:y-7,width:14,height:14,fill:'#f5b369',stroke:'#0e2026','stroke-width':2},root);
   else svg('circle',{cx:x,cy:y,r:7,fill:'#e7f1ea',stroke:'#0e2026','stroke-width':2},root);
   label(root,x+12,y-11,c.id,'#fff',18);
  }
  locations.START=project(route[0]);locations.FINISH=project(route.at(-1));
  label(root,locations.START[0]+10,locations.START[1]-16,'START','#c6f7cf',13);
  label(root,locations.FINISH[0]+10,locations.FINISH[1]+22,'FINISH','#c6f7cf',13);
  mapCache={course,mode:mapMode,locations,project,runners:svg('g',{},root),sweepers:svg('g',{},root)};
 }
 mapCache.runners.replaceChildren();
 for(const [station,runners] of Object.entries(runnerGroups())){const p=mapCache.locations[station];if(p)countMarker(mapCache.runners,p[0],p[1],runners)}
 $('course-note').textContent=`${(course.route.length_m/1609.344).toFixed(2)} mapped miles · Aid stations: ${course.checkpoints.filter(c=>c.aid_station).map(c=>c.id).join(', ')||'none marked'} · Numbered circles count runners last reported at that location`;
 drawElevation();
 drawSweeper();
}
function drawElevation(){
 const root=$('elevation-profile');
 if(!elevationCache||elevationCache.course!==course){
  root.replaceChildren();
  const profile=window.CourseGeometry.elevationProfile(course.route);
  if(!profile){label(root,70,100,'Elevation data is not available for this course.','#a6bebc',18);elevationCache={course,profile:null};return}
  const low=Math.floor(profile.min/250)*250,high=Math.max(low+250,Math.ceil(profile.max/250)*250);
  const length=course.route.length_m,x=d=>65+d/length*900,y=height=>195-(height-low)/(high-low)*145;
  for(let feet=low;feet<=high;feet+=250){const yy=y(feet);svg('line',{x1:65,y1:yy,x2:965,y2:yy,stroke:'#29434b','stroke-width':1},root);label(root,8,yy+4,String(feet),'#a6bebc',11)}
  let path='',solid='',dashed='';
  const samples=profile.samples;
  for(let i=0;i<samples.length;i++){
   const p=samples[i],point=x(p.distance)+','+y(p.feet);path+=(i?'L':'M')+point;
   if(i){const previous=samples[i-1],piece='M'+x(previous.distance)+','+y(previous.feet)+'L'+point;if(previous.estimated||p.estimated)dashed+=piece;else solid+=piece}
  }
  svg('path',{d:path+'L965,195L65,195Z',fill:'#6aafa2','fill-opacity':0.18,stroke:'none'},root);
  svg('path',{d:solid,fill:'none',stroke:'#acd8c6','stroke-width':2},root);
  svg('path',{d:dashed,fill:'none',stroke:'#f5b369','stroke-width':2,'stroke-dasharray':'6 5'},root);
  for(let mile=0;mile<=length/1609.344;mile+=2){const xx=x(mile*1609.344);svg('line',{x1:xx,y1:195,x2:xx,y2:201,stroke:'#a6bebc'},root);label(root,xx-4,218,String(mile),'#a6bebc',11)}
  label(root,910,243,'Miles','#a6bebc',12);label(root,8,28,'Feet','#a6bebc',12);
  for(const c of course.checkpoints){const xx=x(c.distance_m);svg('line',{x1:xx,y1:35,x2:xx,y2:195,stroke:c.aid_station?'#b67b43':'#31505a','stroke-width':0.8,'stroke-dasharray':'2 5'},root);label(root,xx-5,28,c.id,c.aid_station?'#f5b369':'#c2d8d2',13)}
  elevationCache={course,profile,x,y,runners:svg('g',{},root),sweepers:svg('g',{},root)};
  $('elevation-note').textContent=(course.route.elevation_backfill?'Elevation from the course trace, with missing values filled from USGS 3DEP terrain data.':'Elevation from the supplied course trace.')+' Runner markers show confirmed course distance.'+(profile.gaps.length?' Orange dashed sections and orange-outlined markers use interpolated elevation where the track has missing values.':'');
 }
 if(!elevationCache.profile)return;
 const cache=elevationCache;cache.runners.replaceChildren();cache.sweepers.replaceChildren();
 for(const runners of Object.values(runnerGroups())){const distance=runners[0].distance_m;if(distance===null)continue;const height=cache.profile.at(distance);countMarker(cache.runners,cache.x(distance),cache.y(height.feet),runners,height.estimated)}
 const sweep=sweeperStatus(state.sweeper),position=state.sweeper?.position;
 if(sweep.showMarker&&position.distance_m!==null){const height=cache.profile.at(position.distance_m);broomMarker(cache.sweepers,cache.x(position.distance_m),cache.y(height.feet),sweep.stale,0.65)}
}
function drawTable(){if(!state)return;const filter=$('search').value.toLowerCase();const body=$('runners');body.replaceChildren();
for(const r of state.runners.filter(r=>(r.bib+' '+r.name).toLowerCase().includes(filter))){const row=document.createElement('tr');row.classList.toggle('selected-row',selected===r.bib);const first=document.createElement('td'),button=document.createElement('button'),bib=document.createElement('b');bib.textContent=r.bib;button.append(bib,document.createTextNode(r.name));button.onclick=()=>{selected=selected===r.bib?null:r.bib;drawMap();drawTable()};first.append(button);row.append(first);const status=document.createElement('td'),pill=document.createElement('span');pill.className='pill '+r.status;pill.textContent={on_course:'On course',finished:'Finished #'+r.place,withdrawn:'Withdrawn',dns:'DNS',not_reported:'Not reported'}[r.status];status.append(pill);row.append(status);
const ago=r.last?elapsed((new Date(state.race.clock)-new Date(r.last.time))/1000):'—';for(const value of [r.last?.station||(r.position?.station?`${r.position.station} (last known)`:'—'),time(r.last?.time),ago,r.elapsed_seconds===null?'—':elapsed(r.elapsed_seconds)]){const cell=document.createElement('td');cell.textContent=value;row.append(cell)}body.append(row)}}
function render(){const s=state;document.querySelector('footer').textContent='Checkpoint-based tracking · '+s.race.name+(s.race.test_mode?' · Fictional test data':'');$('race-name').textContent=s.race.name;$('mode').textContent=s.race.test_mode?'FICTIONAL TEST':'LIVE RACE';$('clock').textContent=elapsed(s.race.elapsed_seconds);$('clock-note').textContent=s.race.clock_mode==='latest_report'?'Test clock follows the latest entered report · No estimated runner movement':`Race start: ${time(s.race.start_time)} · Clock runs in real time · Confirmed checkpoint tracking`;$('roster-count').textContent=s.runners.length;$('on-course').textContent=s.counts.on_course;$('finished').textContent=s.counts.finished;$('withdrawn').textContent=s.counts.withdrawn;$('dns').textContent=s.counts.dns||0;
document.querySelector('aside').hidden=Boolean(s.public_view);document.querySelector('.review').hidden=Boolean(s.public_view);document.querySelector('details').hidden=Boolean(s.public_view);document.querySelector('.layout').style.gridTemplateColumns=s.public_view?'1fr':'';
const status=sourceStatus(s.source);$('connection').classList.toggle('error',status.error);$('connection').textContent=status.text+` · ${s.revision} saved revisions`;
const activity=$('activity');activity.replaceChildren();for(const entry of s.history){const li=document.createElement('li');li.textContent=entry.raw;const note=document.createElement('small');note.textContent='Received '+time(entry.received)+' · Revision '+entry.sequence;li.append(note);activity.append(li)}if(!s.history.length){const li=document.createElement('li');li.textContent='Ready for the first report.';activity.append(li)}
const issues=$('issues');issues.replaceChildren();const all=[...s.issues.map(i=>`${i.line?'Line '+i.line+': ':''}${i.message} — ${i.text}`),...s.anomalies.map(i=>`Bib ${i.bib}, ${i.id}: ${i.message}`)];$('issue-count').textContent=all.length;for(const message of all){const li=document.createElement('li');li.textContent=message;issues.append(li)}if(!all.length){const li=document.createElement('li');li.textContent='No reports need attention.';li.style.color='#a6bebc';issues.append(li)}drawMap();drawTable()}
async function refresh(){try{
const response=await fetch(settings.stateUrl,{cache:'no-store'});if(!response.ok)throw Error('Could not load race state');const next=await response.json();
const courseUrl=next.course_url||settings.courseUrl;if(!course||loadedCourseUrl!==courseUrl){const result=await fetch(courseUrl,{cache:'no-store'});if(!result.ok)throw Error('Could not load course');course=await result.json();loadedCourseUrl=courseUrl}
state=next;clockReceived=performance.now();clockAge=state.published_at?Math.max(0,(Date.now()-new Date(state.published_at))/1000):0;render();tickClock()
}catch(error){$('connection').classList.add('error');$('connection').textContent=(settings.static?'Published updates are unavailable.':'Tracker service disconnected.')+' Last displayed data may be stale. '+error.message}finally{setTimeout(refresh,3000)}}
$('satellite-view').addEventListener('click',()=>setMapMode('satellite'));$('course-view').addEventListener('click',()=>setMapMode('course'));
function setMapMode(mode){mapMode=mode;$('satellite-view').setAttribute('aria-pressed',String(mode==='satellite'));$('course-view').setAttribute('aria-pressed',String(mode==='course'));drawMap()}
$('search').addEventListener('input',drawTable);setInterval(tickClock,1000);refresh();
