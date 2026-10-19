// Opus Sky shaders. Display-space colour like R2 lookdev (no tone mapping, no post chain).
// GLSL1 syntax: three.js upgrades ShaderMaterial to GLSL ES 3.00 on WebGL2 and maps
// gl_FragDepthEXT to gl_FragDepth.

// R2 painted panorama mapping, reproduced verbatim so the accepted far art is unchanged.
export const PAINTED_SKY = `
  uniform sampler2D skyMap;
  vec3 paintedSky(vec3 ray){
    vec3 d=normalize(ray);
    float u=fract(atan(d.z,d.x+0.000001)/6.2831853+0.99);
    float v=clamp(0.18+sqrt(max(d.y,0.0))*0.80,0.18,0.98);
    vec3 c=texture2D(skyMap,vec2(u,v)).rgb;
    float seam=1.0-smoothstep(0.0,0.075,min(u,1.0-u));
    vec3 clearAir=mix(vec3(0.76,0.82,0.88),vec3(0.28,0.47,0.70),smoothstep(0.02,0.80,d.y));
    c=mix(c,clearAir,seam);
    c=mix(c,vec3(0.25,0.43,0.66),smoothstep(0.82,0.99,d.y));
    c=mix(vec3(0.76,0.82,0.88),c,smoothstep(-0.015,0.055,d.y));
    return c;
  }
`;

// Camera-in-cloud fog. Density comes from the same puffs on the CPU each frame; the
// outward direction lets the clear side of a cloud edge stay clearer than the inside.
export const CLOUD_FOG = `
  uniform vec4 uFog;      // rgb colour, sigma (1/m)
  uniform vec4 uFogDir;   // outward xyz, directional weight
  uniform vec3 uFogGlow;  // forward-scatter tint toward the sun
  uniform float uFogRange; // metres of mist actually around the camera (short once you are out)
  vec3 cloudFog(vec3 col, vec3 ray, float dist, vec3 sun){
    if(uFog.w<=0.0) return col;
    float side=smoothstep(-0.1,0.85,dot(ray,uFogDir.xyz))*uFogDir.w;
    float sigma=uFog.w*mix(1.0,0.22,side);
    float f=1.0-exp(-sigma*min(dist,uFogRange));
    vec3 fogCol=uFog.rgb+uFogGlow*pow(max(dot(ray,sun),0.0),5.0);
    return mix(col,fogCol,f);
  }
`;

// Value noise from a baked, tiling 64³ texture (period 32): one fetch instead of eight hashes.
const NOISE3 = `
  uniform mediump sampler3D uNoise;
  float noise3(vec3 p){ return texture(uNoise,p*(1.0/32.0)).r; }
`;

