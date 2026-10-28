const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const geometry=require('../web/course-geometry.js');
const course=JSON.parse(fs.readFileSync(path.join(__dirname,'../../races/moreau-2026/course.json'),'utf8'));

test('satellite extent and course use exactly the same Web Mercator aspect ratio',()=>{
 const view=geometry.mapProjection(course.route.coordinates);
 const [x0,y0,x1,y1]=view.bbox;
 assert.ok(Math.abs((x1-x0)/(y1-y0)-1000/580)<1e-9);
 for(const p of course.route.coordinates){const [x,y]=view.project(p);assert.ok(x>=54.9&&x<=945.1&&y>=54.9&&y<=525.1)}
 const url=new URL(geometry.imageryUrl(view.bbox));
 assert.equal(url.searchParams.get('bboxSR'),'3857');
 assert.equal(url.searchParams.get('imageSR'),'3857');
 assert.equal(url.searchParams.get('size'),'1600,928');
});
test('missing zero elevations are interpolated and flagged rather than shown as sea level',()=>{
 const profile=geometry.elevationProfile({coordinates:[[0,0,100],[0,0,0],[0,0,0],[0,0,200]],distance_m:[0,100,200,300],elevation_zero_is_missing:true});
 assert.ok(Math.abs(profile.at(150).feet-150*3.280839895)<1e-8);
 assert.equal(profile.at(150).estimated,true);
 assert.ok(profile.min>300);
 assert.equal(profile.gaps.length,1);
});
test('a genuine zero elevation is retained unless a course explicitly marks it missing',()=>{
 const profile=geometry.elevationProfile({coordinates:[[0,0,0],[0,0,100]],distance_m:[0,100]});
 assert.equal(profile.at(0).feet,0);
 assert.equal(profile.gaps.length,0);
});
test('Moreau E lies in a missing-elevation span while G has recorded elevation',()=>{
 const profile=geometry.elevationProfile(course.route);
 const checkpoint=id=>course.checkpoints.find(c=>c.id===id).distance_m;
 assert.equal(profile.at(checkpoint('E')).estimated,true);
 assert.equal(profile.at(checkpoint('G')).estimated,false);
 assert.equal(profile.gaps.length,1);
});
test('courses without elevation data can still display their map',()=>{
 assert.equal(geometry.elevationProfile({coordinates:[[0,0],[0,0]],distance_m:[0,100]}),null);
});
