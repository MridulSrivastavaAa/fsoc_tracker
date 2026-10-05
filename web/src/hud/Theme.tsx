/** Theme picker: a curated palette popover in the top bar and a section in the View drawer. */
import { THEMES, useApp } from '../state/store';

export function ThemeList() {
  const theme = useApp((s) => s.theme);
  const setTheme = useApp((s) => s.setTheme);
  return (
    <div className="theme-list" role="radiogroup" aria-label="Theme">
      {THEMES.map((t) => (
        <button key={t.id} className={`theme-sw ${theme === t.id ? 'on' : ''}`} onClick={() => setTheme(t.id)} role="radio" aria-checked={theme === t.id} title={t.note}>
          <span className="bar">
            {t.swatch.map((c) => (
              <i key={c} style={{ background: c }} />
            ))}
          </span>
          <b style={{ fontWeight: 600 }}>{t.name}</b>
          <span style={{ fontSize: '10px', color: 'var(--text-3)', lineHeight: 1.2 }}>{t.sub}</span>
        </button>
      ))}
    </div>
  );
}

export function ThemePopover() {
  const open = useApp((s) => s.themeOpen);
  const set = useApp((s) => s.set);
  if (!open) return null;
  return (
    <div className="theme-pop glass" onMouseLeave={() => set({ themeOpen: false })}>
      <div className="eyebrow" style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
        <span>Telemetry Palettes</span>
        <span className="dim">4 profiles</span>
      </div>
      <ThemeList />
      <p className="note" style={{ marginBottom: 0, marginTop: 8 }}>
        Synchronizes HUD telemetry panels, 3D space background, predicted orbital vectors, and spatial reference axes.
      </p>
    </div>
  );
}