export const PUFF_VS = `
  attribute vec4 iA; attribute vec4 iB; attribute vec4 iC; attribute vec4 iD;
  uniform vec3 uCam; uniform vec3 uWind; uniform float uTime; uniform float uPxScale; uniform float uLodPx;
  uniform float uFogCull;   // inside cloud: billows beyond ~99% mist are not drawn at all
  varying vec3 vW;
  flat varying vec4 vA; flat varying vec4 vB; flat varying vec4 vC; flat varying vec4 vD;
  flat varying float vMode;
  void main(){
    vec3 C=iA.xyz+uWind; float r=iA.w;
    float level=floor(iD.w), seed=fract(iD.w);
    // Slow boiling of the billows: a time-lapse cumulus, never a sprite swap.
    r*=1.0+step(0.5,level)*0.03*sin(uTime*(0.21+seed*0.17)+seed*61.0);
    float sq=iD.y;
    vec3 toC=C-uCam; float d=length(toC);
    vec3 e=vec3(toC.x,toC.y/sq,toC.z); float dq=length(e)/r;   // ellipsoidal distance, 1 = surface
    // Screen-size LOD: small billows shrink continuously below ~2 px, so detail
    // grows in as you approach instead of popping.
    float px=r/max(d,1.0)*uPxScale;
    r*=level<1.5?1.0:smoothstep(uLodPx*0.35,uLodPx,px);
    vA=vec4(C,r); vB=vec4(iB.xyz+uWind,iB.w); vC=vec4(iC.xyz+uWind,iC.w); vD=iD;
    float base=iD.x;
    vMode=0.0;
    if(r<0.5||d-r>uFogCull){ gl_Position=vec4(2.0,2.0,2.0,1.0); return; }
    vec3 W;
    if(dq<1.002){
      // Inside the ellipsoid: only its flat base can be seen, from below.
      float dy=(base-C.y)/sq, disc=r*r-dy*dy;
      if(uCam.y>=base-0.5||disc<=0.0){ gl_Position=vec4(2.0,2.0,2.0,1.0); return; }
      vMode=1.0;
      float rr=sqrt(disc)*1.02;
      W=vec3(C.x+position.x*rr,base,C.z+position.y*rr);
    } else {
      vec3 dir=toC/d;
      vec3 up0=abs(dir.y)>0.98?vec3(1,0,0):vec3(0,1,0);
      vec3 right=normalize(cross(dir,up0)), up=cross(right,dir);
      // Tangent-cone cover at the centre plane, trimmed to the ellipsoid's own support along
      // the quad's vertical axis: flat cloud-sea rafts get flat quads, not wasted squares.
      float k=d/sqrt(max(d*d-r*r,1e-4*r*r))*1.03;
      float uy2=up.y*up.y, hv=sqrt(r*r*(1.0-uy2)+r*r*sq*sq*uy2);
      W=C+right*position.x*(r*k+2.0)+up*position.y*(hv*k+2.0);
    }
    vW=W;
    gl_Position=projectionMatrix*viewMatrix*vec4(W,1.0);
  }
`;

