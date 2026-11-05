import {useEffect, useRef, useState, type RefObject} from 'react';
import {faces, releaseFaces, rig, type FaceKey} from '../content';
import {FaceEngine} from './engine';

export type Mood = {face: FaceKey; patience: number; pulls: number};

type Props = {
  stageRef: RefObject<HTMLDivElement | null>;
  discColor: string;
  onMood: (m: Mood) => void;
};

/** Neutral time after a release before he goes back to just watching the cursor. */
const HOLD_MS = 5000;

function load(src: string) {
  return new Promise<HTMLImageElement | null>((resolve) => {
    const img = new Image();
    img.decoding = 'async';
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

/** Which face a grab pulls, by where it lands. */
function grabFace(u: number, v: number): FaceKey {
  const side = Math.abs(u - 0.5);
  if (v < rig.hairLine || (side > rig.sides && v < 0.6)) return 'g_ouch';
  if (side > 0.07 && v > 0.44 && v < 0.66) return 'g_squish';
  return 'g_grimace';
}

/**
 * Full-hero canvas plus a hit layer over the stage. The canvas never takes
 * pointer events, so the stretched face can spill over the copy without
 * blocking it; grabs only start on opaque pixels of the cut-out.
 */
export function FaceCanvas({stageRef, discColor, onMood}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const hitRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);
  const onMoodRef = useRef(onMood);
  onMoodRef.current = onMood;
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const hit = hitRef.current!;
    const ring = ringRef.current!;
    let engine: FaceEngine | null = null;
    let disposed = false;
    const cleanups: (() => void)[] = [];

    const stage = {x: 0, y: 0, size: 1};
    const layout = () => {
      const s = stageRef.current;
      if (!s) return;
      const c = canvas.getBoundingClientRect();
      const r = s.getBoundingClientRect();
      Object.assign(stage, {x: r.left - c.left, y: r.top - c.top, size: r.width});
      Object.assign(hit.style, {
        left: `${stage.x}px`,
        top: `${stage.y}px`,
        width: `${stage.size}px`,
        height: `${stage.size}px`,
      });
      engine?.resize(c.width, c.height, Math.min(window.devicePixelRatio || 1, 2));
      engine?.setStage(stage);
    };

    (async () => {
      const keys = Object.keys(faces) as FaceKey[];
      const loaded = await Promise.all(keys.map((k) => load(faces[k].src)));
      if (disposed) return;
      const base = loaded[0];
      if (!base) return setFailed(true);
      // Expressions that fail to load fall back to the base face.
      const images = new Map<string, HTMLImageElement>();
      const available = new Set<FaceKey>();
      keys.forEach((k, i) => {
        images.set(k, loaded[i] ?? base);
        if (loaded[i]) available.add(k);
      });

      try {
        engine = new FaceEngine(canvas, images, 'base', discColor);
      } catch {
        return setFailed(true);
      }
      const e = engine;
      layout();
      e.start();
      e.warm();

      // --- director -------------------------------------------------------
      let face: FaceKey = 'base';
      let mode: 'neutral' | 'held' | 'after' = 'neutral';
      let afterAt = 0;
      let pulls = 0;
      let lastRelease: FaceKey | null = null;
      let cursor: {x: number; y: number} | null = null;
      const downs = new Map<number, {t: number; x: number; y: number; moved: number; u: number; v: number}>();
      let reported = '';

      const report = () => {
        const m = {face, patience: Math.round((1 - e.flush) * 100), pulls};
        const key = `${m.face}|${m.patience}|${m.pulls}`;
        if (key !== reported) {
          reported = key;
          onMoodRef.current(m);
        }
      };
      // A missing grab face borrows the grimace; anything else falls back to base.
      const resolve = (k: FaceKey): FaceKey =>
        available.has(k) ? k : k.startsWith('g_') && available.has('g_grimace') ? 'g_grimace' : 'base';
      const show = (k: FaceKey) => {
        k = resolve(k);
        face = k;
        e.setFace(k);
        report();
      };

      // Idle: the eyes follow the cursor; hovering the nose makes him cross-eyed.
      const neutralFace = (): FaceKey => {
        if (!cursor) return 'base';
        const p = e.pick(cursor.x, cursor.y);
        if (p && Math.hypot(p.u - rig.nose.x, p.v - rig.nose.y) < rig.nose.r * 1.4) return 'x_cross';
        const dx = (cursor.x - (stage.x + stage.size / 2)) / stage.size;
        if (dx < -0.42) return 'l_left';
        if (dx > 0.42) return 'l_right';
        return 'base';
      };

      const local = (ev: PointerEvent) => {
        const c = canvas.getBoundingClientRect();
        return {x: ev.clientX - c.left, y: ev.clientY - c.top};
      };

      const setRing = (ev: PointerEvent, over: boolean) => {
        if (ev.pointerType !== 'mouse') return;
        ring.style.transform = `translate3d(${ev.clientX}px, ${ev.clientY}px, 0)`;
        const on = over || e.held;
        ring.dataset.on = on ? '1' : '';
        ring.dataset.held = e.held ? '1' : '';
        hit.style.cursor = on ? 'none' : '';
      };

      const onDown = (ev: PointerEvent) => {
        layout();
        const p = local(ev);
        const at = e.pick(p.x, p.y);
        if (!at) return;
        ev.preventDefault();
        hit.setPointerCapture(ev.pointerId);
        e.grab(ev.pointerId, at.u, at.v, p.x, p.y);
        downs.set(ev.pointerId, {t: performance.now(), x: p.x, y: p.y, moved: 0, u: at.u, v: at.v});
        if (downs.size === 1) show(grabFace(at.u, at.v));
        mode = 'held';
        setRing(ev, true);
      };

      const onMove = (ev: PointerEvent) => {
        const p = local(ev);
        const d = downs.get(ev.pointerId);
        if (d) {
          d.moved = Math.max(d.moved, Math.hypot(p.x - d.x, p.y - d.y));
          e.drag(ev.pointerId, p.x, p.y);
        }
        setRing(ev, !!e.pick(p.x, p.y));
      };

      const onUp = (ev: PointerEvent) => {
        const d = downs.get(ev.pointerId);
        if (!d) return;
        downs.delete(ev.pointerId);
        e.release(ev.pointerId);
        setRing(ev, !!e.pick(local(ev).x, local(ev).y));
        if (downs.size) return;
        const tap = performance.now() - d.t < 240 && d.moved < 8;
        if (tap) {
          e.poke(d.u, d.v);
          show('x_shock');
        } else {
          pulls += 1;
          let next: FaceKey;
          if (e.flush > 0.8) next = 'x_dizzy';
          else {
            const pool = releaseFaces.filter((k) => k !== lastRelease && available.has(k));
            next = pool.length ? pool[Math.floor(Math.random() * pool.length)] : 'base';
          }
          lastRelease = next;
          show(next);
        }
        mode = 'after';
        afterAt = performance.now();
      };

      // Touch: block the page scroll only when the finger lands on the face.
      const onTouchStart = (ev: TouchEvent) => {
        const c = canvas.getBoundingClientRect();
        const t = ev.touches[0];
        if (t && e.pick(t.clientX - c.left, t.clientY - c.top)) ev.preventDefault();
      };

      const onWindowMove = (ev: PointerEvent) => {
        if (ev.pointerType !== 'mouse') return;
        cursor = local(ev);
        if (mode === 'neutral') {
          const n = neutralFace();
          if (n !== face) show(n);
        }
      };
      const onLeave = () => {
        ring.dataset.on = '';
      };

      hit.addEventListener('pointerdown', onDown);
      hit.addEventListener('pointermove', onMove);
      hit.addEventListener('pointerup', onUp);
      hit.addEventListener('pointercancel', onUp);
      hit.addEventListener('pointerleave', onLeave);
      hit.addEventListener('touchstart', onTouchStart, {passive: false});
      window.addEventListener('pointermove', onWindowMove, {passive: true});

      const timer = window.setInterval(() => {
        if (mode === 'after' && !e.held && performance.now() - afterAt > HOLD_MS) {
          mode = 'neutral';
          show(neutralFace());
        }
        report();
      }, 120);

      // Only run the loop while the hero is on screen.
      const io = new IntersectionObserver(([entry]) => (entry.isIntersecting ? e.start() : e.stop()));
      io.observe(canvas);

      cleanups.push(() => {
        hit.removeEventListener('pointerdown', onDown);
        hit.removeEventListener('pointermove', onMove);
        hit.removeEventListener('pointerup', onUp);
        hit.removeEventListener('pointercancel', onUp);
        hit.removeEventListener('pointerleave', onLeave);
        hit.removeEventListener('touchstart', onTouchStart);
        window.removeEventListener('pointermove', onWindowMove);
        window.clearInterval(timer);
        io.disconnect();
        e.destroy();
      });
    })();

    const ro = new ResizeObserver(layout);
    ro.observe(canvas);
    if (stageRef.current) ro.observe(stageRef.current);
    document.fonts?.ready.then(layout);

    return () => {
      disposed = true;
      ro.disconnect();
      cleanups.forEach((f) => f());
    };
  }, [stageRef, discColor]);

  return (
    <>
      <canvas ref={canvasRef} aria-hidden className="pointer-events-none absolute inset-0 z-20 h-full w-full" />
      <div
        ref={hitRef}
        role="img"
        aria-label="Otis. Grab and stretch his face to change his expression."
        className="absolute z-30 select-none"
      >
        {failed && (
          <>
            <div
              className="absolute rounded-full bg-disc"
              style={{
                left: `${(rig.disc.x - rig.disc.r) * 100}%`,
                top: `${(rig.disc.y - rig.disc.r) * 100}%`,
                width: `${rig.disc.r * 200}%`,
                height: `${rig.disc.r * 200}%`,
              }}
            />
            <img src={faces.base.src} alt="" className="absolute inset-0 h-full w-full" />
          </>
        )}
      </div>
      <div ref={ringRef} aria-hidden className="grab-ring" />
    </>
  );
}
