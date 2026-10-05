/**
 * Application state (zustand).
 *
 * High-rate data (snapshots at 30 Hz, sensor images, time series) lives in plain
 * module-level buffers read by the 3D scene every animation frame; React state only
 * receives a throttled "tick" so the HUD re-renders ~12 times per second.
 */
import { create } from 'zustand';
import { DEFAULT_CONFIG, DeepPartial, SimConfig, mergeConfig } from '../core/config';
import type { Snapshot, TransitionEvent, TrackState } from '../core/telemetry/types';
import { TRACK_STATES } from '../core/telemetry/types';
import { Recorder, Recording } from '../core/telemetry/recorder';
import { PerformanceReport, buildReport, reportHtml, reportMarkdown } from '../core/analysis/report';
import type { EngineCommand, EngineMessage } from '../engine/protocol';
import { DEFAULT_SERVER_URL, LocalEngineProvider, ProviderKind, RemoteEngineProvider, ReplayProvider, TelemetryProvider } from '../services/providers';

// ───────────────────────── high-rate buffers ─────────────────────────
export const live = {
  snap: null as Snapshot | null,
  image: null as { width: number; height: number; frame: number; data: Uint8ClampedArray } | null,
  imageVersion: 0,
  plan: null as Snapshot['plan'] | null,
  /** Last ~1 s of snapshots, so the sensor overlay can use the snapshot matching the displayed image. */
  recent: [] as Snapshot[],
  /** Error at the moment of the latest first detection (coarse-alignment "initial error"). */
  initialErrPx: null as number | null,
};

const N = 30 * 90;
export const SERIES = ['t', 'errPx', 'estErrPx', 'angErr', 'pan', 'tilt', 'panRate', 'tiltRate', 'panCmd', 'tiltCmd', 'conf', 'tgtRate', 'state', 'aqs'] as const;
export type SeriesKey = (typeof SERIES)[number];
export const history = {
  n: 0,
  head: 0,
  data: Object.fromEntries(SERIES.map((k) => [k, new Float32Array(N)])) as Record<SeriesKey, Float32Array>,
  cap: N,
};
/** Recent 3D trail data. */
export const trails = {
  target: [] as [number, number, number][],
  axis: [] as { az: number; el: number; r: number }[],
};

function pushHistory(s: Snapshot) {
  const h = history;
  const i = h.head;
  const d = h.data;
  d.t[i] = s.t;
  d.errPx[i] = s.error.magPx ?? NaN;
  d.estErrPx[i] = s.error.estMagPx ?? NaN;
  d.angErr[i] = s.error.angDeg;
  d.pan[i] = s.gimbal.pan;
  d.tilt[i] = s.gimbal.tilt;
  d.panRate[i] = s.gimbal.panRate;
  d.tiltRate[i] = s.gimbal.tiltRate;
  d.panCmd[i] = s.gimbal.panCmd;
  d.tiltCmd[i] = s.gimbal.tiltCmd;
  d.conf[i] = s.detection?.confidence ?? 0;
  d.tgtRate[i] = s.target.angRateDegS;
  d.state[i] = TRACK_STATES.indexOf(s.state);
  d.aqs[i] = s.metrics.aqs;
  h.head = (i + 1) % h.cap;
  h.n = Math.min(h.cap, h.n + 1);
  trails.target.push(s.target.posKm);
  if (trails.target.length > 30 * 25) trails.target.shift();
  trails.axis.push({ az: s.gimbal.axisAz, el: s.gimbal.axisEl, r: s.target.rangeKm });
  if (trails.axis.length > 30 * 8) trails.axis.shift();
}

export function clearHistory() {
  history.n = 0;
  history.head = 0;
  trails.target.length = 0;
  trails.axis.length = 0;
}

/** Iterate history in time order. */
export function historySlice(key: SeriesKey, seconds: number): { t: Float32Array; v: Float32Array } {
  const h = history;
  const n = Math.min(h.n, Math.round(seconds * 30));
  const t = new Float32Array(n);
  const v = new Float32Array(n);
  for (let k = 0; k < n; k++) {
    const idx = (h.head - n + k + h.cap) % h.cap;
    t[k] = h.data.t[idx];
    v[k] = h.data[key][idx];
  }
  return { t, v };
}