export const PUFF_FS = `
  uniform vec3 uCam; uniform vec3 uSun; uniform float uPxAngle; uniform vec2 uNearFade; uniform vec3 uWind;
  uniform vec3 cLit; uniform vec3 cWarm; uniform vec3 cShadow; uniform vec3 cDeep; uniform vec3 cBase;
  uniform vec3 cSkyShade; uniform vec3 cHalf; uniform vec3 cGlow; uniform vec3 cSilver; uniform vec3 uHorizon; uniform float uHazeDist;
  uniform vec4 uBands;    // lit edge lo/hi, mid edge lo/hi
  uniform vec4 uMix;      // puff, turret, cloud normal weights, brush strength
  uniform mat4 uProj; uniform float uBump;
  uniform sampler2D uSunDepth; uniform mat4 uSunMat; uniform vec4 uSunDepthInfo; // texel, depth range m, soft lo, soft hi
  varying vec3 vW;
  flat varying vec4 vA; flat varying vec4 vB; flat varying vec4 vC; flat varying vec4 vD;
  flat varying float vMode;
  ${PAINTED_SKY}
  ${CLOUD_FOG}
  ${NOISE3}
  void main(){
    vec3 C=vA.xyz; float r=vA.w, base=vD.x;
    vec3 rd=normalize(vW-uCam);
    vec3 P, Np; float alpha=1.0; bool flatFace=false;
    if(vMode>0.5){
      if(rd.y<=1e-4) discard;
      float t=(base-uCam.y)/rd.y; P=uCam+rd*t;
      vec3 q=P-C; q.y/=vD.y; if(dot(q,q)>r*r) discard;
      Np=vec3(0,-1,0); flatFace=true;
    } else {
      // Ray vs axis-aligned ellipsoid, solved in the space where it is a sphere of radius r.
      float sq=vD.y;
      vec3 sc3=vec3(1.0,1.0/sq,1.0);
      vec3 oc=(uCam-C)*sc3, rs=rd*sc3;
      float A=dot(rs,rs), B=dot(oc,rs);
      float tc=-B/A, m2=max(dot(oc,oc)-B*B/A,0.0), m=sqrt(m2);
      float px=max(tc,1.0)*uPxAngle;
      float edge=(r-m)/px;                // ~pixels inside the silhouette
      if(edge<-0.75) discard;
      alpha=clamp(edge+0.5,0.0,1.0);
      float t;
      if(m<r){ t=tc-sqrt((r*r-m2)/A); P=uCam+rd*t; }
      else {
        // AA fringe just outside the rim: shade the exact silhouette point on the surface,
        // otherwise the sun-depth lookup sees a point in open air and lights a halo.
        vec3 q=(oc+rs*tc)*(r/max(m,1e-3));
        P=C+q/sc3; t=dot(P-uCam,rd);
      }
      vec3 g=(P-C); Np=normalize(vec3(g.x,g.y/(sq*sq),g.z));
      if(P.y<base){
        // Flat condensation base: the cut is only visible from below.
        if(rd.y<=1e-4||uCam.y>=base) discard;
        t=(base-uCam.y)/rd.y; P=uCam+rd*t;
        vec3 q=P-C; q.y/=sq; if(dot(q,q)>r*r) discard;
        Np=vec3(0,-1,0); flatFace=true; alpha=1.0;
      }
    }
    float dist=length(P-uCam);
    vec3 L=uSun;
    vec3 dt=P-vB.xyz, dc=P-vC.xyz;
    vec3 Nt=normalize(vec3(dt.x,dt.y/(vB.w*vB.w),dt.z));
    vec3 Nc=normalize(vec3(dc.x,dc.y/(vC.w*vC.w),dc.z));
    if(flatFace){ Nt=Np; Nc=Np; }
    vec3 N=normalize(Np*uMix.x+Nt*uMix.y+Nc*uMix.z);
    float level=floor(vD.w), seed=fract(vD.w);
    // Brush wobble in world space: continuous across neighbouring billows, fixed to the cloud.
    vec3 wp=P-vC.xyz;
    float brush=noise3(wp*0.0042+seed*0.0)*0.62+noise3(wp*0.011+7.3)*0.38-0.5;
    // Smooth sun occlusion: metres behind the first sun-facing cloud surface, 5-tap PCF.
    // The billow's own chord toward the sun is removed analytically, so a single billow
    // never shadows itself into a sphere: only other billows, turrets and clouds count.
    vec3 sq3=vec3(1.0,1.0/vD.y,1.0);
    vec3 so=(P-C)*sq3, sd=L*sq3;
    float sA=dot(sd,sd), sB=dot(so,sd);
    float selfChord=flatFace?0.0:max(0.0,-2.0*sB/sA);
    vec4 sc=uSunMat*vec4(P-uWind,1.0);
    vec2 suv=sc.xy*0.5+0.5; float dR=sc.z*0.5+0.5;
    // Taps rotated by world-anchored noise: up close, shadow edges break up organically instead
    // of showing the sun map's texel staircase.
    float occ=0.0;
    float ang=noise3((P-uWind)*0.045)*6.2831;
    mat2 rot=mat2(cos(ang),sin(ang),-sin(ang),cos(ang));
    for(int k=0;k<5;k++){
      vec2 o=k==0?vec2(0):rot*vec2(k<3?1.0:-1.0,(k==1||k==3)?1.0:-1.0)*uSunDepthInfo.x*2.4;
      float dO=texture2D(uSunDepth,suv+o).r;
      occ+=smoothstep(uSunDepthInfo.z,uSunDepthInfo.w,(dR-dO)*uSunDepthInfo.y-selfChord);
    }
    occ*=0.2;
    float sunVis=1.0-occ*0.9;
    float sunL=(dot(N,L)*0.5+0.5)*sunVis+brush*uMix.w;
    // Cauliflower micro-relief: world-space noise read as a height, lit by its slope toward
    // the sun (directional derivative). Fades in under ~2.6 km; fixed to the cloud in 3D.
    float bumpFade=(1.0-smoothstep(900.0,2600.0,dist))*(flatFace?0.0:1.0);
    float relief=0.0;
    if(bumpFade>0.0){
      vec3 bq=(P-uWind)*(1.0/30.0);
      float n0=noise3(bq), n1=noise3(bq+L*0.33);
      vec3 bq2=bq*0.37+11.0;
      float m0=noise3(bq2), m1=noise3(bq2+L*0.13);
      relief=((n0-n1)*0.75+(m0-m1)*1.1)*bumpFade*uBump;
      // Fine octave only within a few hundred metres, where a wall fills the screen.
      float nearK=1.0-smoothstep(200.0,900.0,dist);
      if(nearK>0.0){ vec3 bq3=bq*2.6+5.0; relief+=(noise3(bq3)-noise3(bq3+L*0.85))*0.55*nearK*uBump; }
    }
    float lit=smoothstep(uBands.x,uBands.y,sunL);
    // The shade side is never grey: sky light from above, cooler toward the base,
    // a pink-lavender half tone where it turns toward the sun.
    // Shade is lit by the sky dome: brightest toward the zenith and the sun-side sky.
    vec3 skyDir=normalize(vec3(L.x*0.55,1.0,L.z*0.55));
    float upness=dot(N,skyDir)*0.5+0.5;
    vec3 shade=mix(cBase,cShadow,smoothstep(0.10,0.50,upness));
    shade=mix(shade,cSkyShade,smoothstep(0.50,0.95,upness));
    // Per-billow modelling eases off as a billow grows large on screen (a continuous function
    // of distance, so nothing pops); world-anchored micro-relief carries the close-up texture.
    float billowPx=r/max(dist,1.0)/uPxAngle;
    float form=(1.0-smoothstep(90.0,420.0,billowPx)*0.65)*(level<1.5?1.0:0.6);
    // In shade each billow keeps its own form: sky-lit crown, cooler underside.
    shade*=flatFace?1.0:mix(1.0-0.09*form,1.0+0.06*form,smoothstep(-0.45,0.85,dot(Np,skyDir)));
    float halfTone=smoothstep(uBands.z,uBands.x,sunL)*(1.0-lit);
    shade=mix(shade,cHalf,halfTone*0.8);
    // Against the light the body drops in value so the silver rim can carry the silhouette.
    float backLit=smoothstep(0.05,0.92,dot(rd,L));
    shade*=mix(1.0,0.83,backLit);
    vec3 col=mix(shade,cLit,lit);
    if(flatFace){
      // Cloud-sea ceiling: brighter where thin (light leaks through), darker under thick cover.
      float mott=noise3((P-uWind)*vec3(0.004,0.0,0.004))*0.6+noise3((P-uWind)*vec3(0.013,0.0,0.013))*0.4;
      col=mix(vec3(0.74,0.75,0.86),vec3(0.44,0.48,0.63),clamp(occ*1.1+(mott-0.5)*0.8,0.0,1.0));
    }
    float band=lit*(1.0-smoothstep(uBands.y,uBands.y+0.18,sunL));
    col=mix(col,cWarm,band*0.55);
    // Micro-relief modulates value inside each mass; it never moves the terminator.
    col*=1.0+relief*mix(0.22,0.34,lit)*(1.6-form*0.6);
    // Billow underside crescent: the soft shadow each bump tucks onto the mass below it.
    // Cauliflower contact shading: the side of each billow that turns into the cloud body,
    // strongest underneath, reads as the painted crevice line even in flat front light.
    float inward=smoothstep(0.25,-0.55,dot(Np,Nt));
    float tuck=inward*mix(0.55,1.0,smoothstep(0.2,-0.6,Np.y))*(level<1.5?1.0:level<2.5?0.3:0.15);
    col=mix(col,mix(cHalf,cShadow,0.35+0.65*(1.0-lit)),tuck*mix(0.26,0.42,1.0-lit)*form*(flatFace?0.0:1.0));
    // Painted vertical gradient: warm crown, cooler and a touch darker toward the base.
    float hf=clamp((P.y-base)/max(2.0*(vC.y-base),1.0),0.0,1.0);
    col*=mix(vec3(0.93,0.94,0.99),vec3(1.02,1.0,0.97),smoothstep(0.0,0.9,hf));
    // Each billow's sun-facing crown catches a little extra light.
    col=mix(col,cLit*1.03,smoothstep(0.65,0.98,dot(Np,L))*lit*0.22*(flatFace?0.0:1.0));
    // Silver lining only on the cloud mass's outer silhouette, not on every bubble.
    // Mass normals only, so internal billow outlines never light up as rings.
    float rimT=1.0-clamp(abs(dot(Nt,-rd)),0.0,1.0);
    float rimC=1.0-clamp(abs(dot(Nc,-rd)),0.0,1.0);
    float back=backLit;
    float silver=smoothstep(0.70,0.99,max(rimT,rimC))*(1.0-occ*0.5)*(flatFace?0.0:1.0);
    // Rim light belongs to the cloud's silhouette against the sky: gone when you are at its wall.
    float clearAir=(1.0-min(1.0,uFog.w*60.0))*smoothstep(250.0,900.0,dist);
    col+=cSilver*silver*back*1.1*clearAir;
    col=mix(col,cGlow,back*pow(rimC,3.0)*0.38*(1.0-lit)*(flatFace?0.3:1.0)*clearAir);
    // Aerial perspective into the R2 painting's own horizon colours.
    vec3 haze=mix(uHorizon,paintedSky(vec3(rd.x,max(rd.y,0.0)*0.3,rd.z)),0.55);
    col=mix(col,haze,(1.0-exp(-dist/uHazeDist))*0.92);
    col=cloudFog(col,rd,dist,L);
    // Condensation base reads flat but slightly ragged from the side, never a ruled line.
    if(!flatFace){
      float bn=noise3((P-uWind)*vec3(0.02,0.0,0.02)+vec3(0.0,3.7,0.0));
      alpha*=smoothstep(0.0,1.0,(P.y-base)/22.0+0.35-bn*0.9);
    }
    // Near the camera the wall breaks into world-anchored wisps instead of a screen dither.
    float nf=smoothstep(uNearFade.x,uNearFade.y,dist);
    if(nf<1.0){
      vec3 wq=(P-uWind)*0.032;
      float wisp=noise3(wq)*0.62+noise3(wq*2.7+3.1)*0.38;
      alpha*=smoothstep(wisp-0.10,wisp+0.10,nf);
    }
    #ifdef DEBUG_OCC
    col=vec3(1.0-occ,lit,0.0);
    #endif
    gl_FragColor=vec4(col,alpha);
    vec4 clip=uProj*viewMatrix*vec4(P,1.0);
    gl_FragDepthEXT=clamp(0.5*clip.z/clip.w+0.5,0.0,1.0);
  }
`;

