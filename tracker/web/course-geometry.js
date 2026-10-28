/* Pure geometry shared by the browser display and Node tests. */
(function(root){
  'use strict';
  const earth=6378137, feetPerMeter=3.280839895;
  function mercator(point){
    const latitude=Math.max(-85,Math.min(85,point[1]));
    return [earth*point[0]*Math.PI/180,earth*Math.log(Math.tan(Math.PI/4+latitude*Math.PI/360))];
  }
  function mapProjection(coordinates,width=1000,height=580,padding=55){
    const points=coordinates.map(mercator);
    let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
    for(const [x,y] of points){minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y)}
    const scale=Math.min((width-2*padding)/Math.max(1,maxX-minX),(height-2*padding)/Math.max(1,maxY-minY));
    const spanX=width/scale,spanY=height/scale,cx=(minX+maxX)/2,cy=(minY+maxY)/2;
    const bbox=[cx-spanX/2,cy-spanY/2,cx+spanX/2,cy+spanY/2];
    return {bbox,project(point){const [x,y]=mercator(point);return [(x-bbox[0])/spanX*width,(bbox[3]-y)/spanY*height]}};
  }
  function imageryUrl(bbox,width=1600,height=928){
    const query=new URLSearchParams({bbox:bbox.map(v=>v.toFixed(6)).join(','),bboxSR:'3857',imageSR:'3857',size:width+','+height,format:'jpg',f:'image'});
    return 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?'+query;
  }
  function elevationProfile(route){
    const distances=route.distance_m;
    if(!distances||distances.length!==route.coordinates.length||distances.length<2)return null;
    const heights=route.coordinates.map(p=>Number.isFinite(p[2])&&!(route.elevation_zero_is_missing&&p[2]===0)?p[2]*feetPerMeter:null);
    const valid=heights.flatMap((h,i)=>h===null?[]:[i]);
    if(!valid.length)return null;
    const gaps=[];
    for(let i=0;i<heights.length;i++){
      if(heights[i]!==null)continue;
      const first=i;while(i+1<heights.length&&heights[i+1]===null)i++;
      const last=i,left=first-1,right=last+1;
      gaps.push({from:distances[Math.max(0,left)],to:distances[Math.min(heights.length-1,right)]});
      for(let j=first;j<=last;j++){
        if(left<0)heights[j]=heights[right];
        else if(right>=heights.length)heights[j]=heights[left];
        else {const span=distances[right]-distances[left];const ratio=span>0?(distances[j]-distances[left])/span:0;heights[j]=heights[left]+ratio*(heights[right]-heights[left])}
      }
    }
    function at(distance){
      let lo=0,hi=distances.length-1;
      while(lo+1<hi){const mid=(lo+hi)>>1;if(distances[mid]<=distance)lo=mid;else hi=mid}
      const span=distances[hi]-distances[lo],ratio=span>0?Math.max(0,Math.min(1,(distance-distances[lo])/span)):0;
      return {feet:heights[lo]+ratio*(heights[hi]-heights[lo]),estimated:gaps.some(g=>distance>=g.from&&distance<=g.to)};
    }
    let min=Infinity,max=-Infinity;for(const height of heights){min=Math.min(min,height);max=Math.max(max,height)}
    const length=distances.at(-1),samples=[];
    const positions=new Set([0,length,...gaps.flatMap(g=>[g.from,g.to])]);
    for(let d=0;d<length;d+=25)positions.add(d);
    for(const distance of [...positions].sort((a,b)=>a-b))samples.push({distance,...at(distance)});
    return {min,max,gaps,samples,at};
  }
  const api={mercator,mapProjection,imageryUrl,elevationProfile};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.CourseGeometry=api;
})(typeof window!=='undefined'?window:globalThis);
