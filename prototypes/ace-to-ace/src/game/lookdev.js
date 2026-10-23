// Ace to Ace R2: painted environment + restrained continuous airframe lighting.
// One forward pass, with no extra render targets or full-screen post effects.
export const SKY_HORIZON = [0.76, 0.82, 0.88];
export const FOG_HEX = 0xc2d1e0;
export const SUN_VECTOR = [-0.64, 0.30, -0.69];
export const INK_HEX = 0x71859a;
export const INK_WIDTH = 0.24; // CSS px, independent of adaptive DPR

const PAINT = `
  float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
  float noise(vec2 p){ vec2 i=floor(p), f=fract(p), u=f*f*(3.0-2.0*f);
    return mix(mix(hash(i),hash(i+vec2(1,0)),u.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),u.x),u.y); }
`;
// This painting has an authored horizon, rather than photographic HDR mapping.
const PAINTED_SKY = `
  uniform sampler2D skyMap;
  vec3 paintedSky(vec3 ray){
    vec3 d=normalize(ray);
    float u=fract(atan(d.z,d.x+0.000001)/6.2831853+0.99);
    float v=clamp(0.18+sqrt(max(d.y,0.0))*0.80,0.18,0.98);
    vec3 c=texture2D(skyMap,vec2(u,v)).rgb;
    // End the authored panorama in a quiet clear-air sector. Mirroring the
    // two painted edges would create an obvious chevron when turning through it.
    float seam=1.0-smoothstep(0.0,0.075,min(u,1.0-u));
    vec3 clearAir=mix(vec3(0.76,0.82,0.88),vec3(0.28,0.47,0.70),smoothstep(0.02,0.80,d.y));
    c=mix(c,clearAir,seam);
    c=mix(c,vec3(0.25,0.43,0.66),smoothstep(0.82,0.99,d.y));
    // Dissolve the image's low edge rather than stretching it below the horizon.
    c=mix(vec3(0.76,0.82,0.88),c,smoothstep(-0.015,0.055,d.y));
    return c;
  }
`;
export const SKY_VS = `
  varying vec3 vDir;
  void main(){ vDir=position; vec4 p=projectionMatrix*modelViewMatrix*vec4(position,1); gl_Position=p.xyww; }
`;
export const SKY_FS = `
  varying vec3 vDir; uniform vec3 sunDir; uniform vec3 horizon;
  ${PAINTED_SKY}
  void main(){
    vec3 d=normalize(vDir), col=paintedSky(d);
    float solar=max(dot(d,sunDir),0.0);
    col=mix(col,vec3(0.98,0.86,0.70),pow(solar,24.0)*0.12);
    col=mix(col,vec3(1.0,0.97,0.86),smoothstep(0.99986,0.99994,solar)*0.55);
    col=mix(col,horizon,(1.0-smoothstep(0.0,0.08,d.y))*0.26);
    gl_FragColor=vec4(col,1);
  }
`;
export const SEA_VS = `
  varying vec3 vWorld;
  void main(){ vec4 w=modelMatrix*vec4(position,1); vWorld=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }
`;
export const SEA_FS = `
  varying vec3 vWorld; uniform vec3 camPos; uniform float time; uniform vec3 sunDir;
  uniform vec3 fogColor; uniform float fogNear; uniform float fogFar;
  ${PAINT}
  ${PAINTED_SKY}
  void main(){
    vec2 p=vWorld.xz; float d=length(vWorld-camPos);
    vec3 V=normalize(camPos-vWorld), R=reflect(-V,vec3(0,1,0));
    float wash=noise(p*0.00018)*0.65+noise(p*0.00047)*0.35;
    vec3 deep=mix(vec3(0.075,0.23,0.34),vec3(0.16,0.35,0.43),wash);
    float fres=pow(1.0-clamp(V.y,0.0,1.0),3.0);
    vec3 reflected=paintedSky(R);
    // Broad reflected sky values replace the R1 directional brush bars.
    vec3 col=mix(deep,reflected,0.20+fres*0.46);
    float solar=max(dot(R,sunDir),0.0), road=pow(solar,72.0);
    float footprint=max(length(dFdx(p)),length(dFdy(p)));
    float detail=1.0-smoothstep(4.0,40.0,footprint);
    float shimmer=noise(p*0.008+vec2(time*0.018,0.0));
    col=mix(col,vec3(0.99,0.89,0.70),road*(0.34+smoothstep(0.48,0.78,shimmer)*detail*0.32));
    col+=vec3(0.11,0.075,0.035)*pow(solar,12.0);
    float ripple=pow(noise(p*0.035+time*0.04),12.0);
    col+=vec3(0.10,0.14,0.15)*ripple*(1.0-smoothstep(250.0,1500.0,d))*detail;
    vec3 ray=normalize(vWorld-camPos);
    vec3 haze=mix(fogColor,paintedSky(vec3(ray.x,0.0,ray.z)),0.72);
    col=mix(col,haze,smoothstep(fogNear,fogFar,d));
    gl_FragColor=vec4(col,1);
  }
`;
export const CLOUD_VS = `
  attribute vec2 aTile; uniform vec3 camPos;
  varying vec2 vUv; varying vec3 vWorld;
  void main(){
    vec3 center=(modelMatrix*instanceMatrix*vec4(0,0,0,1)).xyz;
    vec3 toCam=normalize(camPos-center+vec3(0,0,0.0001));
    vec3 right=cross(vec3(0,1,0),toCam);
    if(length(right)<0.02) right=vec3(viewMatrix[0][0],viewMatrix[1][0],viewMatrix[2][0]);
    right=normalize(right);
    vec3 up=normalize(cross(toCam,right));
    vec2 size=vec2(length(instanceMatrix[0].xyz),length(instanceMatrix[1].xyz));
    vWorld=center+right*position.x*size.x+up*position.y*size.y;
    vUv=uv*0.5+aTile;
    gl_Position=projectionMatrix*viewMatrix*vec4(vWorld,1);
  }
`;
export const CLOUD_FS = `
  uniform sampler2D cloudMap; uniform vec3 camPos; uniform vec3 fogColor;
  uniform float fogNear; uniform float fogFar;
  varying vec2 vUv; varying vec3 vWorld;
  ${PAINTED_SKY}
  void main(){
    vec4 paint=texture2D(cloudMap,vUv);
    float d=length(vWorld-camPos);
    float a=paint.a*smoothstep(350.0,1500.0,d)*0.72;
    if(a<0.025) discard;
    vec3 background=paintedSky(vWorld-camPos);
    vec3 haze=mix(fogColor,background,0.62);
    float edge=(1.0-smoothstep(0.18,0.88,paint.a))*0.72;
    vec3 col=mix(paint.rgb,background,edge);
    col=mix(col,haze,smoothstep(fogNear,fogFar,d)*0.60);
    gl_FragColor=vec4(col,a*(1.0-smoothstep(fogNear,fogFar,d)*0.20));
  }
`;
export const AIRFRAME_VS = `
  attribute vec3 smoothNormal;
  varying vec3 vPaint; varying vec3 vNormal; varying vec3 vEye; varying vec3 vWorldNormal;
  #include <fog_pars_vertex>
  void main(){
    vPaint=color;
    // Keep flat wing planes while smoothing the fuselage shoulders.
    float curve=0.65*(1.0-pow(abs(normal.y),6.0));
    vec3 n=normalize(mix(normal,smoothNormal,curve));
    vNormal=normalize(normalMatrix*n); vWorldNormal=normalize(mat3(modelMatrix)*n);
    vec4 mvPosition=modelViewMatrix*vec4(position,1);
    vEye=-mvPosition.xyz; gl_Position=projectionMatrix*mvPosition;
    #include <fog_vertex>
  }
`;
export const AIRFRAME_FRAGMENT = `
  uniform vec3 sunDir; uniform vec3 tint;
  varying vec3 vPaint; varying vec3 vNormal; varying vec3 vEye; varying vec3 vWorldNormal;
  #include <fog_pars_fragment>
  void main(){
    vec3 N=normalize(vNormal), V=normalize(vEye);
    vec3 L=normalize((viewMatrix*vec4(sunDir,0)).xyz);
    float l=dot(N,L);
    // Continuous warm/cool areas with a broad, gentle terminator.
    vec3 shade=mix(vec3(0.33,0.44,0.64),vec3(0.70,0.80,0.94),smoothstep(-0.65,0.35,l));
    shade=mix(shade,vec3(1.15,1.06,0.90),smoothstep(0.04,0.88,l));
    vec3 col=vPaint*shade;
    float skyFacing=clamp(normalize(vWorldNormal).y*0.5+0.5,0.0,1.0);
    float fres=pow(1.0-max(dot(N,V),0.0),3.0);
    col+=vPaint*vec3(0.12,0.19,0.30)*skyFacing*(0.25+fres*0.65);
    float dark=1.0-smoothstep(0.025,0.085,dot(vPaint,vec3(0.21,0.72,0.07)));
    float shoulder=pow(max(dot(N,normalize(L+V)),0.0),mix(28.0,64.0,dark));
    col+=vec3(0.84,0.78,0.65)*shoulder*mix(0.11,0.54,dark)*smoothstep(-0.10,0.45,l);
    float rim=smoothstep(0.86,0.99,1.0-max(dot(N,V),0.0))*smoothstep(0.0,0.5,l);
    col+=vec3(0.30,0.24,0.15)*rim*0.18;
    col=mix(col,vec3(0.10,0.24,0.34),dark*fres*0.30);
    gl_FragColor=vec4(col*tint,1);
    #include <fog_fragment>
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;