// One-time sun-view depth of the puffs (orthographic). Sampling it gives every surface a
// smooth "how far behind the sun-facing surface am I" value: big painted light/shade masses
// and cast shadows that do not change from billow to billow.
export const SUNDEPTH_VS = `
  attribute vec4 iA; attribute vec4 iD;
  uniform vec3 uViewDir;
  varying vec3 vW; flat varying vec4 vA; flat varying vec2 vBase;
  void main(){
    vA=iA; vBase=iD.xy;
    vec3 up0=abs(uViewDir.y)>0.98?vec3(1,0,0):vec3(0,1,0);
    vec3 right=normalize(cross(uViewDir,up0)), up=cross(right,uViewDir);
    vec3 W=iA.xyz+(right*position.x+up*position.y)*iA.w*1.02;
    vW=W; gl_Position=projectionMatrix*viewMatrix*vec4(W,1.0);
  }
`;
export const SUNDEPTH_FS = `
  uniform vec3 uViewDir; uniform mat4 uProj;
  varying vec3 vW; flat varying vec4 vA; flat varying vec2 vBase;
  void main(){
    vec3 C=vA.xyz; float r=vA.w; vec3 sc3=vec3(1.0,1.0/vBase.y,1.0);
    vec3 oc=(vW-C)*sc3, rs=uViewDir*sc3;
    float A=dot(rs,rs), B=dot(oc,rs), m2=dot(oc,oc)-B*B/A;
    if(m2>r*r) discard;
    float t=-B/A-sqrt((r*r-m2)/A);
    vec3 P=vW+uViewDir*t;
    if(P.y<vBase.x) discard;
    vec4 clip=uProj*viewMatrix*vec4(P,1.0);
    gl_FragDepthEXT=clamp(0.5*clip.z/clip.w+0.5,0.0,1.0);
    gl_FragColor=vec4(1.0);
  }
`;

