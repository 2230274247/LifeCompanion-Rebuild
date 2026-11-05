import {useEffect, useLayoutEffect, useRef, useState} from 'react';

/**
 * From md up, sizes the one-line headline (inline-block, nowrap) to span its
 * parent's content box exactly. Below md it keeps its CSS size and wraps.
 * Either way the final size is published on the parent as --mega, which the
 * stage uses to tuck up under the type.
 */
export function useFitHeadline<T extends HTMLElement>() {
  const ref = useRef<T>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    const parent = el?.parentElement;
    if (!el || !parent) return;
    const wide = window.matchMedia('(min-width: 768px)');

    const PROBE = 100;
    const fit = () => {
      if (wide.matches) {
        el.style.fontSize = `${PROBE}px`;
        const styles = getComputedStyle(parent);
        const available = parent.clientWidth - parseFloat(styles.paddingLeft) - parseFloat(styles.paddingRight);
        const natural = el.offsetWidth;
        if (natural > 0) el.style.fontSize = `${(PROBE * available) / natural}px`;
      } else {
        el.style.fontSize = '';
      }
      parent.style.setProperty('--mega', getComputedStyle(el).fontSize);
    };

    fit();
    // Re-fit once Satoshi swaps in; its advances differ from the fallback.
    document.fonts?.ready.then(fit);
    const ro = new ResizeObserver(fit);
    ro.observe(parent);
    return () => ro.disconnect();
  }, []);

  return ref;
}

const THEME_KEY = 'otis-theme';

export function useTheme() {
  const [dark, setDark] = useState(() => {
    try {
      const saved = localStorage.getItem(THEME_KEY);
      if (saved) return saved === 'dark';
    } catch {
      /* storage blocked — fall through to the system setting */
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#0e1015' : '#e8ebf1');
    try {
      localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light');
    } catch {
      /* not persisted; fine */
    }
  }, [dark]);

  return [dark, () => setDark((d) => !d)] as const;
}
