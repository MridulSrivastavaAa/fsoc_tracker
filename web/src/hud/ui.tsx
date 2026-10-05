/** Small UI primitives and formatting helpers for the HUD. */
import type { ReactNode } from 'react';

export const fmt = (v: number | null | undefined, d = 2, unit = '') =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : `${v.toFixed(d)}${unit}`;
export const fmtSigned = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(d)}`;
export const fmtClock = (t: number) => {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${String(m).padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}`;
};

export function Slider(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  digits?: number;
  onChange: (v: number) => void;
}) {
  const { label, value, min, max, step = 0.01, unit = '', digits = 2, onChange } = props;
  const p = ((value - min) / (max - min)) * 100;
  return (
    <div className="field">
      <label>{label}</label>
      <span className="val">
        {value.toFixed(digits)}
        {unit}
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        style={{ ['--p' as string]: `${p}%` }}
        onChange={(e) => onChange(parseFloat(e.target.value))}
      />
    </div>
  );
}

export function Toggle({ label, on, onChange, hint }: { label: ReactNode; on: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <div className={`toggle ${on ? 'on' : ''}`} onClick={() => onChange(!on)} role="switch" aria-checked={on} title={hint}>
      <span>{label}</span>
      <span className="sw" />
    </div>
  );
}

export function Seg<T extends string>({ value, options, onChange }: { value: T; options: { v: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button key={o.v} className={o.v === value ? 'on' : ''} onClick={() => onChange(o.v)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Section({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <div className="section">
      <div className="eyebrow">
        <span>{title}</span>
        {right}
      </div>
      {children}
    </div>
  );
}

export function Readout({ label, value, unit, color }: { label: string; value: string; unit?: string; color?: string }) {
  return (
    <div className="ro">
      <div className="eyebrow">{label}</div>
      <div className="v" style={color ? { color } : undefined}>
        {value}
        {unit && <small>{unit}</small>}
      </div>
    </div>
  );
}

/** Line icons drawn for NETRA (24 px grid, 1.5 px stroke). */
export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const p = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  const paths: Record<string, ReactNode> = {
    scenario: (
      <>
        {/* Globe / planetary horizon */}
        <circle cx="12" cy="12" r="7.5" {...p} strokeWidth={1.4} />
        {/* Equatorial / meridian line */}
        <path d="M4.5 12h15M12 4.5c2.5 2.5 4 4.5 4 7.5s-1.5 5-4 7.5" {...p} strokeWidth={1.2} opacity={0.45} />
        {/* Orbital overpass trajectory track */}
        <path d="M3 17C4.5 9 10 3.5 18 3.5c3.2 0 4 2.5 2.5 5.5-2.5 5-9 10.5-16 11" {...p} strokeWidth={1.6} />
        {/* Satellite node on orbital track */}
        <circle cx="18" cy="4" r="1.8" fill="currentColor" stroke="none" />
        <path d="M20 2.5l1.5 1.5M16 5.5l-1.5-1.5" {...p} strokeWidth={1.3} />
      </>
    ),
    target: (
      <>
        {/* Targeting pod corner brackets */}
        <path d="M4 8V5.5a1.5 1.5 0 0 1 1.5-1.5H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16" {...p} strokeWidth={1.4} />
        {/* Target acquisition crosshair */}
        <circle cx="12" cy="12" r="4.8" {...p} strokeWidth={1.3} />
        <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
        <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" {...p} strokeWidth={1.6} />
      </>
    ),
    disturbance: (
      <>
        {/* Upper atmospheric flow stream with vortex */}
        <path d="M3 6.5h11a3 3 0 1 0-3-3" {...p} strokeWidth={1.5} />
        {/* Acute scintillation disturbance pulse */}
        <path d="M3 12h4l1.8-3.5 2.4 7 2-4.5 1.8 2.5H21" {...p} strokeWidth={1.6} />
        {/* Lower turbulence boundary stream */}
        <path d="M3 17.5h8.5a2.5 2.5 0 1 1-2.5 2.5" {...p} strokeWidth={1.5} />
      </>
    ),
    tracking: (
      <>
        {/* Closed-loop optical tracking diamond gate */}
        <path d="M12 3.5L20.5 12L12 20.5L3.5 12Z" {...p} strokeWidth={1.5} />
        {/* Inner centroid tracking circle */}
        <circle cx="12" cy="12" r="3.2" {...p} strokeWidth={1.2} strokeDasharray="2 1.5" />
        <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
        {/* Optical alignment ticks */}
        <path d="M12 1.5v2M12 20.5v2M1.5 12h2M20.5 12h2" {...p} strokeWidth={1.6} />
      </>
    ),
    experiment: (
      <>
        {/* Coordinate axes */}
        <path d="M3.5 4v16a1 1 0 0 0 1 1h16" {...p} strokeWidth={1.5} />
        {/* Telemetry metric distribution bars */}
        <path d="M7.5 17v-4M11.5 17v-7M15.5 17v-9" {...p} strokeWidth={2} strokeLinecap="round" opacity={0.35} />
        {/* Performance telemetry curve */}
        <path d="M6.5 14l3.5-4.5 3.5 3 4-7 3 2.5" {...p} strokeWidth={1.7} />
        <circle cx="20.5" cy="8" r="1.4" fill="currentColor" stroke="none" />
      </>
    ),
    optics: (
      <>
        <circle cx="9" cy="12" r="6" {...p} />
        <circle cx="9" cy="12" r="2.5" {...p} />
        <path d="M15 8.5l4-2.5v12l-4-2.5" {...p} />
        <path d="M9 3v2M9 19v2M3 12h2" {...p} />
        <path d="M19 12h3" {...p} strokeWidth={2} />
      </>
    ),
    view: (
      <>
        <path d="M2.5 12C4.5 7.5 8 5 12 5s7.5 2.5 9.5 7c-2 4.5-5.5 7-9.5 7s-7.5-2.5-9.5-7Z" {...p} />
        <circle cx="12" cy="12" r="3.5" {...p} />
        <circle cx="12" cy="12" r="1.5" fill="currentColor" />
        <path d="M12 2v1.5M12 20.5V22M2 12h1.5M20.5 12H22" {...p} opacity={0.5} />
      </>
    ),
    measure: (
      <>
        <path d="M4 20L20 4" {...p} />
        <path d="M6 18l-2 2M18 6l2-2" {...p} strokeWidth={2} />
        <path d="M8.5 13.5l-2-2M11.5 10.5l-2-2M14.5 7.5l-2-2" {...p} />
        <path d="M10 17l-3-3M17 10l-3-3" {...p} opacity={0.6} strokeDasharray="1.5 2" />
      </>
    ),
    analysis: <path d="M3.5 19.5h17M5 16l4-5 4 3 6-8" {...p} />,
    help: (
      <>
        {/* Command HUD key badge */}
        <rect x="3.5" y="3.5" width="17" height="17" rx="4" {...p} strokeWidth={1.5} />
        {/* Hotkey question glyph */}
        <path d="M9.5 8.5a2.5 2.5 0 0 1 3.4-.2 2.2 2.2 0 0 1 .5 2.2c-.4.8-1.4 1.3-1.4 2.1v.6" {...p} strokeWidth={1.6} />
        <circle cx="12" cy="16.4" r="1" fill="currentColor" stroke="none" />
      </>
    ),
    play: <path d="M8 5.5v13l10-6.5z" {...p} />,
    pause: <path d="M8.5 5.5v13M15.5 5.5v13" {...p} />,
    reset: <path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 4.5v4h4" {...p} />,
    expand: <path d="M14 4.5h5.5V10M10 19.5H4.5V14M19.5 4.5l-6 6M4.5 19.5l6-6" {...p} />,
    close: <path d="M6 6l12 12M18 6 6 18" {...p} />,
    download: <path d="M12 4v11m0 0-4-4m4 4 4-4M5 19.5h14" {...p} />,
    upload: <path d="M12 15.5v-11m0 0-4 4m4-4 4 4M5 19.5h14" {...p} />,
    crosshair: (
      <>
        <circle cx="12" cy="12" r="7" {...p} />
        <path d="M12 2.5v5M12 16.5v5M2.5 12h5M16.5 12h5" {...p} />
      </>
    ),
    palette: (
      <>
        {/* Contrast disc / display theme switcher */}
        <circle cx="12" cy="12" r="8" {...p} strokeWidth={1.6} />
        <path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" stroke="none" />
      </>
    ),
    film: (
      <>
        {/* Camera body */}
        <rect x="3" y="5.5" width="12" height="13" rx="2.5" {...p} strokeWidth={1.5} />
        {/* Lens cone */}
        <path d="M15 10l5.5-3.5v11L15 14" {...p} strokeWidth={1.5} strokeLinejoin="round" />
        {/* Optical sensor aperture / play reticle */}
        <circle cx="9" cy="12" r="3" {...p} strokeWidth={1.2} />
        <path d="M8 10.5l2.8 1.5L8 13.5z" fill="currentColor" stroke="none" />
      </>
    ),
    report: (
      <>
        <path d="M6 3.5h8l4 4v13H6z" {...p} />
        <path d="M14 3.5v4h4M9 12h6M9 15.5h6M9 8.5h2" {...p} />
      </>
    ),
    screen: (
      <>
        <rect x="3.5" y="3.5" width="17" height="17" rx="1.5" {...p} />
        <rect x="8" y="9" width="7" height="5.5" {...p} />
        <circle cx="16.5" cy="7" r="1" {...p} />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" {...p} />,
    minus: <path d="M5 12h14" {...p} />,
    hand: <path d="M8 13V6.5a1.5 1.5 0 0 1 3 0V12m0-6.5V5a1.5 1.5 0 0 1 3 0v7m0-5.5a1.5 1.5 0 0 1 3 0V14a6 6 0 0 1-6 6h-.5a6 6 0 0 1-4.9-2.5L4 14.3a1.5 1.5 0 0 1 2.3-1.9L8 14" {...p} />,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      {paths[name] ?? null}
    </svg>
  );
}

export function BrandMark() {
  // NETRA electro-optical eye logo with precision laser targeting beam
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="netra-eye-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#8fdcff" />
          <stop offset="100%" stopColor="#38bdf8" />
        </linearGradient>
      </defs>
      {/* Outer Eye / Aperture Silhouette */}
      <path
        d="M 3 16 C 9 6, 23 6, 29 16 C 23 26, 9 26, 3 16 Z"
        fill="rgba(var(--accent-rgb),0.08)"
        stroke="url(#netra-eye-grad)"
        strokeWidth="1.6"
      />
      {/* Optical Reticle / Iris Ring */}
      <circle
        cx="16"
        cy="16"
        r="7.5"
        fill="rgba(var(--accent-rgb),0.12)"
        stroke="rgba(var(--accent-rgb),0.65)"
        strokeWidth="1.1"
      />
      {/* Boresight Pupil / Core Beacon */}
      <circle cx="16" cy="16" r="3" fill="#ffffff" />
      <circle cx="16" cy="16" r="1.3" fill="#ffb547" />
    </svg>
  );
}

/** Resolve a CSS custom property of the active theme (e.g. '--ser-a'); plain colours pass through. */
const varCache = new Map<string, string>();
let varTheme = '';
export function cssVar(name: string): string {
  if (!name.startsWith('--')) return name;
  const theme = document.documentElement.dataset.theme ?? '';
  if (theme !== varTheme) {
    varCache.clear();
    varTheme = theme;
  }
  let v = varCache.get(name);
  if (v === undefined) {
    v = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#8fdcff';
    varCache.set(name, v);
  }
  return v;
}
