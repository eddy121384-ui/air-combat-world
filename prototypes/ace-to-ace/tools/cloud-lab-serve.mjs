// Local static preview with byte ranges for seeking the runtime comparison clips.
// No runtime/game dependency; Node built-ins only.
import http from 'node:http';
import {stat} from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,sep,extname} from 'node:path';
const root=fileURLToPath(new URL('../',import.meta.url)),port=Number(process.argv[2]||8096);
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript','.mjs':'text/javascript','.webm':'video/webm','.jpg':'image/jpeg','.png':'image/png','.webp':'image/webp','.json':'application/json','.md':'text/plain; charset=utf-8'};
const server=http.createServer(async(req,res)=>{
 try{
  if(!['GET','HEAD'].includes(req.method)){res.writeHead(405);res.end();return;}
  const url=new URL(req.url,'http://local');
  const path=resolve(root,'.'+decodeURIComponent(url.pathname==='/'?'/tools/cloud-lab.html':url.pathname));
  if(!path.startsWith(resolve(root)+sep)){res.writeHead(403);res.end();return;}
  const info=await stat(path);if(!info.isFile()){res.writeHead(404);res.end();return;}
  let start=0,end=info.size-1,status=200;
  const headers={'Content-Type':mime[extname(path)]||'application/octet-stream','Accept-Ranges':'bytes'};
  if(req.headers.range){
   const match=/^bytes=(\d+)-(\d*)$/.exec(req.headers.range);
   if(!match||Number(match[1])>=info.size){res.writeHead(416,{'Content-Range':`bytes */${info.size}`});res.end();return;}
   start=Number(match[1]);end=match[2]?Math.min(Number(match[2]),end):end;
   if(end<start){res.writeHead(416);res.end();return;}
   status=206;headers['Content-Range']=`bytes ${start}-${end}/${info.size}`;
  }
  headers['Content-Length']=Math.max(0,end-start+1);res.writeHead(status,headers);
  if(req.method==='HEAD'||!info.size){res.end();return;}
  const stream=createReadStream(path,{start,end});res.on('close',()=>stream.destroy());
  stream.on('error',()=>res.destroy());stream.pipe(res);
 }catch{if(!res.headersSent)res.writeHead(404);res.end();}
});
server.listen(port,'127.0.0.1',()=>console.log(`Cloud Lab http://127.0.0.1:${port}/tools/cloud-lab.html\nComparison http://127.0.0.1:${port}/docs/cloud-engine-b2/gallery.html`));