export const SKY_VS = `
  varying vec3 vDir;
  void main(){ vDir=position; vec4 p=projectionMatrix*modelViewMatrix*vec4(position,1); gl_Position=p.xyww; }
`;
export const SKY_FS = `
  varying vec3 vDir; uniform vec3 uSun; uniform vec3 uHorizon;
  ${PAINTED_SKY}
  ${CLOUD_FOG}
  void main(){
    vec3 d=normalize(vDir), col=paintedSky(d);
    float solar=max(dot(d,uSun),0.0);
    col=mix(col,vec3(0.98,0.86,0.70),pow(solar,24.0)*0.12);
    col=mix(col,vec3(1.0,0.97,0.86),smoothstep(0.99986,0.99994,solar)*0.55);
    col=mix(col,uHorizon,(1.0-smoothstep(0.0,0.08,d.y))*0.26);
    col=cloudFog(col,d,1e5,uSun);
    gl_FragColor=vec4(col,1);
  }
`;

export const SEA_VS = `
  varying vec3 vWorld;
  void main(){ vec4 w=modelMatrix*vec4(position,1); vWorld=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }
`;
export const SEA_FS = `
  varying vec3 vWorld; uniform vec3 uCam; uniform float uTime; uniform vec3 uSun;
  uniform vec3 uHorizon; uniform float uFogNear; uniform float uFogFar;
  uniform sampler2D shadowMap; uniform vec3 uShadow; // extent, wind x, wind z
  uniform vec3 cSeaShade;
  ${PAINTED_SKY}
  ${CLOUD_FOG}
  float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
  float noise(vec2 p){ vec2 i=floor(p), f=fract(p), u=f*f*(3.0-2.0*f);
    return mix(mix(hash(i),hash(i+vec2(1,0)),u.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),u.x),u.y); }
  void main(){
    vec2 p=vWorld.xz; float d=length(vWorld-uCam);
    vec3 V=normalize(uCam-vWorld), R=reflect(-V,vec3(0,1,0));
    float wash=noise(p*0.00018)*0.65+noise(p*0.00047)*0.35;
    vec3 deep=mix(vec3(0.075,0.23,0.34),vec3(0.16,0.35,0.43),wash);
    float fres=pow(1.0-clamp(V.y,0.0,1.0),3.0);
    vec3 col=mix(deep,paintedSky(R),0.20+fres*0.46);
    // Cloud shadows: projected along the sun from the same puffs, drifting with the wind.
    vec2 suv=(p-uShadow.yz)/uShadow.x+0.5;
    vec2 eb=min(suv,1.0-suv);
    float inside=smoothstep(0.0,0.04,min(eb.x,eb.y));
    float shade=texture2D(shadowMap,suv).r*inside;
    float solar=max(dot(R,uSun),0.0), road=pow(solar,72.0);
    float footprint=max(length(dFdx(p)),length(dFdy(p)));
    float detail=1.0-smoothstep(4.0,40.0,footprint);
    float shimmer=noise(p*0.008+vec2(uTime*0.018,0.0));
    col=mix(col,vec3(0.99,0.89,0.70),road*(0.34+smoothstep(0.48,0.78,shimmer)*detail*0.32)*(1.0-shade));
    col+=vec3(0.11,0.075,0.035)*pow(solar,12.0)*(1.0-shade);
    float ripple=pow(noise(p*0.035+uTime*0.04),12.0);
    col+=vec3(0.10,0.14,0.15)*ripple*(1.0-smoothstep(250.0,1500.0,d))*detail;
    col=mix(col,col*cSeaShade,shade*0.85);
    vec3 ray=normalize(vWorld-uCam);
    vec3 haze=mix(uHorizon,paintedSky(vec3(ray.x,0.0,ray.z)),0.72);
    col=mix(col,haze,smoothstep(uFogNear,uFogFar,d));
    col=cloudFog(col,ray,d,uSun);
    gl_FragColor=vec4(col,1);
  }
`;

