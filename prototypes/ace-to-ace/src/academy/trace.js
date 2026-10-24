// Bounded 2D telemetry trace. Reads recorded positions; no sim/replay state.
export function drawFlightTrace(g,w,h,trace=[],kind='plan') {
  g.save();g.clearRect(0,0,w,h);g.fillStyle='rgba(8,22,40,.72)';g.fillRect(0,0,w,h);
  g.font=`600 ${w>300?14:12}px system-ui,sans-serif`;g.fillStyle='#7dffb0';g.fillText(kind==='vertical'?'側視 高度／距離':'俯視 綠我／橘敵',8,15);
  if(trace.length<2){g.restore();return;}
  const paths=[trace.map(p=>({x:kind==='vertical'?-p.z:p.x,y:kind==='vertical'?p.y:-p.z}))];
  if(kind!=='vertical')paths.push(trace.map(p=>({x:p.bx,y:-p.bz})));
  const pts=paths.flat(),xs=pts.map(p=>p.x),ys=pts.map(p=>p.y);
  const minX=Math.min(...xs),minY=Math.min(...ys),dx=Math.max(200,Math.max(...xs)-minX),dy=Math.max(200,Math.max(...ys)-minY);
  const scale=Math.min((w-24)/dx,(h-40)/dy),ox=(w-dx*scale)/2,oy=h-12;
  paths.forEach((path,i)=>{
    g.strokeStyle=i?'#ffe2a3':'#7dffb0';g.lineWidth=1.6;g.beginPath();
    path.forEach((p,k)=>{const x=ox+(p.x-minX)*scale,y=oy-(p.y-minY)*scale;if(k)g.lineTo(x,y);else g.moveTo(x,y);});g.stroke();
    const p=path.at(-1);g.fillStyle=g.strokeStyle;g.fillRect(ox+(p.x-minX)*scale-2,oy-(p.y-minY)*scale-2,4,4);
  });
  g.restore();
}
