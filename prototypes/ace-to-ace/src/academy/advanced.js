// Three opt-in advanced sorties. Existing ten lesson definitions/judges stay intact.
import { placeJet, bankDeg, gammaDeg, hdgDeg, wrapDeg } from './runner.js';
import { ManeuverPilot } from './maneuver-pilot.js';
import { PlayerController } from '../game/input.js';
import { TurnDrone } from './drones.js';
import { ChaserBot } from '../ai/bots.js';
import { specificEnergy, makeControls } from '../sim/aircraft.js';
import { sub, norm, dot, len, angleBetween, forwardOf, upOf, DEG } from '../sim/math.js';

export const advancedSupport=(lesson,control)=>lesson.id==='A01'&&control!=='expert'
  ? 'A01 需要 Expert：Assisted 在過頂後會介入改平，無法保持本課所需的倒飛半滾轉。請在飛行設定選擇相同物理模式的 Expert。' : null;
export function relativeFlight(a,b) {
  const p=sub(b.pos,a.pos),R=len(p),los=norm(p);
  return {range:R,closure:dot(sub(a.vel,b.vel),los),ata:angleBetween(forwardOf(a.q),los)/DEG,
    tail:angleBetween(forwardOf(b.q),los)/DEG,along:dot(p,forwardOf(a.q)),entryAlong:-p.z};
}
function resetScenario(r) {
  // Explicit new situation at demo/practice/challenge boundaries ONLY.
  const id=r.lesson.id;r.waiting=false;r.demoController=null;
  r.match.timeLimit=1e9;r.match.result=null;r.match.phase='regulation';
  r.match.missiles=[];r.match.bullets=[];
  placeJet(r.me,{pos:{x:0,y:3000,z:0},speed:id==='A01'?280:id==='T01'?270:190,heading:0,throttle:.72});
  placeJet(r.foe,{pos:{x:0,y:3000,z:id==='T02'?650:-1000},speed:id==='T02'?250:180,heading:0,throttle:.72});
  for(const ac of [r.me,r.foe]){ac.controls=makeControls();ac.controls.throttle=.72;ac.abCur=0;ac.lock={target:null,timer:0,locked:false};ac.oob=0;ac.hp=100;ac.alive=true;ac.damageScale=0;ac.deathCause=null;}
  r.foe.dormant=id==='A01';
  if(id==='T01')r.match.setController(r.foe,new TurnDrone(r.foe,{speed:180,rate:7}));
  if(id==='T02'){
    const ai=new ChaserBot(r.foe,{seed:91});
    r.foeAI=ai;r.match.setController(r.foe,{update(dt,m){
      const c=ai.update(dt,m);c.fireMissile=false;c.fireGun=false;return c;
    }});
  }
  r.d.m={entrySpeed:r.me.speed,entryEnergy:specificEnergy(r.me),minSpeed:r.me.speed,maxHeight:0,
    maxG:1,vertical:false,inverted:false,halfRoll:0,window:0,bestWindow:0,
    initialClosure:relativeFlight(r.me,r.foe).closure,peakClosure:0,lowestClosure:Infinity,
    unload:0,reversals:0,side:0,overshoot:false,lowEnergy:0,badFire:0,fullG:0,
    trace:[],sampleT:0,stage:r.phase.id,startT:r.t};
  r.inputReset=true;
}
function measure(r,dt) {
  const a=r.me,b=r.foe,m=r.d.m,g=relativeFlight(a,b),f=forwardOf(a.q),u=upOf(a.q);
  m.minSpeed=Math.min(m.minSpeed,a.speed);m.maxHeight=Math.max(m.maxHeight,a.pos.y-3000);
  m.maxG=Math.max(m.maxG,a.nCur);m.peakClosure=Math.max(m.peakClosure,g.closure);
  m.lowestClosure=Math.min(m.lowestClosure,g.closure);
  m.vertical ||= f.y>.94&&gammaDeg(a)>70;
  if(m.vertical&&f.z>.85&&u.y<-.65)m.inverted=true;
  if(m.inverted)m.halfRoll+=Math.abs(a.rollRateCur)*dt/DEG;
  if(a.pos.y>3150&&gammaDeg(a)>10&&a.nCur<4.5)m.unload+=dt;
  // Count settled left/right banks, not +/-180 wraparound or thumb jitter.
  const bank=bankDeg(a),side=Math.abs(bank)>30&&Math.abs(bank)<110?Math.sign(bank):0;
  if(Math.abs(bank)<15){m.crossedLevel=true;m.levelHeading=hdgDeg(a);}
  // A roll without a real turn is not a scissors reversal.
  const turned=side*wrapDeg(hdgDeg(a)-(m.levelHeading??hdgDeg(a)))>=8;
  if(side&&side!==m.side&&m.crossedLevel&&turned){
    if(m.side)m.reversals++;
    m.side=side;m.crossedLevel=false;
  }
  if(r.lesson.id==='T02'&&g.entryAlong>40&&g.along>40&&g.range<1500)m.overshoot=true;
  if(a.speed<100)m.lowEnergy+=dt;
  m.slowNow=a.speed<85?(m.slowNow||0)+dt:0;
  if(a.nCur>7)m.fullG+=dt;
  const window=g.range>=80&&g.range<1400&&g.ata<(r.lesson.id==='T02'?30:18)&&g.tail<50&&Math.abs(g.closure)<35&&a.speed>=100;
  if(r.lesson.id!=='A01'){if(window)m.window+=dt;else m.window=0;}
  m.bestWindow=Math.max(m.bestWindow,m.window);
  if(a.controls.fireGun&&!window)m.badFire+=dt;
  if(r.t>=m.sampleT){m.sampleT=r.t+.2;m.trace.push({x:a.pos.x,y:a.pos.y,z:a.pos.z,bx:b.pos.x,by:b.pos.y,bz:b.pos.z});if(m.trace.length>400)m.trace.shift();}
  m.duration=r.phaseT;
  m.end={speed:a.speed,energy:specificEnergy(a),height:a.pos.y-3000,...g};
  return {m,g,window};
}
export function advancedFailure(r) {
  const m=r.d.m,id=r.lesson.id;
  if(m.minSpeed<85)return `速度低至 ${Math.round(m.minSpeed*3.6)} km/h${id==='T02'?`、有效反轉 ${m.reversals} 次`:''}：低能量時繼續拉桿只會失去轉向餘裕。卸載、恢復速度再嘗試。`;
  if(id==='A01') {
    if(!m.vertical)return '沒有經過向上垂直航跡：這是平面轉彎，不是半筋斗。先保持機翼水平，以約 4–5G 拉起。';
    if(!m.inverted)return '已爬升，但沒有倒飛反向：半筋斗尚未完成。越過頂點後仍須完成反向，再開始半滾轉。';
    if(m.halfRoll<140)return `倒飛後只滾轉 ${Math.round(m.halfRoll)}°：少了最後半滾轉。卸載、左右滾轉至機翼朝上，再看 FPM。`;
    if(r.alt<3600)return `機動末端只保留 ${Math.round(r.alt-3000)}m 高度收益：曾經爬高不等於完成高度交易。半滾轉後在高處改平，別再俯衝回起點。`;
    return `已反向但未穩住：坡度 ${Math.round(r.bank)}°、航跡 ${Math.round(r.gamma)}°。先停滾轉，再小幅修 FPM。`;
  }
  if(m.badFire>.2)return `尚未改善位置就開火 ${m.badFire.toFixed(1)} 秒：窗口要求尾後位置、距離與接近率同時合適。先完成機動，再考慮射擊。`;
  if(id==='T01') {
    if(m.maxHeight<250)return `只爬升 ${Math.round(m.maxHeight)} m：沒有把多餘速度換成高度。先卸載拉起，再從高處切回。`;
    if(m.unload<.5)return `曾爬升，但低 G 爬升只有 ${m.unload.toFixed(1)} 秒。一直拉緊會消耗能量；放鬆轉彎，讓相對位置改變。`;
    return `接近率 ${Math.round(m.end.closure*3.6)} km/h、偏離機尾 ${Math.round(m.end.tail)}°：尚無穩定射擊窗口。別追急，從高處切回尾後、提早收油。`;
  }
  if(m.reversals<2)return `有效反轉 ${m.reversals} 次：持續同向拉 G 不是剪刀。觀察追兵，交替滾轉並管理速度，至少完成兩次反轉。`;
  if(!m.overshoot)return `反轉 ${m.reversals} 次，追兵仍未穿過前方：速度管理尚未造成衝過頭，單靠左右搖晃不足。`;
  return `追兵曾衝過頭，但未取得尾後或安全脫離；最低 ${Math.round(m.minSpeed*3.6)} km/h。反轉後保留能量，別急著追機頭。`;
}
function success(r,dt,{m,g}) {
  if(r.lesson.id==='A01') {
    const stable=m.inverted&&m.halfRoll>=140&&r.alt>=3600&&Math.abs(wrapDeg(hdgDeg(r.me)-180))<15&&Math.abs(r.bank)<12&&Math.abs(r.gamma)<7&&r.me.speed>110;
    m.window=stable?m.window+dt:0;m.bestWindow=Math.max(m.bestWindow,m.window);return m.window>=1;
  }
  if(r.lesson.id==='T01')return m.maxHeight>=250&&m.unload>=.5&&m.initialClosure>=60&&m.window>=1.2;
  const safeExit=g.range>1800&&g.range<5000&&g.closure< -15&&relativeFlight(r.foe,r.me).ata>60&&r.me.speed>150;
  m.escape= safeExit?(m.escape||0)+dt:0;
  return m.reversals>=2&&m.overshoot&&(m.window>=1.2||m.escape>=2);
}
function cue(r) {
  if(r.result)return {goal:r.result.success?'機動確認 · CLEAR':'本次未通過',readout:`用時 ${Math.round(r.t)} 秒`,tip:'正在準備本次數據結算',state:r.result.success?'good':'warn'};
  const m=r.d.m,g=relativeFlight(r.me,r.foe),id=r.lesson.id;
  if(r.waiting)return {goal:'完成；按下方按鍵重置情境',readout:`${Math.round(r.me.speed*3.6)}km/h · 峰值${m.maxG.toFixed(1)}G`,tip:'綠線是本次航跡；下一段由你操縱',state:'good'};
  if(r.phase.id==='challenge')return {goal:'自主挑戰：完成機動與位置改善',readout:id==='A01'?`爬升 ${Math.round(m.maxHeight)}m · 滾轉 ${Math.round(m.halfRoll)}°`:`${Math.round(g.range)}m · 接近 ${Math.round(g.closure*3.6)}km/h`,tip:r.me.speed<100?'低能量：卸載、先救速度':'觀察 HUD，選擇自己的操作時機',state:r.me.speed<100?'warn':'neutral'};
  let tip;
  if(r.me.speed<100)tip='速度低：卸載、加速，別再拉緊';
  else if(id==='A01')tip=!m.vertical?'機翼水平，約 4–5G 拉起':!m.inverted?'持續半筋斗，倒飛反向後再滾轉':m.halfRoll<140?'卸載，半滾轉；橫向回中停止滾轉':'機翼朝上，小幅修 FPM 至 0°';
  else if(id==='T01')tip=m.maxHeight<250?'接近太快：先以約 3G 拉起爬升':g.ata>35?r.pick('側推協調轉彎；前推降低航跡','滾向目標後方，再拉回尾後'):g.closure>35?'收油，別讓接近率再增加':'窗口看位置與接近率，不只看機頭';
  else tip=m.reversals<2?r.pick('按住 LOOK 看追兵，再交替側推反轉','LOOK 看追兵；反向滾轉再拉'):!m.overshoot?'保持交替反轉，提早管理接近率':'它過去了：追尾後，或帶速度安全脫離';
  return {goal:`${r.phase.id==='demonstration'?'KITE 示範 · 勿操縱':'引導練習 · 由你操縱'}`,readout:id==='A01'?`+${Math.round(m.maxHeight)}m · ${Math.round(r.kmh)}km/h · ${r.g.toFixed(1)}G`:id==='T01'?`${Math.round(g.range)}m · ${Math.round(g.closure*3.6)}km/h · ${r.g.toFixed(1)}G`:`${Math.round(g.range)}m · ${Math.round(g.closure*3.6)}km/h · 反轉 ${m.reversals}`,tip,state:r.me.speed<100?'warn':'neutral'};
}
function phase(id) {
  return {id,
    enter(r){resetScenario(r);if(id==='demonstration'){
      const demo=new ManeuverPilot(r.me,r.foe,r.lesson.id,r.control);
      const pc=new PlayerController(r.me,demo.input,{assist:r.assisted,invert:false});
      r.demoController={update(dt){demo.update(dt);return pc.update(dt);}};
    }},
    say:r=>id==='demonstration'?'現在由 KITE 操縱示範機。看速度、高度與軌跡。':id==='guided'?'情境已重置。換你飛；我會依你的狀態提醒。':'同一個情境，這次由你判斷時機。',
    progress:r=>Math.min(1,r.d.m.window/(r.lesson.id==='A01'?1:1.2)),
    update(r,dt){
      const data=measure(r,dt),m=data.m;
      if(!r.foe.dormant&&!r.foe.alive)return {fail:`訓練目標已離場（${r.foe.deathCause==='crash'?'墜落':'越界'}），本次未完成。${advancedFailure(r)}`} ;
      if(success(r,dt,data)){
        r.notes[id]=structuredClone(m);
        if(id==='challenge')return 'done';
        r.flash('機動確認 · 檢視航跡再繼續','#7dffb0');
        r.say(r.lesson.id==='A01'?`反向完成，爬升 ${Math.round(m.maxHeight)}m。`:r.lesson.id==='T01'?`尾後窗口穩住了，接近 ${Math.round(m.end.closure*3.6)}km/h。`:`反轉 ${m.reversals} 次，攻防位置已改變。`,{urgent:true});
        r.waiting=true;return;
      }
      if(id!=='challenge'){
        if(r.me.speed<100)r.coachOnce('low',r.lesson.id==='A01'?'速度不足。先卸載、把機頭放低，別硬過頂。':r.lesson.id==='T01'?'速度不足。先卸載，別把高度交易變成失速。':'速度不足，先卸載。剪刀剪掉的是接近率，別把自己也剪掉。',{urgent:true});
        if(r.lesson.id==='T01'&&m.maxHeight>250&&m.unload>=.5)r.coachOnce('zoom','高度存好了。現在看接近率，從高處切回。');
        if(r.lesson.id==='T02'&&m.overshoot)r.coachOnce('cross','追兵已穿過前方。保留速度，換到它尾後。',{urgent:true});
        if(r.lesson.id==='A01'&&m.inverted)r.coachOnce('top','已倒飛反向。卸載，半滾轉；高度不是免費的。',{urgent:true});
        if(m.badFire>.2)r.coachOnce('shot','先拿到位置。子彈不能替你完成機動。',{urgent:true});
      }
      if(r.phaseT>r.lesson.attemptLimit||m.slowNow>8||m.badFire>2)return {fail:advancedFailure(r)};
    },
  };
}
function setup(r) {
  r.requestAdvance=()=>{if(!r.waiting||r.result)return false;r.waiting=false;r.next();return true;};
  r.replayDemo=()=>{if(r.result||!r.waiting)return false;r.waiting=false;r.phaseIdx=-1;r.next();return true;};
}
function debrief(r,ok) {
  const m=r.notes.challenge||r.d.m,g=m.end||{},id=r.lesson.id;
  return {good:ok?[id==='A01'?'半筋斗、倒飛、半滾轉與穩定反向皆由飛行狀態確認。':id==='T01'?'高度交易後，實際接近率與尾後窗口改善。':'交替反轉後，追兵確實穿越前方，並取得反咬或安全脫離。']:[],
    improve:ok?['再試一次：用較少 G、較少速度損失完成同樣的位置改善。']:[advancedFailure(r)],
    stats:[['速度損失',`${Math.round((m.entrySpeed-(g.speed||r.me.speed))*3.6)} km/h`],['能量高度 Δ',`${Math.round((g.energy||specificEnergy(r.me))-m.entryEnergy)} m`],['最高爬升',`${Math.round(m.maxHeight)} m`],['最大 G',m.maxG.toFixed(1)],
      [id==='A01'?'倒飛後滾轉':'有效反轉',id==='A01'?`${Math.round(m.halfRoll)}°`:`${m.reversals} 次`],['接近率',id==='A01'?'—':`${Math.round(m.initialClosure*3.6)} → ${Math.round((g.closure||0)*3.6)} km/h`],[id==='A01'?'穩定反向':'尾後窗口',`${m.bestWindow.toFixed(1)} s`],['過度拉 G',`${m.fullG.toFixed(1)} s >7G`]],
    closing:ok?'確認通過。漂亮的機動不是畫得圓，是結束時還有選擇。':'保留這次數據。下一趟只改一件事，我等你。'};
}
const common={advanced:true,setup,crashReason:r=>`墜海。${advancedFailure(r)}`,rules:{weapons:true,missiles:false,playerDamage:0},phases:[phase('demonstration'),phase('guided'),phase('challenge')],guidance:cue,debrief,
  grade(r){const m=r.notes.challenge;return m.minSpeed>130&&m.fullG<3?'S':m.minSpeed>100?'A':'B';}};