// ───────────────────────── React-facing store ─────────────────────────
export type DrawerId = 'scenario' | 'target' | 'disturbance' | 'tracking' | 'experiment' | 'optics' | 'plugin' | null;
export type ViewPreset = 'overview' | 'terminal' | 'link' | 'sensor' | 'orbit' | 'free' | 'follow';
export type FollowKey = 'sat3';
export type Quality = 'low' | 'medium' | 'high';
export type ThemeId = 'mission-control' | 'orbital-graphite' | 'aerospace-smoked-cream' | 'dusky-solar-cream';

export interface ThemeMeta {
  id: ThemeId;
  name: string;
  paletteNumber: string;
  subtitle: string;
  note: string;
  swatch: string[];
  viewport: string;
  spaceSecondary: string;
  panelSurface: string;
  elevatedSurface: string;
  borderDivider: string;
  primaryText: string;
  secondaryText: string;
  tertiaryText: string;
  strongText: string;
  isroOrange: string;
  orangeHighlight: string;
  successLock: string;
  alertLost: string;
  spatialBlue: string;
  axisColor: string;
}

export const THEME_CONFIGS: Record<ThemeId, ThemeMeta> = {
  'mission-control': {
    id: 'mission-control',
    name: 'Mission Control',
    paletteNumber: 'Palette 01',
    subtitle: 'Deep Space Navy',
    note: 'Default mission operations palette with midnight cosmic navy and starlight readouts',
    swatch: ['#050912', '#0B1320', '#FF8C1A', '#2DD36F'],
    viewport: '#050912',
    spaceSecondary: '#050912',
    panelSurface: '#0B1320',
    elevatedSurface: '#111D30',
    borderDivider: '#1D2F4A',
    primaryText: '#F4F8FD',
    secondaryText: '#A5BCD7',
    tertiaryText: '#8AA4C2',
    strongText: '#FFFFFF',
    isroOrange: '#FF8C1A',
    orangeHighlight: '#FFA347',
    successLock: '#2DD36F',
    alertLost: '#FF4D4D',
    spatialBlue: '#1E90FF',
    axisColor: '#F4F8FD',
  },
  'orbital-graphite': {
    id: 'orbital-graphite',
    name: 'Orbital Graphite',
    paletteNumber: 'Palette 02',
    subtitle: 'Smoked Cream',
    note: 'Deep orbital carbon chassis paired with high-contrast smoked cream instrumentation',
    swatch: ['#0B0D0F', '#202428', '#E4D7BD', '#E97824'],
    viewport: '#0B0D0F',
    spaceSecondary: '#15181B',
    panelSurface: '#202428',
    elevatedSurface: '#2B3034',
    borderDivider: '#41474C',
    primaryText: '#E4D7BD',
    secondaryText: '#C4B594',
    tertiaryText: '#A59678',
    strongText: '#F5EAD4',
    isroOrange: '#E97824',
    orangeHighlight: '#F28E42',
    successLock: '#3BA35C',
    alertLost: '#D9534F',
    spatialBlue: '#3B7189',
    axisColor: '#F5EAD4',
  },
  'aerospace-smoked-cream': {
    id: 'aerospace-smoked-cream',
    name: 'Aerospace Smoked Cream',
    paletteNumber: 'Palette 03',
    subtitle: 'Black-Side Cream',
    note: 'Deep smoked bronze-black chassis complementing deep space with warm cream readouts',
    swatch: ['#0B1117', '#24211B', '#E6D8BE', '#E87522'],
    viewport: '#0B1117',
    spaceSecondary: '#111B23',
    panelSurface: '#24211B',
    elevatedSurface: '#2F2B23',
    borderDivider: '#4A4234',
    primaryText: '#E6D8BE',
    secondaryText: '#C5B697',
    tertiaryText: '#A6977A',
    strongText: '#F6ECD6',
    isroOrange: '#E87522',
    orangeHighlight: '#F28C38',
    successLock: '#299653',
    alertLost: '#D84D45',
    spatialBlue: '#3B7189',
    axisColor: '#F6ECD6',
  },
  'dusky-solar-cream': {
    id: 'dusky-solar-cream',
    name: 'Dusky Solar Cream',
    paletteNumber: 'Palette 04',
    subtitle: 'Weathered Khaki-Cream',
    note: 'Weathered dusky cream surfaces shaded with black, paired with deep blue-black space',
    swatch: ['#BCAE88', '#D0C39E', '#100E0A', '#E87522'],
    viewport: '#0B1117',
    spaceSecondary: '#111B23',
    panelSurface: '#D0C39E',
    elevatedSurface: '#A89872',
    borderDivider: '#6E6041',
    primaryText: '#100E0A',
    secondaryText: '#262014',
    tertiaryText: '#3D3422',
    strongText: '#050403',
    isroOrange: '#E87522',
    orangeHighlight: '#F28C38',
    successLock: '#299653',
    alertLost: '#D84D45',
    spatialBlue: '#3B7189',
    axisColor: '#050403',
  },
};