// Vapour streaks: world-fixed points inside cloud density, smeared along the camera's own
// motion over a short shutter. They exist only where the puffs say there is cloud.
export const STREAK_VS = `
  attribute vec4 iP;  // world position, alpha
  uniform vec3 uCam; uniform vec3 uVel; uniform float uShutter; uniform float uWidth;
  varying vec2 vUv; varying float vAlpha;
  void main(){
    vec3 a=iP.xyz, b=iP.xyz+uVel*uShutter;
    vec3 axis=b-a; float len=length(axis);
    vec3 dirA=len>1e-3?axis/len:vec3(0,0,1);
    vec3 toCam=normalize(uCam-mix(a,b,0.5));
    vec3 side=normalize(cross(dirA,toCam)+vec3(1e-5,0,0));
    float w=uWidth*(0.6+fract(sin(dot(iP.xyz,vec3(12.9898,78.233,37.719)))*43758.5453)*0.8);
    vec3 W=mix(a,b,position.y*0.5+0.5)+side*position.x*w;
    vUv=position.xy; vAlpha=iP.w;
    gl_Position=projectionMatrix*viewMatrix*vec4(W,1.0);
  }
`;
export const STREAK_FS = `
  uniform vec3 uColor; varying vec2 vUv; varying float vAlpha;
  void main(){
    float across=exp(-vUv.x*vUv.x*3.5);
    float along=smoothstep(-1.0,-0.4,vUv.y)*(1.0-smoothstep(0.55,1.0,vUv.y));
    gl_FragColor=vec4(uColor,across*along*vAlpha);
  }
`;