export const ADVANCED_LESSONS=[{
  ...common,id:'A01',no:'A01',title:'殷麥曼轉彎',en:'IMMELMANN',attemptLimit:45,
  principle:'半筋斗先反向並換取高度，倒飛後卸載、半滾轉恢復正飛。不是爬升中直接水平轉頭。',
  real:'真實原理：進場能量、垂直面拉起與頂點滾轉共同決定結果。這是機動概念教學，不是真機特技操作檢查單。',
  model:'模型：共用 G／阻力／速度與四元數姿態，可近似過頂與倒飛；無完整攻角、尾旋或倒飛供油。規則：3000m／1008km/h 起始、訓練不受武器損傷；只有 Expert 開放。',
  goals:['看 KITE 用同一套物理示範','引導練習：半筋斗 → 倒飛反向 → 半滾轉','自主挑戰：爬升≥600m、反向±15°，穩定航跡與機翼 1 秒'],
  intro:['今天把速度存成高度，再把機頭帶回來。少做半滾轉，回場時塔台會先看到你的肚子。'],
},{
  ...common,id:'T01',no:'T01',title:'高悠悠機動',en:'HIGH YO-YO',attemptLimit:65,
  principle:'接近過快時爬出目標轉彎平面，減少水平追趕，再從高處切回尾後。目標是改善位置，不是追求最高。',
  real:'真實 BFM 原理：控制接近率、角度與能量；過高的 Yo-Yo 也可能失去接敵。沒有放諸所有空戰的固定秒數。',
  model:'模型：訓練敵機以正常 AI 升力控制器轉彎，沒有軌道鎖定。Assisted 以協調平轉近似，需先爬升，再側推並前推修低航跡；自由升力向量控制請用 Expert。訓練武器不造成傷害。',
  goals:['初始接近率約 324km/h，觀察過頭風險','爬升≥250m，有低 G 卸載爬升','尾後80–1400m、ATA<18°、偏離機尾<50°、接近率±126km/h，連續1.2秒'],
  intro:['你比它快，暫時是好消息。一直追它現在的位置，下一句就會是「它在你後面」。'],
},{
  ...common,id:'T02',no:'T02',title:'防禦剪刀機動',en:'DEFENSIVE SCISSORS',attemptLimit:55,
  principle:'交替轉向、反轉與速度管理，讓追兵前衝；反轉後爭取尾後或帶能量脫離。只拉滿 G 不等於防禦。',
  real:'真實 BFM 原理：剪刀依賴相對運動與反轉時機；低能量剪刀可能把自己困住，且不保證能擺脫有經驗的攻擊者。',
  model:'模型：對手是既有 ChaserBot 純追擊 AI，不讀玩家輸入，同物理、武器禁用。規則要求兩次實際左右坡度反轉、追兵穿越起始航向的前方，再反咬或安全脫離。非完整三維滾剪刀。',
  goals:['從650m尾隨、追兵較快的不利局面開始','至少兩次有效反轉，讓追兵確實穿越前方','取得連續1.2秒尾後窗口；或距離>1.8km、追兵機頭偏離>60°並帶速度脫離2秒'],
  intro:['後面那位很急。讓他先到前面，但別把速度全送給他——你還得有本錢離開。'],
}];
