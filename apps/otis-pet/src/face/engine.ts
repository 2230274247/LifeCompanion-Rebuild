import {rig} from '../content';

/**
 * Taffy-face renderer. The portrait is a dense grid; every grab drags the
 * vertices around its anchor by a gaussian of their rest distance, so a long
 * pull draws the skin out into a tapering tube. Let go and a damped spring
 * snaps it back with a wobble. A flush value reddens the cheeks, then the
 * whole face, the longer it is mistreated.
 */

const GRID = 128;
const SLOTS = 4;
const SIGMA = 0.072; // grab falloff, in image UV
const SPRING = 260;
const DAMPING = 11;
const FADE = 0.09; // expression crossfade, seconds

const faceVert = `#version 300 es
in vec2 aUv;
uniform vec2 uView;
uniform vec3 uStage;
uniform vec4 uGrab[${SLOTS}];
out vec2 vUv;
out float vStretch;
void main() {
  vec2 p = uStage.xy + aUv * uStage.z;
  float s = 0.0;
  for (int i = 0; i < ${SLOTS}; i++) {
    vec2 d = aUv - uGrab[i].xy;
    float len = length(uGrab[i].zw) / uStage.z;
    float sig = ${SIGMA} * (1.0 + 0.35 * len);
    float w = exp(-dot(d, d) / (2.0 * sig * sig));
    p += uGrab[i].zw * w;
    s += w * len;
  }
  vUv = aUv;
  vStretch = s;
  vec2 c = p / uView * 2.0 - 1.0;
  gl_Position = vec4(c.x, -c.y, 0.0, 1.0);
}`;

const faceFrag = `#version 300 es
precision highp float;
in vec2 vUv;
in float vStretch;
uniform sampler2D uA;
uniform sampler2D uB;
uniform float uMix;
uniform vec4 uDisc;
uniform float uFlush;
uniform vec4 uCheeks;
uniform vec4 uFace;
uniform vec3 uNose;
out vec4 outColor;

float blob(vec2 p, vec2 c, float r) {
  vec2 d = p - c;
  return exp(-dot(d, d) / (2.0 * r * r));
}

void main() {
  vec4 c = mix(texture(uA, vUv), texture(uB, vUv), uMix);

  // Below the disc centre the bust is cut by the disc; above it the head breaks out.
  float inDisc = 1.0 - smoothstep(uDisc.z - uDisc.w, uDisc.z + uDisc.w, length(vUv - uDisc.xy));
  c *= max(step(vUv.y, uDisc.y), inDisc);

  // Flush: cheeks and nose first, then the whole face. Only skin-like pixels
  // (red well above blue) take it, so eye whites and irises stay clean.
  vec3 rgb = c.a > 0.0 ? c.rgb / c.a : vec3(0.0);
  float skin = smoothstep(0.04, 0.16, rgb.r - rgb.b);
  float blush = blob(vUv, uCheeks.xy, 0.055) + blob(vUv, uCheeks.zw, 0.055) + 0.8 * blob(vUv, uNose.xy, uNose.z);
  vec2 e = (vUv - uFace.xy) / uFace.zw;
  float face = 1.0 - smoothstep(0.55, 1.05, length(e));
  float m = blush * smoothstep(0.0, 0.5, uFlush) + face * smoothstep(0.4, 1.0, uFlush) * 0.9;
  m += clamp(vStretch * 0.7, 0.0, 0.45);
  m = clamp(m, 0.0, 1.0) * skin;
  rgb *= mix(vec3(1.0), vec3(1.08, 0.56, 0.54), m);

  outColor = vec4(rgb * c.a, c.a);
}`;

const discVert = `#version 300 es
in vec2 aUv;
uniform vec2 uView;
uniform vec3 uStage;
uniform vec3 uDisc;
out vec2 vP;
void main() {
  vP = (aUv * 2.0 - 1.0) * (uDisc.z + 0.01);
  vec2 p = uStage.xy + (uDisc.xy + vP) * uStage.z;
  vec2 c = p / uView * 2.0 - 1.0;
  gl_Position = vec4(c.x, -c.y, 0.0, 1.0);
}`;

const discFrag = `#version 300 es
precision highp float;
in vec2 vP;
uniform vec3 uDisc;
uniform float uAa;
uniform vec3 uColor;
out vec4 outColor;
void main() {
  float a = 1.0 - smoothstep(uDisc.z - uAa, uDisc.z + uAa, length(vP));
  outColor = vec4(uColor * a, a);
}`;