export const THEMES: { id: ThemeId; name: string; sub: string; note: string; swatch: string[] }[] = Object.values(THEME_CONFIGS).map((c) => ({
  id: c.id,
  name: c.name,
  sub: c.subtitle,
  note: `${c.paletteNumber}: ${c.name} (${c.subtitle}) — ${c.note}`,
  swatch: c.swatch,
}));

function localStorageGet(k: string): string | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage.getItem(k) : null;
  } catch {
    return null;
  }
}
function localStorageSet(k: string, v: string) {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(k, v);
  } catch {
    /* storage unavailable */
  }
}

export const STATE_HEX: Record<TrackState, string> = {
  IDLE: '#8AA4C2',
  SEARCHING: '#FF8C1A',
  DETECTED: '#FFA347',
  ACQUIRING: '#FFA347',
  TRACKING: '#1E90FF',
  LOCKED: '#2DD36F',
  LOST: '#FF4D4D',
  REACQUIRING: '#FFA347',
};

export function applyTheme(t: ThemeId) {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.theme = t;
  const cfg = THEME_CONFIGS[t] ?? THEME_CONFIGS['mission-control'];
  STATE_HEX.SEARCHING = cfg.isroOrange;
  STATE_HEX.DETECTED = cfg.orangeHighlight;
  STATE_HEX.ACQUIRING = cfg.orangeHighlight;
  STATE_HEX.TRACKING = cfg.spatialBlue;
  STATE_HEX.LOCKED = cfg.successLock;
  STATE_HEX.LOST = cfg.alertLost;
  STATE_HEX.REACQUIRING = cfg.orangeHighlight;
  STATE_HEX.IDLE = cfg.tertiaryText;
}

function initialTheme(): ThemeId {
  const t = localStorageGet('netra.theme') as ThemeId | null;
  const ok = THEMES.some((x) => x.id === t) ? (t as ThemeId) : 'mission-control';
  applyTheme(ok);
  return ok;
}

interface AppState {
  tick: number;
  hud: Snapshot | null;
  config: SimConfig;
  providerKind: ProviderKind;
  providerStatus: 'connecting' | 'online' | 'error';
  providerError: string | null;
  serverUrl: string;
  running: boolean;
  demo: boolean;
  engineFps: number;
  timeScale: number;
  events: TransitionEvent[];
  drawer: DrawerId;
  view: ViewPreset;
  viewNonce: number;
  followKey: FollowKey;
  quality: Quality;
  theme: ThemeId;
  themeOpen: boolean;
  videoOpen: boolean;
  sensorTab: 'camera' | 'screen';
  autoReport: boolean;
  overlays: { labels: boolean; fov: boolean; trails: boolean; grid: boolean; truth: boolean; calibration: boolean; roi: boolean; space: boolean };
  sensorExpanded: boolean;
  analysisOpen: boolean;
  analysisTab: string;
  helpOpen: boolean;
  recording: { active: boolean; frames: number };
  replay: { name: string; length: number; position: number; playing: boolean } | null;
  toast: string | null;
  /** Increments whenever the run restarts (reset, preset, demo) — used to re-frame the camera. */
  resetNonce: number;

  connect: (kind: ProviderKind, opts?: { url?: string; recording?: Recording }) => Promise<void>;
  send: (cmd: EngineCommand) => void;
  patchConfig: (patch: DeepPartial<SimConfig>) => void;
  replaceConfig: (cfg: SimConfig) => void;
  setDrawer: (d: DrawerId) => void;
  setView: (v: ViewPreset) => void;
  flyTo: (k: FollowKey) => void;
  setQuality: (q: Quality) => void;
  setTheme: (t: ThemeId) => void;
  toggleOverlay: (k: keyof AppState['overlays']) => void;
  set: (p: Partial<AppState>) => void;
  startRecording: () => void;
  stopRecording: () => void;
  exportCsv: () => void;
  exportJson: () => void;
  downloadReport: (source: 'live' | 'recording', fmt?: ReportFormat) => void;
  seekReplay: (i: number) => void;
  notify: (msg: string, ms?: number) => void;
}

let provider: TelemetryProvider | null = null;
export const recorder = new Recorder();
let lastHud = 0;
let toastTimer: ReturnType<typeof setTimeout> | null = null;

export type ReportFormat = 'html' | 'md' | 'json';

