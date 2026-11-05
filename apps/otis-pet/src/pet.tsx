import {StrictMode, useCallback, useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {faces} from './content';
import {FaceCanvas, type Mood} from './face/FaceCanvas';
import './index.css';
import './pet.css';

const DISC = '#2f4bf0';

/**
 * The face's hit layer is a 320px square, but most of that square is air.
 * Make transparent pixels part of the window-drag region so the pet can be
 * picked up anywhere it looks empty, while opaque pixels stay no-drag and
 * keep the grab gesture. The mask comes from the base cut-out's own alpha.
 */
function usePassthroughAlpha() {
  useEffect(() => {
    const size = 256;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d', {willReadFrequently: true});
    if (!ctx) return;
    let alpha: Uint8Array | null = null;
    const img = new Image();
    img.decoding = 'async';
    img.onload = () => {
      ctx.drawImage(img, 0, 0, size, size);
      const data = ctx.getImageData(0, 0, size, size).data;
      alpha = new Uint8Array(size * size);
      for (let i = 0; i < alpha.length; i++) alpha[i] = data[i * 4 + 3];
    };
    img.src = faces.base.src;

    const hit = () => document.querySelector<HTMLElement>('.pet-shell [role="img"]');
    const onMove = (event: PointerEvent) => {
      // Never switch mid-grab: a held pointer is still pulling the face.
      if (event.buttons || !alpha) return;
      const el = hit();
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      if (x < 0 || y < 0 || x >= rect.width || y >= rect.height) return;
      const px = Math.min(size - 1, Math.floor((x / rect.width) * size));
      const py = Math.min(size - 1, Math.floor((y / rect.height) * size));
      // pointer-events alone is not enough: the app region of a no-drag box
      // still blocks the window drag, so flip that too.
      const solid = alpha[py * size + px] > 16;
      el.style.setProperty('-webkit-app-region', solid ? 'no-drag' : 'drag');
      el.style.pointerEvents = solid ? 'auto' : 'none';
    };
    window.addEventListener('pointermove', onMove);
    return () => window.removeEventListener('pointermove', onMove);
  }, []);
}

/**
 * The desktop-pet surface. It reuses the portfolio's face engine and rig
 * untouched; only the surrounding page is different — no headline, bio or
 * press strip, just Otis and his patience.
 */
function Pet() {
  const stageRef = useRef<HTMLDivElement>(null);
  usePassthroughAlpha();
  const [mood, setMood] = useState<Mood>({face: 'base', patience: 100, pulls: 0});
  const onMood = useCallback((m: Mood) => setMood(m), []);
  const patience = mood.patience;

  return (
    <div className="pet-shell">
      {/* Empty space drags the window; the face and the meter sit above it. */}
      <div className="pet-drag-zone" />
      <div ref={stageRef} className="pet-stage">
        <p className={`hint pet-hint font-serif italic ${mood.pulls ? 'pet-hint-off' : ''}`}>
          pull my face
          <svg viewBox="0 0 60 40" className="ml-2 block h-6 w-9 -scale-x-100" fill="none" aria-hidden>
            <path d="M4 4c18 2 34 12 44 30" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            <path d="M40 31l8 4 1-9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </p>
      </div>

      <FaceCanvas stageRef={stageRef} discColor={DISC} onMood={onMood} />

      <div className="pet-meter" aria-live="polite">
        <div className="pet-mood">
          <span>Current mood</span>
          <strong>{faces[mood.face].mood}</strong>
        </div>
        <div className="pet-bar">
          <i
            style={{
              width: `${patience}%`,
              background: `color-mix(in oklab, var(--disc) ${patience}%, #e8412c)`,
            }}
          />
        </div>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Pet />
  </StrictMode>,
);

// Right-click borrows the tray menu so quitting stays reachable even when the
// Windows tray icon is in the overflow area.
window.addEventListener('contextmenu', (event) => {
  event.preventDefault();
  window.pet?.showMenu();
});