type Slot = {
  pointer: number | null;
  ax: number;
  ay: number;
  ox: number;
  oy: number;
  vx: number;
  vy: number;
  tx: number;
  ty: number;
  live: boolean;
};

export type Stage = {x: number; y: number; size: number};

function compile(gl: WebGL2RenderingContext, vs: string, fs: string) {
  const prog = gl.createProgram()!;
  for (const [type, src] of [
    [gl.VERTEX_SHADER, vs],
    [gl.FRAGMENT_SHADER, fs],
  ] as const) {
    const sh = gl.createShader(type)!;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh) ?? 'shader');
    gl.attachShader(prog, sh);
  }
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) ?? 'link');
  return prog;
}

function uniforms(gl: WebGL2RenderingContext, prog: WebGLProgram, names: string[]) {
  return Object.fromEntries(names.map((n) => [n, gl.getUniformLocation(prog, n)])) as Record<
    string,
    WebGLUniformLocation | null
  >;
}

export class FaceEngine {
  flush = 0;
  private gl: WebGL2RenderingContext;
  private face: WebGLProgram;
  private disc: WebGLProgram;
  private fu: Record<string, WebGLUniformLocation | null>;
  private du: Record<string, WebGLUniformLocation | null>;
  private faceVao: WebGLVertexArrayObject;
  private discVao: WebGLVertexArrayObject;
  private indexCount: number;
  private textures = new Map<string, WebGLTexture>();
  private images: Map<string, HTMLImageElement>;
  private alpha: Uint8ClampedArray;
  private alphaSize = 256;
  private slots: Slot[] = Array.from({length: SLOTS}, () => ({
    pointer: null,
    ax: 0,
    ay: 0,
    ox: 0,
    oy: 0,
    vx: 0,
    vy: 0,
    tx: 0,
    ty: 0,
    live: false,
  }));
  private stage: Stage = {x: 0, y: 0, size: 1};
  private view = {w: 1, h: 1, dpr: 1};
  private texA: string;
  private texB: string;
  private mix = 0;
  private lastHeld = 0;
  private raf = 0;
  private last = 0;
  private discColor: [number, number, number];

  constructor(
    private canvas: HTMLCanvasElement,
    images: Map<string, HTMLImageElement>,
    base: string,
    discColor: string,
  ) {
    const gl = canvas.getContext('webgl2', {premultipliedAlpha: true, antialias: true, alpha: true});
    if (!gl) throw new Error('webgl2');
    this.gl = gl;
    this.images = images;
    this.texA = this.texB = base;
    this.discColor = [1, 3, 5].map((i) => parseInt(discColor.slice(i, i + 2), 16) / 255) as [number, number, number];

    this.face = compile(gl, faceVert, faceFrag);
    this.disc = compile(gl, discVert, discFrag);
    this.fu = uniforms(gl, this.face, ['uView', 'uStage', 'uGrab', 'uA', 'uB', 'uMix', 'uDisc', 'uFlush', 'uCheeks', 'uFace', 'uNose']);
    this.du = uniforms(gl, this.disc, ['uView', 'uStage', 'uDisc', 'uAa', 'uColor']);

    // Grid mesh in UV space; the vertex shader places and warps it.
    const n = GRID + 1;
    const uv = new Float32Array(n * n * 2);
    for (let y = 0; y < n; y++)
      for (let x = 0; x < n; x++) {
        uv[(y * n + x) * 2] = x / GRID;
        uv[(y * n + x) * 2 + 1] = y / GRID;
      }
    const idx = new Uint16Array(GRID * GRID * 6);
    let k = 0;
    for (let y = 0; y < GRID; y++)
      for (let x = 0; x < GRID; x++) {
        const a = y * n + x;
        idx.set([a, a + 1, a + n, a + 1, a + n + 1, a + n], k);
        k += 6;
      }
    this.indexCount = idx.length;
    this.faceVao = this.vao(this.face, uv, idx);
    this.discVao = this.vao(this.disc, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), null);

