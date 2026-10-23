import {HUD_ITEMS,emptyLayout,validLayout,loadLayout,saveLayout,safeBounds,layoutRect,relativeEntry} from './hud-layout.js';
const managed=['position','left','top','right','bottom','width','height','opacity','margin','background-color','border-color','--power-scale'];
const copy=x=>JSON.parse(JSON.stringify(x));
export class HudEditor {
  constructor({input,onClose=()=>{}}) {
    this.input=input;this.onClose=onClose;this.layout=loadLayout();this.active=false;
    this.root=document.querySelector('#hudEditor');this.handles=new Map();this.nodes=new Map(HUD_ITEMS.map(([k,s])=>[k,document.querySelector(s)]));
    const layer=document.querySelector('#hudHandles'),select=document.querySelector('#hudSelection');
    for(const [key,,label] of HUD_ITEMS) {
      const handle=document.createElement('div');handle.className='hud-handle';handle.dataset.edit=key;
      const text=document.createElement('span');text.textContent=key==='power'?'THROTTLE':label;handle.append(text);
      layer.append(handle);this.handles.set(key,handle);
      const option=document.createElement('option');option.value=key;option.textContent=label;select.append(option);
      handle.addEventListener('pointerdown',e=>this.down(e,key));
      handle.addEventListener('pointermove',e=>this.move(e));
      for(const type of ['pointerup','pointercancel','lostpointercapture'])handle.addEventListener(type,e=>{if(this.drag?.id===e.pointerId)this.drag=null;});
    }
    select.addEventListener('change',()=>this.select(select.value));
    for(const [id,key,factor] of [['hudSize','scale',.01],['hudOpacity','opacity',.01]])document.querySelector('#'+id).addEventListener('input',e=>{
      const entry=this.entry(this.selected);entry[key]=Number(e.target.value)*factor;this.draft.items[this.selected]=entry;this.render();this.select(this.selected);
    });
    document.querySelector('#hudSave').addEventListener('click',()=>this.close(true));
    document.querySelector('#hudCancel').addEventListener('click',()=>this.close(false));
    document.querySelector('#hudReset').addEventListener('click',()=>this.preset('default'));
    document.querySelector('#hudRight').addEventListener('click',()=>this.preset('right'));
    document.querySelector('#hudLeft').addEventListener('click',()=>this.preset('left'));
    document.querySelector('#hudBorders').addEventListener('change',e=>this.root.classList.toggle('no-borders',!e.target.checked));
    document.querySelector('#hudFold').addEventListener('click',()=>{const folded=this.root.classList.toggle('folded');document.querySelector('#hudFold').textContent=folded?'展開':'收合';});
    window.addEventListener('keydown',e=>{if(this.active&&e.code==='Escape'){e.preventDefault();this.close(false);}});
    window.addEventListener('resize',()=>{this.drag=null;this.input.releaseHeld();this.render();});
    this.render();
  }
  safe() {
    const css=getComputedStyle(document.documentElement),value=k=>parseFloat(css.getPropertyValue(k))||0;
    // Resolve env() through the computed safe-area rectangle (custom vars may retain env tokens).
    const probe=document.querySelector('#hudSafeArea'),r=probe.getBoundingClientRect();
    return safeBounds(innerWidth,innerHeight,{left:Math.max(r.x,value('--sal')),right:Math.max(innerWidth-r.right,value('--sar')),
      top:Math.max(r.y,value('--sat')),bottom:Math.max(innerHeight-r.bottom,value('--sab'))});
  }
  clearStyles() {
    for(const node of this.nodes.values())for(const k of managed)node.style.removeProperty(k);
    for(const s of ['#throttleTrack','#throttleValue','#stickBase'])document.querySelector(s).style.removeProperty('opacity');
    for(const k of ['--stick-home-x','--stick-home-y','--stick-size'])document.documentElement.style.removeProperty(k);
    this.input.stickScale=this.input.throttleScale=1;
  }
  render() {
    this.clearStyles();const safe=this.safe(),layout=this.active?this.draft:this.layout;
    // Measure legacy CSS, even when TILT currently hides the stick/CAL.
    const hidden=[];for(const node of this.nodes.values()) {if(node.classList.contains('hidden')){hidden.push(node);node.classList.remove('hidden');}
    }
    // #touch can be hidden on menus: measure without making controls interactive.
    const touch=document.querySelector('#touch'),wasHidden=touch.classList.contains('hidden');if(wasHidden)touch.classList.remove('hidden');
    this.base=new Map([...this.nodes].map(([k,n])=>[k,n.getBoundingClientRect().toJSON()]));
    for(const [key] of HUD_ITEMS) {
      const e=layout.items[key];if(!e)continue;
      const node=this.nodes.get(key),r=layoutRect(e,this.base.get(key),safe,key);
      Object.assign(node.style,{position:'fixed',left:r.x+'px',top:r.y+'px',right:'auto',bottom:'auto',width:r.width+'px',height:r.height+'px',margin:'0'});
      if(key==='power') {
        const scale=Math.min(e.scale,r.width/this.base.get(key).width,r.height/this.base.get(key).height);
        node.style.setProperty('--power-scale',scale);this.input.throttleScale=scale;
        // Fade the strip's frame too, without multiplying independent AB/BRK opacity.
        node.style.backgroundColor=`rgba(9,31,51,${.46*e.opacity})`;
        node.style.borderColor=`rgba(155,203,222,${.52*e.opacity})`;
        for(const s of ['#throttleTrack','#throttleValue'])document.querySelector(s).style.opacity=e.opacity;
        for(const btn of ['boost','brake'])if(!layout.items[btn])this.nodes.get(btn).style.opacity=e.opacity;
      } else if(key==='stick') {
        this.input.stickScale=e.scale;
        const root=document.documentElement.style;root.setProperty('--stick-size',e.scale);
        root.setProperty('--stick-home-x',r.x+Math.min(110*e.scale,r.width/2)+'px');
        root.setProperty('--stick-home-y',r.y+r.height-Math.min(120*e.scale,r.height/2)+'px');
        document.querySelector('#stickBase').style.opacity=e.opacity;
      } else node.style.opacity=key==='pause'?Math.max(.6,e.opacity):e.opacity;
    }
    this.input.setThrottle(this.input.throttle());
    if(this.active) {
      for(const [key,node] of this.nodes) {
        const r=node.getBoundingClientRect(),h=this.handles.get(key);
        Object.assign(h.style,{left:r.x+'px',top:r.y+'px',width:r.width+'px',height:r.height+'px'});
      }
      this.warnings();
    }
    if(wasHidden)touch.classList.add('hidden');for(const node of hidden)node.classList.add('hidden');
  }
  entry(key) {
    const existing=this.draft.items[key];if(existing)return {...existing};
    const rect=this.nodes.get(key).getBoundingClientRect(),base=this.base.get(key);
    const scale=key==='boost'||key==='brake'?rect.width/base.width:1;
    return relativeEntry(rect,this.safe(),scale,key==='boost'||key==='brake'?(this.draft.items.power?.opacity||1):1);
  }
  open() {
    this.input.releaseHeld();this.input.enabled=false;this.draft=copy(this.layout);this.active=true;
    document.body.classList.add('hud-editing');this.root.classList.remove('hidden');
    this.render();this.select('gun');
  }
  close(save) {
    if(!this.active)return;
    this.drag=null;let stored=true;
    if(save){this.layout=validLayout(this.draft);stored=saveLayout(this.layout);}
    this.active=false;document.body.classList.remove('hud-editing');this.root.classList.add('hidden');
    this.render();this.input.releaseHeld();this.input.enabled=true;this.onClose({save,stored});
  }
  select(key) {
    this.selected=key;document.querySelector('#hudSelection').value=key;
    document.querySelector('#hudSelectionNote').textContent=key==='pause'?'暫停保留至少 40px 與 60% 可見度。':key==='power'?'拖曳移動整條；AB／BRK 獨立配置後不隨油門移動。':key==='stick'?'拖曳移動搖桿區；大小也會調整操縱行程。':'拖曳框線移動；收合工具可預覽全畫面。';
    for(const [k,h] of this.handles)h.classList.toggle('selected',k===key);
    const e=this.entry(key);document.querySelector('#hudSize').value=Math.round(e.scale*100);document.querySelector('#hudOpacity').value=Math.round(e.opacity*100);
    document.querySelector('#hudSizeValue').textContent=Math.round(e.scale*100)+'%';document.querySelector('#hudOpacityValue').textContent=Math.round(e.opacity*100)+'%';
  }
  down(e,key) {
    if(!this.active||this.drag)return;e.preventDefault();e.stopPropagation();this.select(key);
    const rect=this.nodes.get(key).getBoundingClientRect();this.drag={id:e.pointerId,key,x:e.clientX,y:e.clientY,rect,entry:this.entry(key)};
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  move(e) {
    const d=this.drag;if(!this.active||d?.id!==e.pointerId)return;e.preventDefault();
    this.draft.items[d.key]=relativeEntry({x:d.rect.x+e.clientX-d.x,y:d.rect.y+e.clientY-d.y,width:d.rect.width,height:d.rect.height},this.safe(),d.entry.scale,d.entry.opacity);
    this.render();
  }
  preset(side) {
    this.draft=emptyLayout();this.render();
    if(side==='left') {
      const safe=this.safe();
      for(const [key,node] of this.nodes) {
        if(['pause','level','boost','brake'].includes(key))continue;
        const e=relativeEntry(node.getBoundingClientRect(),safe);e.x=1-e.x;
        if(key==='power'){e.x=.07;e.y=.43;e.scale=.9;}
        if(key==='flare'){e.x=.26;e.y=.39;}
        if(key==='look'){e.x=.36;e.y=.39;}
        if(key==='yawLeft'){e.x=.30;e.y=.66;}
        if(key==='yawRight'){e.x=.40;e.y=.66;}
        this.draft.items[key]=e;
      }
    }
    this.render();this.select(this.selected||'gun');
  }
  warnings() {
    const pairs=[],keys=HUD_ITEMS.map(x=>x[0]).filter(k=>!['stick','power','calibrate'].includes(k));
    for(let i=0;i<keys.length;i++)for(let j=i+1;j<keys.length;j++) {
      const a=this.nodes.get(keys[i]).getBoundingClientRect(),b=this.nodes.get(keys[j]).getBoundingClientRect();
      const dx=Math.max(a.x-b.right,b.x-a.right,0),dy=Math.max(a.y-b.bottom,b.y-a.bottom,0);
      if(dx<12&&dy<12){const label=k=>HUD_ITEMS.find(item=>item[0]===k)[2];pairs.push(label(keys[i])+' / '+label(keys[j]));}
    }
    document.querySelector('#hudWarning').textContent=pairs.length?'拇指間距偏近：'+pairs.slice(0,2).join('、')+'。請預留移動空間。':'預留拇指移動空間，別遮住中央瞄準區。';
  }
}