/** Save a performance report as HTML (printable), Markdown or JSON. */
export function saveReport(rep: PerformanceReport, fmt: ReportFormat, base: string) {
  if (fmt === 'json') download(`${base}.json`, JSON.stringify(rep, null, 2), 'application/json');
  else if (fmt === 'md') download(`${base}.md`, reportMarkdown(rep), 'text/markdown');
  else download(`${base}.html`, reportHtml(rep), 'text/html');
}

export function download(name: string, text: string, type: string) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const stamp = () => new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);

export const useApp = create<AppState>((set, get) => {
  const onMessage = (m: EngineMessage) => {
    switch (m.type) {
      case 'snapshot': {
        const s = m.snapshot;
        if (live.snap && s.t < live.snap.t - 0.5) {
          clearHistory();
          set({ resetNonce: get().resetNonce + 1 });
        }
        if (s.state === 'DETECTED' && live.snap?.state !== 'DETECTED' && s.detection) {
          live.initialErrPx = Math.hypot(s.detection.x - s.camera.width / 2, s.detection.y - s.camera.height / 2);
        }
        live.snap = s;
        live.recent.push(s);
        if (live.recent.length > 40) live.recent.shift();
        if (s.plan) live.plan = s.plan;
        pushHistory(s);
        recorder.push(s);
        const now = performance.now();
        const newEvents = s.events.length ? [...get().events, ...s.events].slice(-250) : null;
        if (now - lastHud > 25 || newEvents) {
          lastHud = now;
          const rp = provider instanceof ReplayProvider ? provider : null;
          set({
            hud: s,
            tick: get().tick + 1,
            ...(get().providerStatus !== 'online' ? { providerStatus: 'online', providerError: null } : {}),
            ...(newEvents ? { events: newEvents } : {}),
            recording: { active: recorder.active, frames: recorder.frames.length },
            ...(rp ? { replay: { name: rp.recording.name, length: rp.length, position: rp.position, playing: rp.isPlaying } } : {}),
          });
        }
        break;
      }
      case 'frame':
        live.image = { width: m.width, height: m.height, frame: m.frame, data: m.data };
        live.imageVersion++;
        break;
      case 'config':
        set({ config: m.config });
        break;
      case 'status':
        set({
          providerStatus: 'online',
          providerError: null,
          running: m.running,
          demo: m.demo,
          engineFps: m.fps,
          timeScale: m.timeScale,
        });
        break;
      case 'error':
        set({ providerStatus: 'error', providerError: m.message, engineFps: 0 });
        get().notify(m.message);
        break;
    }
  };

  return {
    tick: 0,
    hud: null,
    config: DEFAULT_CONFIG,
    providerKind: 'local',
    providerStatus: 'connecting',
    providerError: null,
    serverUrl: DEFAULT_SERVER_URL,
    running: false,
    demo: false,
    engineFps: 0,
    timeScale: 1,
    events: [],
    drawer: null,
    view: 'overview',
    viewNonce: 0,
    followKey: 'sat3',
    quality: (localStorageGet('netra.quality') as Quality) ?? 'medium',
    theme: initialTheme(),
    themeOpen: false,
    videoOpen: false,
    sensorTab: 'camera',
    autoReport: localStorageGet('netra.autoReport') !== '0',
    overlays: { labels: true, fov: true, trails: true, grid: false, truth: false, calibration: false, roi: true, space: true },
    sensorExpanded: false,
    analysisOpen: false,
    analysisTab: 'error',
    helpOpen: false,
    recording: { active: false, frames: 0 },
    replay: null,
    toast: null,
    resetNonce: 0,

    async connect(kind, opts) {
      provider?.disconnect();
      provider = null;
      clearHistory();
      live.snap = null;
      live.image = null;
      live.imageVersion++;
      set({ providerKind: kind, providerStatus: 'connecting', providerError: null, events: [], replay: null, hud: null });
      let p: TelemetryProvider;
      if (kind === 'remote') p = new RemoteEngineProvider(opts?.url ?? get().serverUrl);
      else if (kind === 'replay' && opts?.recording) p = new ReplayProvider(opts.recording);
      else p = new LocalEngineProvider();
      try {
        await p.connect(onMessage);
        provider = p;
        set({ providerStatus: 'online', ...(opts?.url ? { serverUrl: opts.url } : {}) });
        if (kind === 'remote') {
          p.send({ type: 'replaceConfig', config: get().config });
          p.send({ type: 'start' });
        }
        if (kind === 'replay' && opts?.recording) {
          set({ replay: { name: opts.recording.name, length: opts.recording.frames.length, position: 0, playing: true } });
        }
      } catch (err) {
        set({ providerStatus: 'error', providerError: String((err as Error).message ?? err), engineFps: 0 });
        get().notify(`FastAPI: ${String((err as Error).message ?? err)}`);
        if (kind === 'remote') {
          provider = p;
        }
      }
    },

    send(cmd) {
      provider?.send(cmd);
      if (cmd.type === 'reset' || cmd.type === 'replaceConfig') clearHistory();
    },

    patchConfig(patch) {
      set({ config: mergeConfig(get().config, patch) });
      provider?.send({ type: 'config', patch });
    },

    replaceConfig(cfg) {
      set({ config: cfg });
      clearHistory();
      provider?.send({ type: 'replaceConfig', config: cfg });
    },

    setDrawer: (d) => set({ drawer: get().drawer === d ? null : d }),
    setView: (v) => set({ view: v, viewNonce: get().viewNonce + 1 }),
    flyTo: (k) => set({ view: 'follow', followKey: k, viewNonce: get().viewNonce + 1, overlays: { ...get().overlays, space: true } }),
    setQuality: (q) => {
      localStorageSet('netra.quality', q);
      set({ quality: q });
      provider?.send({ type: 'imageRate', hz: q === 'low' ? 8 : q === 'medium' ? 15 : 30 });
    },
    setTheme: (t) => {
      localStorageSet('netra.theme', t);
      applyTheme(t);
      set({ theme: t });
    },
    toggleOverlay: (k) => set({ overlays: { ...get().overlays, [k]: !get().overlays[k] } }),
    set: (p) => set(p),

    startRecording() {
      recorder.start();
      set({ recording: { active: true, frames: 0 } });
      get().notify('Recording telemetry…');
    },
    stopRecording() {
      recorder.stop();
      set({ recording: { active: false, frames: recorder.frames.length } });
      if (get().autoReport && recorder.frames.length > 1) {
        get().downloadReport('recording', 'html');
        get().notify(`Recorded ${recorder.frames.length} frames — performance report saved automatically`);
      } else get().notify(`Recorded ${recorder.frames.length} frames`);
    },
    downloadReport(source, fmt = 'html') {
      const kindLabel = get().providerKind === 'remote' ? 'FastAPI engine' : get().providerKind === 'replay' ? 'Replay' : 'Browser engine (local)';
      if (source === 'recording') {
        const last = recorder.frames[recorder.frames.length - 1];
        if (!last) return get().notify('Nothing recorded yet — press Record first');
        const rep = buildReport({ kind: 'recording', source: kindLabel, config: get().config, metrics: last.metrics, events: recorder.events });
        saveReport(rep, fmt, `netra-report-${stamp()}`);
      } else {
        const snap = live.snap;
        if (!snap) return get().notify('No telemetry yet');
        const rep = buildReport({ kind: 'live', source: kindLabel, config: get().config, metrics: snap.metrics, events: get().events });
        saveReport(rep, fmt, `netra-report-${stamp()}`);
      }
    },
    exportCsv() {
      if (!recorder.frames.length) return get().notify('Nothing recorded yet — press Record first');
      download(`netra-run-${stamp()}.csv`, recorder.toCsv(), 'text/csv');
    },
    exportJson() {
      if (!recorder.frames.length) return get().notify('Nothing recorded yet — press Record first');
      const rec = recorder.toRecording(`NETRA run ${stamp()}`, get().config, get().providerKind);
      download(`netra-run-${stamp()}.json`, JSON.stringify(rec), 'application/json');
    },
    seekReplay(i) {
      if (provider instanceof ReplayProvider) {
        provider.seek(i);
        clearHistory();
      }
    },
    notify(msg, ms = 3800) {
      if (toastTimer) clearTimeout(toastTimer);
      set({ toast: msg });
      toastTimer = setTimeout(() => set({ toast: null }), ms);
    },
  };
});

export const stateColor = (s: TrackState | undefined): string => {
  switch (s) {
    case 'SEARCHING':
      return 'var(--amber)';
    case 'DETECTED':
      return 'var(--amber-hi)';
    case 'ACQUIRING':
      return 'var(--amber-hi)';
    case 'TRACKING':
      return 'var(--ice)';
    case 'LOCKED':
      return 'var(--lock)';
    case 'LOST':
      return 'var(--lost)';
    case 'REACQUIRING':
      return 'var(--warn)';
    default:
      return 'var(--text-3)';
  }
};