    // Low-res alpha copy of the base face for hit testing.
    const c = document.createElement('canvas');
    c.width = c.height = this.alphaSize;
    const ctx = c.getContext('2d', {willReadFrequently: true})!;
    ctx.drawImage(images.get(base)!, 0, 0, this.alphaSize, this.alphaSize);
    this.alpha = ctx.getImageData(0, 0, this.alphaSize, this.alphaSize).data;

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    this.texture(base);
  }

  private vao(prog: WebGLProgram, data: Float32Array, idx: Uint16Array | null) {
    const gl = this.gl;
    const vao = gl.createVertexArray()!;
    gl.bindVertexArray(vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'aUv');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    if (idx) {
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer());
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.STATIC_DRAW);
    }
    gl.bindVertexArray(null);
    return vao;
  }

  private texture(key: string) {
    let tex = this.textures.get(key);
    if (tex) return tex;
    const gl = this.gl;
    tex = gl.createTexture()!;
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, this.images.get(key)!);
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    this.textures.set(key, tex);
    return tex;
  }

  /** Upload the remaining expressions one per idle slot so the first swap never hitches. */
  warm() {
    const keys = [...this.images.keys()].filter((k) => !this.textures.has(k));
    const next = () => {
      const k = keys.shift();
      if (!k) return;
      this.texture(k);
      setTimeout(next, 30);
    };
    next();
  }

  resize(w: number, h: number, dpr: number) {
    this.view = {w, h, dpr};
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
  }

  setStage(stage: Stage) {
    this.stage = stage;
  }

  setFace(key: string) {
    if (key === this.texB) return;
    // Mid-fade, keep whichever face dominates as the one we fade from.
    if (this.mix >= 0.5) this.texA = this.texB;
    this.texB = key;
    this.mix = 0;
  }

  /** Displacement of a rest UV point from all slots, in px. */
  private displace(u: number, v: number) {
    let dx = 0;
    let dy = 0;
    for (const s of this.slots) {
      if (!s.live) continue;
      const len = Math.hypot(s.ox, s.oy) / this.stage.size;
      const sig = SIGMA * (1 + 0.35 * len);
      const w = Math.exp(-((u - s.ax) ** 2 + (v - s.ay) ** 2) / (2 * sig * sig));
      dx += s.ox * w;
      dy += s.oy * w;
    }
    return [dx, dy];
  }

  /** Rest UV under a canvas point (undoing any wobble in flight), or null if it misses the cut-out. */
  pick(px: number, py: number) {
    const {x, y, size} = this.stage;
    let u = (px - x) / size;
    let v = (py - y) / size;
    for (let i = 0; i < 5; i++) {
      const [dx, dy] = this.displace(u, v);
      u = (px - dx - x) / size;
      v = (py - dy - y) / size;
    }
    if (u < 0 || v < 0 || u >= 1 || v >= 1) return null;
    const {disc} = rig;
    if (v > disc.y && Math.hypot(u - disc.x, v - disc.y) > disc.r) return null;
    const a = this.alpha[(Math.floor(v * this.alphaSize) * this.alphaSize + Math.floor(u * this.alphaSize)) * 4 + 3];
    return a > 120 ? {u, v} : null;
  }

  grab(pointer: number, u: number, v: number, px: number, py: number) {
    const free =
      this.slots.find((s) => !s.live) ??
      this.slots.filter((s) => s.pointer === null).sort((a, b) => Math.hypot(a.ox, a.oy) - Math.hypot(b.ox, b.oy))[0];
    if (!free) return;
    Object.assign(free, {pointer, ax: u, ay: v, ox: 0, oy: 0, vx: 0, vy: 0, live: true});
    this.drag(pointer, px, py);
  }

  drag(pointer: number, px: number, py: number) {
    const s = this.slots.find((s) => s.pointer === pointer);
    if (!s) return;
    const {x, y, size} = this.stage;
    // Clamp to the canvas, then rubber-band so the pull gets heavier the further it goes.
    const cx = Math.min(Math.max(px, 4), this.view.w - 4);
    const cy = Math.min(Math.max(py, 4), this.view.h - 4);
    const tx = cx - (x + s.ax * size);
    const ty = cy - (y + s.ay * size);
    const len = Math.hypot(tx, ty);
    const max = size * 1.1;
    const k = len > 0 ? (max * Math.tanh(len / max)) / len : 0;
    s.tx = tx * k;
    s.ty = ty * k;
  }

  release(pointer: number) {
    const s = this.slots.find((s) => s.pointer === pointer);
    if (s) s.pointer = null;
  }

  /** A tap: no stretch, just a jolt so the face jiggles. */
  poke(u: number, v: number) {
    const s = this.slots.find((s) => !s.live);
    if (!s) return;
    const size = this.stage.size;
    Object.assign(s, {pointer: null, ax: u, ay: v, ox: 0, oy: 0, vx: (0.5 - u) * size * 2.2, vy: size * 0.9, live: true});
  }

  get held() {
    return this.slots.some((s) => s.pointer !== null);
  }

  /** Longest current pull as a fraction of the stage. */
  get stretch() {
    return Math.max(0, ...this.slots.map((s) => (s.live ? Math.hypot(s.ox, s.oy) / this.stage.size : 0)));
  }

  start() {
    if (this.raf) return;
    const tick = (t: number) => {
      this.raf = requestAnimationFrame(tick);
      const dt = Math.min((t - (this.last || t)) / 1000, 1 / 30);
      this.last = t;
      this.step(dt, t);
      this.draw();
    };
    this.raf = requestAnimationFrame(tick);
  }

  stop() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.last = 0;
  }

  private step(dt: number, now: number) {
    for (const s of this.slots) {
      if (!s.live) continue;
      if (s.pointer !== null) {
        // Follow the finger almost rigidly; keep the velocity for the release.
        const nx = s.ox + (s.tx - s.ox) * Math.min(1, dt * 38);
        const ny = s.oy + (s.ty - s.oy) * Math.min(1, dt * 38);
        s.vx = dt > 0 ? (nx - s.ox) / dt : 0;
        s.vy = dt > 0 ? (ny - s.oy) / dt : 0;
        s.ox = nx;
        s.oy = ny;
        continue;
      }
      const h = dt / 3;
      for (let i = 0; i < 3; i++) {
        s.vx += (-SPRING * s.ox - DAMPING * s.vx) * h;
        s.vy += (-SPRING * s.oy - DAMPING * s.vy) * h;
        s.ox += s.vx * h;
        s.oy += s.vy * h;
      }
      if (Math.hypot(s.ox, s.oy) < 0.25 && Math.hypot(s.vx, s.vy) < 6) s.live = false;
    }

    if (this.held) {
      this.lastHeld = now;
      this.flush = Math.min(1, this.flush + dt * 0.3 * Math.min(1, this.stretch / 0.4 + 0.15));
    } else if (now - this.lastHeld > 1600) {
      this.flush = Math.max(0, this.flush - dt * 0.07);
    }

    if (this.mix < 1) {
      this.mix = Math.min(1, this.mix + dt / FADE);
      if (this.mix >= 1) this.texA = this.texB;
    }
  }

  private draw() {
    const gl = this.gl;
    const {w, h, dpr} = this.view;
    const {x, y, size} = this.stage;
    const {disc, cheeks, face, nose} = rig;
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.useProgram(this.disc);
    gl.uniform2f(this.du.uView, w, h);
    gl.uniform3f(this.du.uStage, x, y, size);
    gl.uniform3f(this.du.uDisc, disc.x, disc.y, disc.r);
    gl.uniform1f(this.du.uAa, 1 / (size * dpr));
    gl.uniform3f(this.du.uColor, ...this.discColor);
    gl.bindVertexArray(this.discVao);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    gl.useProgram(this.face);
    gl.uniform2f(this.fu.uView, w, h);
    gl.uniform3f(this.fu.uStage, x, y, size);
    const g = new Float32Array(SLOTS * 4);
    this.slots.forEach((s, i) => s.live && g.set([s.ax, s.ay, s.ox, s.oy], i * 4));
    gl.uniform4fv(this.fu.uGrab, g);
    gl.uniform4f(this.fu.uDisc, disc.x, disc.y, disc.r, 1 / (size * dpr));
    gl.uniform1f(this.fu.uFlush, this.flush);
    gl.uniform4f(this.fu.uCheeks, cheeks[0].x, cheeks[0].y, cheeks[1].x, cheeks[1].y);
    gl.uniform4f(this.fu.uFace, face.x, face.y, face.rx, face.ry);
    gl.uniform3f(this.fu.uNose, nose.x, nose.y, nose.r);
    gl.uniform1f(this.fu.uMix, this.mix);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.texture(this.texA));
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.texture(this.texB));
    gl.uniform1i(this.fu.uA, 0);
    gl.uniform1i(this.fu.uB, 1);
    gl.bindVertexArray(this.faceVao);
    gl.drawElements(gl.TRIANGLES, this.indexCount, gl.UNSIGNED_SHORT, 0);
  }

  destroy() {
    this.stop();
    this.gl.getExtension('WEBGL_lose_context')?.loseContext();
  }
}