// Mist clumps: isotropic soft blobs on the same world lattice as the streaks. A gaussian ball
// looks identical from every side, so a camera-facing quad is exact; they give the white-out
// inside a cloud some depth and parallax instead of a flat screen tint.
export const MIST_VS = `
  attribute vec4 iM;   // world position, packed radius(int m) + alpha fraction
  uniform vec3 uCam;
  varying vec2 vUv; varying float vAlpha; varying float vTone;
  void main(){
    float r=floor(iM.w); vAlpha=fract(iM.w);
    vec3 toC=normalize(iM.xyz-uCam);
    vec3 up0=abs(toC.y)>0.98?vec3(1,0,0):vec3(0,1,0);
    vec3 right=normalize(cross(toC,up0)), up=cross(right,toC);
    vec3 W=iM.xyz+(right*position.x+up*position.y)*r;
    vUv=position.xy; vTone=fract(sin(dot(iM.xyz,vec3(1.7,9.2,3.1)))*4375.85);
    gl_Position=projectionMatrix*viewMatrix*vec4(W,1.0);
  }
`;
export const MIST_FS = `
  uniform vec3 uLight; uniform vec3 uShade; uniform vec3 uSun; uniform vec3 uCam;
  varying vec2 vUv; varying float vAlpha; varying float vTone;
  void main(){
    float g=exp(-dot(vUv,vUv)*3.2);
    vec3 col=mix(uShade,uLight,vTone);
    gl_FragColor=vec4(col,g*vAlpha);
  }
`;
