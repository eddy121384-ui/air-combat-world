import assert from 'node:assert/strict';
export async function checkTilt({page,iphone,shot,report}) {
  report.perf.tilt=[];
  for(const width of [812,667])for(const flight of ['arcade','tactical'])for(const control of ['assisted','expert']) {
    const {ctx,p}=await page({...iphone,viewport:{width,height:375}},`?mode=${flight}&control=${control}&seed=41`,'tilt');
    await p.waitForFunction(()=>window.__game?.mode==='title');
    await p.evaluate(()=>{
      window.addEventListener('deviceorientation',e=>{if(e.isTrusted)e.stopImmediatePropagation();},true); // isolate the controlled synthetic stream from headless hardware
      const g=window.__game;window.__sensorClock=performance.now();g.tilt.now=()=>window.__sensorClock;
      window.__sensorAngle=90;Object.defineProperty(screen.orientation,'angle',{configurable:true,get:()=>window.__sensorAngle});
      window.__permissionCalls=[];
      DeviceOrientationEvent.requestPermission=()=>{window.__permissionCalls.push(navigator.userActivation.isActive);return Promise.resolve('granted');};
      for(const [k,v] of Object.entries({'--sal':'34px','--sar':'34px','--sab':'21px'}))document.documentElement.style.setProperty(k,v);
    });
    const emit=async(beta,gamma,n=1,step=false)=>p.evaluate(({beta,gamma,n,step})=>{
      const g=window.__game;
      for(let i=0;i<n;i++) {window.__sensorClock+=1000/60;
        window.dispatchEvent(new DeviceOrientationEvent('deviceorientation',{beta,gamma,alpha:0}));
        g.tilt.tick();if(step)g.match.step(1/60);
      }
      return {axes:g.input.axes(),state:g.tilt.state,source:g.input.inputDevice};
    },{beta,gamma,n,step});
    const probe=()=>p.evaluate(async()=>{
      const g=window.__game,b=g.match?.blue,A=await import('/src/sim/aircraft.js');
      return {axes:g.input.axes(),state:g.tilt.state,active:g.tilt.active,source:g.input.inputDevice,
        bank:b?A.bankAngle(b)*180/Math.PI:0,power:[g.input.throttle(),g.input.boost(),g.input.brake()],
        pose:b?JSON.stringify([b.pos,b.vel,b.q,b.speed]):null};
    });
    await p.tap('#btnTitleSettings');await p.tap('[data-input-device="tilt"]');
    await p.tap('#btnTiltEnable');await p.waitForFunction(()=>window.__game.tilt.state==='waiting');
    assert.deepEqual(await p.evaluate(()=>window.__permissionCalls),[true],'permission directly in real user gesture');
    assert.deepEqual((await emit(0,-40)).axes,{x:0,y:0,yaw:0},'current grip calibration');
    await p.tap('#btnSettingsApply');assert.equal((await probe()).active,false,'title does not retain sensor listener');
    await p.tap('#btnStart');await p.evaluate(()=>window.__game.setTimeScale(0));
    if(width===667&&flight==='arcade'&&control==='expert')await p.waitForTimeout(2600);
    await emit(0,-40);assert.equal((await probe()).source,'tilt',JSON.stringify(await probe()));
    assert.ok(await p.locator('#stickZone').isHidden());
    const before=await probe();await emit(12,-50,15);const tilted=await probe();
    assert.ok(tilted.axes.x>.35&&tilted.axes.y>.2,'landscape sensor mapping');
    assert.equal(tilted.pose,before.pose,'orientation only commands input, never writes aircraft state');
    await emit(.5,-40);assert.deepEqual((await probe()).axes,{x:0,y:0,yaw:0},'noise deadzone centres immediately');
    await emit(14,-40,15);await p.tap('#tiltCalibrate');
    assert.deepEqual((await probe()).axes,{x:0,y:0,yaw:0},'actual CAL button resets comfortable grip');
    await emit(14,-40);assert.equal((await probe()).axes.x,0);
    // Both landscape directions reset the reference; no old-axis jump.
    await p.evaluate(()=>{window.__sensorAngle=270;screen.orientation.dispatchEvent(new Event('change'));});
    assert.equal((await probe()).state,'waiting');await emit(0,40);await emit(-12,52,15);
    assert.ok((await probe()).axes.x>.35&&(await probe()).axes.y>.35);
    await p.evaluate(()=>{window.__sensorAngle=90;screen.orientation.dispatchEvent(new Event('change'));});await emit(0,-40);
    await p.setViewportSize({width:width===812?667:812,height:375});
    await p.waitForFunction(()=>window.__game.tilt.state==='waiting');
    assert.equal((await probe()).state,'waiting','landscape resize suspends old axes and restarts a fresh reference');
    assert.deepEqual((await probe()).axes,{x:0,y:0,yaw:0});await emit(0,-40);
    assert.equal((await probe()).source,'tilt','resizing does not silently abandon an enabled sensor');
    await p.setViewportSize({width,height:375});await p.waitForFunction(()=>window.__game.tilt.state==='waiting');await emit(0,-40);
    // Full authority -> real flight, then neutral: Expert stays banked, Assisted rolls out.
    for(let n=0;n<100;n++){await emit(20,-40,1,true);if((await probe()).bank>=58)break;}
    const banked=await probe();assert.ok(banked.bank>=58&&banked.bank<70,JSON.stringify({width,flight,control,banked}));
    await emit(0,-40,30,true);const neutral=await probe();
    assert.deepEqual(neutral.axes,{x:0,y:0,yaw:0});
    if(control==='expert')assert.ok(Math.abs(neutral.bank-banked.bank)<10,'Expert neutral is not auto-level');
    else assert.ok(Math.abs(neutral.bank)<Math.abs(banked.bank)-15,'Assisted rolls out');
    await p.tap('[data-btn="level"]');await emit(12,-40,15,true);
    assert.equal(await p.evaluate(()=>window.__game.input.levelAssist.active),false,'sensor manual override cancels LVL');
    // Other controls remain touch-owned and power independent.
    await p.tap('[data-btn="boost"]');const throttle=await p.locator('#throttleTrack').boundingBox();
    const cdp=await ctx.newCDPSession(p),touch=(type,points)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points});
    const pedal=await p.locator('[data-btn="yawRight"]').boundingBox(),brk=await p.locator('[data-btn="brake"]').boundingBox();
    await touch('touchStart',[{x:pedal.x+25,y:pedal.y+25,id:1},{x:brk.x+25,y:brk.y+20,id:2}]);
    const held=await probe();assert.equal(held.axes.yaw,1);assert.deepEqual(held.power,[.72,true,true]);
    await touch('touchEnd',[]);assert.deepEqual((await probe()).power,[.72,true,false]);
    await touch('touchStart',[{x:throttle.x+20,y:throttle.y+60,id:3}]);await touch('touchEnd',[]);
    assert.ok((await probe()).power[0]<.6,'latched throttle remains available');
    if(width===667&&flight==='arcade'&&control==='expert')await shot(p,'27-tilt-flight-safe-area');
    await p.tap('#pauseBtn');assert.equal((await probe()).active,false);assert.deepEqual((await probe()).axes,{x:0,y:0,yaw:0});
    await p.tap('#btnPauseSettings');await p.tap('#tiltInvertX');await p.tap('#tiltInvertY');
    await p.locator('#tiltSmoothing').evaluate(el=>{el.value='0';el.dispatchEvent(new Event('input',{bubbles:true}));});
    await p.tap('#btnTiltEnable');await emit(0,-40);await emit(30,-70);
    assert.deepEqual((await probe()).axes,{x:-1,y:-1,yaw:0},'UI inversions, saturation and smoothing setting apply');
    if(width===667&&flight==='arcade'&&control==='expert')await shot(p,'28-tilt-settings-safe-area');
    await p.tap('#btnSettingsApply');await p.evaluate(()=>window.__game.setTimeScale(0));await emit(0,-40);await emit(12,-40);
    await p.evaluate(()=>window.dispatchEvent(new Event('blur')));assert.equal((await probe()).active,false);
    await p.tap('#btnResume');await emit(0,-40);await emit(12,-40);
    await p.evaluate(()=>{window.__sensorClock+=1600;window.__game.tilt.tick();});
    assert.equal((await probe()).state,'stale');assert.deepEqual((await probe()).axes,{x:0,y:0,yaw:0});
    assert.ok(await p.locator('#stickZone').isVisible(),'dropout falls back to real virtual stick');
    await touch('touchStart',[{x:150,y:260,id:4}]);await touch('touchMove',[{x:185,y:260,id:4}]);
    assert.ok((await probe()).axes.x>0);await touch('touchEnd',[]);
    await p.tap('#pauseBtn');await p.tap('#btnPauseSettings');
    await p.tap('#tiltInvertX');await p.tap('#tiltInvertY');await p.tap('#btnTiltEnable');await emit(0,-40);await p.tap('#btnSettingsApply');
    for(const id of ['L01','L02']) {
      await p.evaluate(id=>{window.__game.startLesson(id);window.__game.setTimeScale(0);},id);await emit(0,-40);
      await p.evaluate(()=>{const g=window.__game;g.hud.msgs=[];g.lesson.tickRadio(0);g.hud.radioLayout=null;});
      await p.waitForFunction(()=>window.__game.hud.radioLayout);
      const radio=await p.evaluate(()=>({text:window.__game.hud.radio.text,layout:window.__game.hud.radioLayout}));
      assert.ok(!radio.text.includes('放手'),'active TILT gets grip-neutral instructions');
      assert.ok(radio.layout.fontPx>=14&&radio.layout.lines.length<=2,'TILT radio remains readable');
      if(id==='L01')assert.match(radio.text,/校準握姿/);
      await p.tap('#pauseBtn');assert.equal((await probe()).active,false);
    }
    await p.tap('#btnPauseSettings');await p.tap('[data-input-device="stick"]');await p.tap('#btnSettingsApply');
    assert.equal((await probe()).active,false);assert.ok(await p.locator('#stickZone').isVisible(),'device switch releases the sensor');
    await p.tap('#pauseBtn');await p.tap('#btnPauseSettings');await p.tap('[data-input-device="tilt"]');await p.tap('#btnSettingsApply');
    await p.reload();await p.waitForFunction(()=>window.__game?.mode==='title');
    assert.equal(await p.evaluate(()=>window.__game.settings.inputDevice),'tilt');
    assert.equal((await probe()).active,false,'stored preference never assumes permission');
    await p.tap('#btnTitleSettings');await p.tap('#btnTiltEnable'); // Chromium permissionless API; still waits for data
    await p.tap('#btnSettingsCancel');assert.equal((await probe()).active,false,'cancel does not leak listener');
    report.perf.tilt.push({width,flight,control,banked:banked.bank,neutral:neutral.bank,passed:true});
    await ctx.close();
  }
  // Browser permission refusal, thrown request and absent hardware all use stick.
  for(const failure of ['denied','reject','unavailable','insecure']) {
    const {ctx,p}=await page(iphone,'','tilt-'+failure);await p.waitForFunction(()=>window.__game);
    await p.evaluate(failure=>{
      if(failure==='unavailable')Object.defineProperty(window,'DeviceOrientationEvent',{value:undefined,configurable:true});
      else if(failure==='insecure')Object.defineProperty(window,'isSecureContext',{value:false,configurable:true});
      else DeviceOrientationEvent.requestPermission=()=>failure==='reject'?Promise.reject(Error('denied')):Promise.resolve('denied');
    },failure);
    await p.tap('#btnTitleSettings');await p.tap('[data-input-device="tilt"]');await p.tap('#btnTiltEnable');
    await p.waitForFunction(()=>['denied','unavailable','insecure'].includes(window.__game.tilt.state));
    assert.equal(await p.evaluate(()=>window.__game.tilt.active),false);
    await p.tap('#btnSettingsApply');await p.tap('#btnStart');
    assert.ok(await p.locator('#stickZone').isVisible());assert.deepEqual(await p.evaluate(()=>window.__game.input.axes()),{x:0,y:0,yaw:0});
    await ctx.close();
  }
}
