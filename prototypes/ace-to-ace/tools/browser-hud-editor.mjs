import assert from 'node:assert/strict';
export async function checkHudEditor({page,iphone,shot,report}) {
  report.perf.hudEditor=[];
  for(const width of [812,667])for(const flight of ['arcade','tactical'])for(const control of ['assisted','expert']) {
    const {ctx,p}=await page({...iphone,viewport:{width,height:375}},`?mode=${flight}&control=${control}&seed=41&autostart=1`,'hud-editor');
    await p.waitForFunction(()=>window.__game?.mode==='playing');
    await p.evaluate(()=>{
      const g=window.__game;g.setTimeScale(0);
      for(const [k,v] of Object.entries({'--sal':'34px','--sar':'34px','--sab':'21px'}))document.documentElement.style.setProperty(k,v);
    });
    const rect=sel=>p.locator(sel).boundingBox();
    const legacy=await rect('[data-btn="gun"]');
    const cdp=await ctx.newCDPSession(p),touch=(type,pts)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:pts});
    const drag=async(key,dx,dy)=>{
      const r=await rect(`[data-edit="${key}"]`); // real CDP gesture; choose exposed edge if toolbar covers its centre
      const x=key==='stick'?r.x+r.width*.65:r.x+r.width/2,y=key==='stick'?r.y+r.height-15:r.y+r.height/2;
      await touch('touchStart',[{x,y,id:11}]);
      for(let i=1;i<=6;i++)await touch('touchMove',[{x:x+dx*i/6,y:y+dy*i/6,id:11}]);
      await touch('touchEnd',[]);
    };
    const dragRange=async(id,target)=>{
      const slider=p.locator(id);await slider.evaluate(el=>el.scrollIntoView({block:'center'}));
      const r=await slider.boundingBox(),values=await slider.evaluate(el=>({min:+el.min,max:+el.max,current:+el.value}));
      const x=value=>r.x+8+(r.width-16)*(value-values.min)/(values.max-values.min),y=r.y+r.height/2;
      await touch('touchStart',[{x:x(values.current),y,id:55}]);
      for(let i=1;i<=6;i++)await touch('touchMove',[{x:x(values.current+(target-values.current)*i/6),y,id:55}]);
      await touch('touchEnd',[]);const actual=Number(await slider.inputValue());
      assert.ok(Math.abs(actual-target)<=2,'native mobile range drag reaches requested adjustment');return actual;
    };
    const inputs=()=>p.evaluate(()=>{
      const g=window.__game,i=g.input;return {axes:i.axes(),gun:i.gun(),brake:i.brake(),boost:i.boost(),throttle:i.throttle(),presses:i.pressed.size,level:i.levelAssist.active,time:g.match.time,enabled:i.enabled};
    });
    await p.tap('#pauseBtn');await p.tap('#btnPauseHud');
    assert.equal(await p.evaluate(()=>window.__game.mode),'editing');
    const frozen=await inputs();assert.equal(frozen.enabled,false);
    await drag('gun',-60,-25);
    const moved=await rect('[data-btn="gun"]');assert.ok(Math.abs(moved.x-(legacy.x-60))<2&&Math.abs(moved.y-(legacy.y-25))<2,'real touch drag moves gun');
    await p.locator('#hudSize').fill('130');await p.locator('#hudOpacity').fill('40');
    const scaled=await rect('[data-btn="gun"]');assert.ok(Math.abs(scaled.width-109.2)<1,'130% gun size');
    assert.equal(await p.locator('[data-btn="gun"]').evaluate(el=>Number(getComputedStyle(el).opacity)),.4);
    if(width===667&&flight==='arcade'&&control==='expert'){
      const size=await dragRange('#hudSize',110);assert.ok(Math.abs((await rect('[data-btn="gun"]')).width-84*size/100)<1);
      const opacity=await dragRange('#hudOpacity',60);assert.equal(await p.locator('[data-btn="gun"]').evaluate(el=>Number(getComputedStyle(el).opacity)),opacity/100);
    }
    await p.keyboard.press('KeyW');await p.keyboard.press('KeyL');await p.keyboard.press('Space');
    assert.deepEqual(await inputs(),frozen,'editing cannot fire, change AB, move aircraft or activate LVL');
    await p.tap('#hudCancel');assert.equal(await p.evaluate(()=>window.__game.mode),'paused');
    assert.deepEqual(await rect('[data-btn="gun"]'),legacy,'cancel restores exact prior layout');
    assert.equal(await p.evaluate(()=>localStorage.getItem('ace2ace.hud.v1')),null,'cancel never persists');
    await p.tap('#btnPauseHud');await drag('gun',-60,-25);
    await p.locator('#hudSize').fill('130');await p.locator('#hudOpacity').fill('40');
    // Move the full strip, then scale it. AB/BRK retain their default relative slots.
    await p.tap('#hudFold');await drag('power',-10,35);await p.tap('#hudFold');
    await p.locator('#hudSelection').selectOption('power');await p.locator('#hudSize').fill('110');
    const power=await rect('#powerControl');assert.ok(Math.abs(power.height-247.5)<1);
    await p.tap('#hudFold');await drag('boost',25,10);await p.tap('#hudFold');
    assert.equal((await inputs()).boost,false,'dragging AB never toggles it');
    await p.locator('#hudSelection').selectOption('pause');await p.locator('#hudSize').fill('65');await p.locator('#hudOpacity').fill('20');
    const pause=await rect('#pauseBtn');assert.ok(pause.width>=40&&pause.height>=40,'menu keeps minimum usable target');
    assert.equal(await p.locator('#pauseBtn').evaluate(el=>Number(getComputedStyle(el).opacity)),.6,'menu opacity floor');
    if(width===667&&flight==='arcade'&&control==='expert')await shot(p,'29-hud-editor-safe-area');
    await p.tap('#hudSave');
    const saved=await p.evaluate(()=>JSON.parse(localStorage.getItem('ace2ace.hud.v1')));
    assert.equal(saved.version,1);assert.equal(saved.items.gun.scale,1.3);assert.equal(saved.items.gun.opacity,.4);
    for(const item of Object.values(saved.items))assert.ok(item.x>=0&&item.x<=1&&item.y>=0&&item.y<=1,'normalized centres');
    const savedGun=await rect('[data-btn="gun"]');await p.reload();await p.waitForFunction(()=>window.__game?.mode==='playing');
    await p.evaluate(()=>{window.__game.setTimeScale(0);for(const [k,v] of Object.entries({'--sal':'34px','--sar':'34px','--sab':'21px'}))document.documentElement.style.setProperty(k,v);window.dispatchEvent(new Event('resize'));});
    assert.deepEqual(await rect('[data-btn="gun"]'),savedGun,'reload restores saved position and size');
    assert.equal(await p.locator('[data-btn="gun"]').evaluate(el=>Number(getComputedStyle(el).opacity)),.4);
    // 130% persistence is verified above. This compact phone layout overlaps BRK
    // at that size; choose 90% before testing independent multi-finger gameplay.
    await p.tap('#pauseBtn');await p.tap('#btnPauseHud');
    await p.locator('#hudSelection').selectOption('gun');await p.locator('#hudSize').fill('90');await p.tap('#hudSave');await p.tap('#btnResume');
    await p.evaluate(()=>window.__game.setTimeScale(0));
    // The resized throttle uses its actual scaled thumb travel, not old pixel constants.
    const track=await rect('#throttleTrack'),handle=await rect('#throttleHandle');
    await touch('touchStart',[{x:track.x+track.width/2,y:track.y+handle.height/2,id:21}]);await touch('touchEnd',[]);
    assert.ok(Math.abs((await inputs()).throttle-1)<.02,'scaled strip reaches full throttle');
    await touch('touchStart',[{x:track.x+track.width/2,y:track.y+track.height-handle.height/2,id:22}]);await touch('touchEnd',[]);
    assert.ok((await inputs()).throttle<.02,'scaled strip reaches idle and latches');
    await p.tap('[data-btn="boost"]');assert.equal((await inputs()).boost,true);
    // Real simultaneous custom GUN + BRK remain independently owned.
    const gun=await rect('[data-btn="gun"]'),brake=await rect('[data-btn="brake"]');
    await touch('touchStart',[{x:gun.x+gun.width/2,y:gun.y+gun.height/2,id:31},{x:brake.x+brake.width/2,y:brake.y+brake.height/2,id:32}]);
    assert.ok((await inputs()).gun&&(await inputs()).brake,JSON.stringify({input:await inputs(),gun,brake,hits:await p.evaluate(({gun,brake})=>[gun,brake].map(r=>document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.outerHTML),{gun,brake})}));
    await touch('touchEnd',[{x:brake.x+brake.width/2,y:brake.y+brake.height/2,id:32}]);
    assert.equal((await inputs()).brake,false);assert.equal((await inputs()).gun,true,'other finger still holds moved gun');
    await touch('touchEnd',[]);assert.equal((await inputs()).gun,false);assert.equal((await inputs()).boost,true);
    await p.tap('#pauseBtn');await p.tap('#btnPauseHud');
    await p.tap('#hudLeft');await p.tap('#hudFold');
    const leftGun=await rect('[data-btn="gun"]'),rightStick=await rect('#stickZone');
    assert.ok(leftGun.x<width/2&&rightStick.x>=width*.45,'left-hand preset swaps thumb jobs');
    // All actual configurable targets stay inside notch/home bounds after preset.
    const bounds=await p.evaluate(()=>{
      const ed=window.__game.hudEditor;return {safe:ed.safe(),nodes:[...ed.nodes].map(([key,n])=>({key,r:n.getBoundingClientRect().toJSON()}))};
    });
    for(const {key,r} of bounds.nodes)if(!['pause','level','calibrate'].includes(key))assert.ok(r.x>=bounds.safe.x-.1&&r.y>=bounds.safe.y-.1&&r.right<=bounds.safe.x+bounds.safe.width+.1&&r.bottom<=bounds.safe.y+bounds.safe.height+.1,`${key} stays in safe bounds`);
    const centres=await p.evaluate(()=>[...window.__game.hudEditor.nodes].filter(([key])=>!['stick','power'].includes(key)).map(([key,n])=>{const r=n.getBoundingClientRect();return {key,x:r.x+r.width/2,y:r.y+r.height/2};}));
    for(const a of centres)for(const b of centres)if(a.key!==b.key)assert.ok(Math.hypot(a.x-b.x,a.y-b.y)>38,`left preset thumb targets ${a.key}/${b.key} need space`);
    // Real stick-zone drag; no flight command despite moving its interaction area.
    await drag('stick',-25,-10);assert.deepEqual((await inputs()).axes,{x:0,y:0,yaw:0});
    if(width===667&&flight==='arcade'&&control==='expert')await shot(p,'30-hud-editor-left-hand');
    await p.tap('#hudFold');await p.tap('#hudRight');assert.deepEqual(await rect('[data-btn="gun"]'),legacy,'right preset restores legacy layout');
    await p.tap('#hudReset');await p.tap('#hudSave');assert.deepEqual((await p.evaluate(()=>JSON.parse(localStorage.getItem('ace2ace.hud.v1')))).items,{});
    // TILT preference/fallback must not destroy independent HUD layout entries.
    await p.tap('#btnPauseSettings');await p.tap('[data-input-device="tilt"]');await p.tap('#btnSettingsApply');
    await p.evaluate(()=>{window.__game.setTimeScale(0);const t=window.__game.tilt;t.allowed=true;t.start();window.dispatchEvent(new DeviceOrientationEvent('deviceorientation',{beta:0,gamma:-40}));t.tick();});
    await p.waitForFunction(()=>document.querySelector('#stickZone').classList.contains('hidden'));
    await p.tap('#pauseBtn');await p.tap('#btnPauseHud');assert.ok(await p.locator('[data-edit="stick"]').isVisible(),'TILT-hidden stick remains editable');
    await p.tap('#hudFold');await drag('stick',-15,-10);await p.tap('#hudFold');await p.tap('#hudSave');
    assert.ok((await p.evaluate(()=>JSON.parse(localStorage.getItem('ace2ace.hud.v1')))).items.stick,'stick edit retained independently');
    await p.tap('#btnPauseSettings');await p.tap('[data-input-device="stick"]');await p.tap('#btnSettingsApply');
    await p.evaluate(()=>window.__game.setTimeScale(0));assert.ok(await p.locator('#stickZone').isVisible());
    // Resizing to the other phone width keeps every saved target accessible.
    await p.setViewportSize({width:width===667?812:667,height:375});
    const final=await rect('#pauseBtn');assert.ok(final.x>=34&&final.x+final.width<=((width===667?812:667)-34));
    report.perf.hudEditor.push({width,flight,control,passed:true});await ctx.close();
  }
  {
    const {ctx,p}=await page({viewport:{width:1280,height:720},hasTouch:false},'?autostart=1','hud-desktop');
    await p.waitForFunction(()=>window.__game?.mode==='playing');assert.ok(await p.locator('[data-btn="gun"]').isHidden());
    await p.click('#pauseBtn');await p.click('#btnPauseHud');assert.ok(await p.locator('[data-btn="gun"]').isVisible());
    await p.click('#hudCancel');await p.click('#btnResume');assert.ok(await p.locator('[data-btn="gun"]').isHidden(),'desktop keeps its original non-touch presentation');await ctx.close();
  }
  // Corrupt/future data falls back, title preview doesn't write academy progress.
  const {ctx,p}=await page(iphone,'','hud-storage');await p.waitForFunction(()=>window.__game);
  await p.evaluate(()=>localStorage.setItem('ace2ace.hud.v1','{"version":999,"items":{"gun":{"x":-999}}}'));
  await p.reload();await p.waitForFunction(()=>window.__game);await p.tap('#btnTitleHud');
  assert.equal(await p.evaluate(()=>window.__game.mode),'editing');
  assert.equal(await p.evaluate(()=>localStorage.getItem('ace2ace.academy.v1')),null);
  await p.tap('#hudCancel');assert.equal(await p.evaluate(()=>window.__game.mode),'title');await ctx.close();
}
