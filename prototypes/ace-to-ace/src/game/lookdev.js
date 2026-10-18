// Ace to Ace only: anime film 2D-look / NPR experiment, display-referred palettes.
// One forward pass: no render targets, bloom, screen-space outlines or LUT chain.
export const SKY_HORIZON = [0.81, 0.80, 0.78];
export const FOG_HEX = 0xcfccc7;
export const SUN_VECTOR = [-0.64, 0.34, -0.69];
export const INK_HEX = 0x38475c;
export const INK_WIDTH = 0.65; // CSS px, independent of adaptive DPR

const PAINT = `
  float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
  float noise(vec2 p){ vec2 i=floor(p), f=fract(p), u=f*f*(3.0-2.0*f);
    return mix(mix(hash(i),hash(i+vec2(1,0)),u.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),u.x),u.y); }
`;

export const SKY_VS = `
  varying vec3 vDir;
  void main(){ vDir=position; vec4 p=projectionMatrix*modelViewMatrix*vec4(position,1); gl_Position=p.xyww; }
`;
export const SKY_FS = `
  varying vec3 vDir; uniform vec3 sunDir; uniform vec3 horizon;
  ${PAINT}
  void main(){
    vec3 d=normalize(vDir);
    float h=max(d.y,0.0), facing=pow(max(dot(d,sunDir),0.0),5.0);
    vec3 col=mix(horizon,vec3(0.25,0.43,0.62),pow(smoothstep(0.0,0.9,h),0.7));
    col=mix(col,vec3(0.93,0.78,0.60),facing*(1.0-smoothstep(0.15,0.65,h))*0.55);
    col+=vec3(0.13,0.075,0.025)*pow(max(dot(d,sunDir),0.0),24.0);
    // High, brushed cirrus: long strokes, anchored in sky direction, never to screen roll.
    vec2 p=d.xz/max(0.18,h+0.2);
    float strokes=noise(p*vec2(3.0,38.0))+noise(p*vec2(8.0,75.0))*0.22;
    float cirrus=smoothstep(0.73,0.91,strokes)*smoothstep(0.15,0.5,h)*(1.0-smoothstep(0.72,0.95,h));
    col=mix(col,vec3(0.85,0.85,0.83),cirrus*0.07);
    float s=dot(d,sunDir);
    col=mix(col,vec3(1.0,0.94,0.78),smoothstep(0.9992,0.99965,s));
    col+=(hash(floor(gl_FragCoord.xy))-0.5)*0.003;
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
  void main(){
    vec2 p=vWorld.xz; float d=length(vWorld-camPos);
    float wash=noise(p*vec2(0.00055,0.0018));
    vec3 col=mix(vec3(0.20,0.34,0.43),vec3(0.32,0.49,0.56),smoothstep(0.35,0.64,wash));
    float footprint=max(length(dFdx(p)),length(dFdy(p)));
    float detail=1.0-smoothstep(18.0,100.0,footprint);
    float bands=noise(p*vec2(0.0013,0.014)+vec2(time*0.008,0));
    col=mix(col,vec3(0.50,0.63,0.65),smoothstep(0.60,0.78,bands)*0.14*detail);
    // Broken horizontal gold strokes, instead of a metallic PBR highlight.
    vec3 V=normalize(camPos-vWorld);
    float align=dot(normalize(V.xz),normalize(-sunDir.xz));
    float path=pow(max(align,0.0),32.0)*(1.0-smoothstep(0.12,0.9,V.y));
    float marks=noise(p*vec2(0.0015,0.012)+vec2(time*0.018,0));
    col=mix(col,vec3(0.93,0.79,0.58),path*smoothstep(0.52,0.78,marks)*0.65*detail);
    float crests=noise(p*vec2(0.025,0.16)+vec2(time*0.07,0));
    col=mix(col,vec3(0.74,0.80,0.77),smoothstep(0.77,0.83,crests)*(1.0-smoothstep(700.0,3500.0,d))*0.45);
    vec3 ray=normalize(vWorld-camPos);
    float facing=pow(max(dot(ray,sunDir),0.0),5.0);
    vec3 haze=mix(fogColor,vec3(0.93,0.78,0.60),facing*0.55);
    haze+=vec3(0.13,0.075,0.025)*pow(max(dot(ray,sunDir),0.0),24.0);
    col=mix(col,haze,smoothstep(fogNear,fogFar,d));
    col+=(hash(floor(gl_FragCoord.xy))-0.5)*0.003;
    gl_FragColor=vec4(col,1);
  }
`;

export const CLOUD_VS = `
  attribute vec2 aTile;
  uniform vec3 camPos;
  varying vec2 vUv; varying vec3 vWorld;
  void main(){
    // Face the camera with world-up projected onto the card. This preserves the
    // horizon under roll, while clouds also remain visible in steep dives.
    vec3 center=(modelMatrix*instanceMatrix*vec4(0,0,0,1)).xyz;
    vec3 toCam=normalize(camPos-center);
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
  void main(){
    vec4 paint=texture2D(cloudMap,vUv);
    float d=length(vWorld-camPos);
    // MSAA alpha coverage supplies soft edges with depth writes, avoiding unsorted
    // translucent billboards. Fade near the aircraft so a cloud never hides combat.
    float a=smoothstep(0.06,0.85,paint.a)*smoothstep(180.0,950.0,d);
    if(a<0.025) discard;
    vec3 col=mix(paint.rgb,fogColor,smoothstep(fogNear,fogFar,d)*0.72);
    gl_FragColor=vec4(col,a);
  }
`;

export const AIRFRAME_VS = `
  varying vec3 vPaint; varying vec3 vNormal; varying vec3 vEye;
  #include <fog_pars_vertex>
  void main(){
    vPaint=color;
    vNormal=normalize(normalMatrix*normal);
    vec4 mvPosition=modelViewMatrix*vec4(position,1);
    vEye=-mvPosition.xyz;
    gl_Position=projectionMatrix*mvPosition;
    #include <fog_vertex>
  }
`;
export const AIRFRAME_FRAGMENT = `
  uniform vec3 sunDir; uniform vec3 tint;
  varying vec3 vPaint; varying vec3 vNormal; varying vec3 vEye;
  #include <fog_pars_fragment>
  void main(){
    vec3 N=normalize(vNormal), V=normalize(vEye);
    vec3 L=normalize((viewMatrix*vec4(sunDir,0)).xyz);
    float l=dot(N,L);
    vec3 shade=mix(vec3(0.38,0.47,0.65),vec3(0.73,0.78,0.85),smoothstep(-0.18,-0.12,l));
    shade=mix(shade,vec3(1.15,1.08,0.92),smoothstep(0.38,0.44,l));
    vec3 col=vPaint*shade*tint;
    float rim=smoothstep(0.72,0.94,1.0-max(dot(N,V),0.0))*smoothstep(0.05,0.55,l);
    col=mix(col,vec3(0.83,0.77,0.62),rim*0.23);
    // A deliberate narrow canopy glint; no metallic/specular BRDF.
    float dark=1.0-smoothstep(0.035,0.10,dot(vPaint,vec3(0.21,0.72,0.07)));
    float glint=smoothstep(0.94,0.965,dot(reflect(-L,N),V));
    col=mix(col,vec3(0.70,0.82,0.85),glint*dark*0.55);
    gl_FragColor=vec4(col,1);
    #include <fog_fragment>
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;
