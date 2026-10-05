import { useState, useEffect, useRef, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { DrawerId, recorder, saveReport, stateColor, useApp } from '../state/store';
import { SCENARIO_PRESETS, presetConfig } from '../core/presets';
import { buildReport } from '../core/analysis/report';
import { SimConfig, TrajectoryKind } from '../core/config';
import { isRecording } from '../core/telemetry/recorder';
import type { BatchMessage, BatchRunResult } from '../engine/batch.worker';
import { Icon, Section, Seg, Slider, Toggle, fmt } from './ui';

export interface ToolDef {
  id: Exclude<DrawerId, null>;
  num: string;
  code: string;
  icon: string;
  label: string;
  tag: string;
  desc: string;
}

export const TOOLS: ToolDef[] = [
  {
    id: 'target',
    num: '01',
    code: 'TRGT',
    icon: 'target',
    label: 'Kinematics & Orbit',
    tag: 'DYNAMICS',
    desc: 'Configure orbital flight paths, target distance, velocity, and line-of-sight kinematics.',
  },
  {
    id: 'tracking',
    num: '02',
    code: 'LOOP',
    icon: 'tracking',
    label: 'Acquisition & Loop',
    tag: 'PIPELINE',
    desc: 'Tune PID control gains, Kalman filtering, acquisition thresholds, and closed-loop lock.',
  },
  {
    id: 'disturbance',
    num: '03',
    code: 'NOIS',
    icon: 'disturbance',
    label: 'Noise & Atmosphere',
    tag: 'TURBULENCE',
    desc: 'Simulate atmospheric scintillation, beam wander, sensor noise, and platform vibration.',
  },
  {
    id: 'scenario',
    num: '04',
    code: 'SCEN',
    icon: 'scenario',
    label: 'Flight Scenarios',
    tag: 'PROFILES',
    desc: 'Select mission profiles, LEO satellite passes, custom flight paths, and waypoint routes.',
  },
  {
    id: 'experiment',
    num: '05',
    code: 'ANLS',
    icon: 'experiment',
    label: 'Telemetry & Reports',
    tag: 'METRICS',
    desc: 'Run multi-trial Monte Carlo batches, export telemetry CSVs, and generate audit reports.',
  },
  {
    id: 'plugin',
    num: '06',
    code: 'ALGO',
    icon: 'code',
    label: 'Algorithm Plugins',
    tag: 'CUSTOM',
    desc: 'Load custom tracking, control, or vision modules with live parameter tuning and A/B verification.',
  },
];

export function ToolRail() {
  const drawer = useApp((s) => s.drawer);
  const setDrawer = useApp((s) => s.setDrawer);
  const set = useApp((s) => s.set);
  return (
    <nav className="rail-strip glass" aria-label="Tools">
      <div className="rail-strip-header">
        <span>HUD</span>
      </div>
      {TOOLS.map((t) => (
        <button
          key={t.id}
          className={`rail-btn ${drawer === t.id ? 'on' : ''}`}
          onClick={() => setDrawer(t.id)}
          aria-label={t.label}
        >
          <Icon name={t.icon} />
          <span className="rail-indicator" />
          <div className="tip">
            <div className="tip-header">
              <span className="tip-code">{t.code}</span>
              <span className="tip-tag">{t.tag}</span>
            </div>
            <div className="tip-label">{t.label}</div>
            <div className="tip-desc">{t.desc}</div>
          </div>
        </button>
      ))}
      <div className="sep" />
      <button
        className="rail-btn bench-btn"
        onClick={() => set({ videoOpen: true })}
        aria-label="Video benchmark"
      >
        <Icon name="film" />
        <div className="tip">
          <div className="tip-header">
            <span className="tip-code">BENCH</span>
            <span className="tip-tag">BYPASS</span>
          </div>
          <div className="tip-label">Video Benchmark · Camera Bypass</div>
          <div className="tip-desc">Feed video (.mp4) directly into the detector to benchmark centroid error against truth.</div>
        </div>
      </button>
      <button
        className="rail-btn bench-btn"
        onClick={() => window.open('http://localhost:8000/api/plugins/playground', '_blank')}
        aria-label="Plugin Playground"
      >
        <Icon name="code" />
        <div className="tip">
          <div className="tip-header">
            <span className="tip-code">ALGO</span>
            <span className="tip-tag">GUI</span>
          </div>
          <div className="tip-label">Plugin Playground</div>
          <div className="tip-desc">Open the standalone Algorithm Plugin Playground GUI in a new tab.</div>
        </div>
      </button>
    </nav>
  );
}

function useCfg() {
  const cfg = useApp((s) => s.config);
  const patch = useApp((s) => s.patchConfig);
  return { cfg, patch };
}

const PRESET_TAGS: Record<string, string> = {
  'open-sky': 'REF',
  'ps-baseline': 'PS169',
  'moving-platform': 'MOBILE',
  'high-jitter': 'JITTER',
  'weak-beacon': 'HAZE',
  'fast-target': 'SPEED',
  'acquisition-challenge': 'ACQ',
  'occlusion': 'OCCL',
  'leo-pass': 'ORBIT',
};

function ScenarioDrawer() {
  const { cfg, patch } = useCfg();
  const replace = useApp((s) => s.replaceConfig);
  const timeScale = useApp((s) => s.timeScale);
  const send = useApp((s) => s.send);
  const sc = cfg.scene;
  const activePreset = SCENARIO_PRESETS.find((p) => p.id === cfg.scenarioId) || SCENARIO_PRESETS[0];

  return (
    <>
      <Section title="Operational Presets">
        <div className="preset-grid">
          {SCENARIO_PRESETS.map((p) => (
            <button
              key={p.id}
              className={`preset-chip ${cfg.scenarioId === p.id ? 'on' : ''}`}
              onClick={() => replace(presetConfig(p.id, cfg.seed))}
              title={p.summary}
            >
              <span className="preset-dot" />
              <span className="preset-title">{p.name}</span>
              <span className="preset-tag">{PRESET_TAGS[p.id] || 'CASE'}</span>
            </button>
          ))}
        </div>
        {activePreset && (
          <div className="preset-detail">
            <span className="preset-desc">{activePreset.summary}</span>
          </div>
        )}
      </Section>
      <Section title="Simulation Speed">
        <div className="field" style={{ margin: '4px 0' }}>
          <label style={{ fontSize: 11.5 }}>Playback rate</label>
          <div style={{ gridColumn: '1 / -1' }}>
            <Seg
              value={String(timeScale)}
              options={['0.25', '0.5', '1', '2'].map((v) => ({ v, label: `${v}×` }))}
              onChange={(v) => send({ type: 'timeScale', value: parseFloat(v) })}
            />
          </div>
        </div>
      </Section>
      <Section title="Pointing Geometry" right={<span className="dim">resets loop</span>}>
        <Slider label="LOS azimuth" value={sc.losAzDeg} min={0} max={359} step={1} digits={0} unit="°" onChange={(v) => patch({ scene: { losAzDeg: v } })} />
        <Slider label="LOS elevation" value={sc.losElDeg} min={15} max={80} step={1} digits={0} unit="°" onChange={(v) => patch({ scene: { losElDeg: v } })} />
        <Slider label="Target altitude" value={sc.altitudeKm} min={300} max={1200} step={10} digits={0} unit=" km" onChange={(v) => patch({ scene: { altitudeKm: v } })} />
        <p className="note" style={{ fontSize: 10.5, marginTop: 4 }}>
          Station: <b>{sc.siteName}</b> ({sc.siteLatDeg.toFixed(2)}° N, {sc.siteLonDeg.toFixed(2)}° E).
        </p>
      </Section>
    </>
  );
}

const TRAJ: { v: TrajectoryKind; label: string }[] = [
  { v: 'stationary', label: 'Static' },
  { v: 'linear', label: 'Linear' },
  { v: 'circular', label: 'Circular' },
  { v: 'sinusoidal', label: 'Sinusoid' },
  { v: 'figure8', label: 'Figure-8' },
  { v: 'spiral', label: 'Spiral' },
  { v: 'random', label: 'Random' },
  { v: 'custom', label: 'Waypoints' },
  { v: 'orbital', label: 'LEO Orbit' },
];

function WaypointEditor({ cfg, onChange }: { cfg: SimConfig; onChange: (w: [number, number][]) => void }) {
  const hu = cfg.logic.searchHalfUDeg;
  const hv = cfg.logic.searchHalfVDeg;
  const W = 290;
  const H = 160;
  const sc = Math.min(W / (2 * hu), H / (2 * hv));
  const X = (u: number) => W / 2 + u * sc;
  const Y = (v: number) => H / 2 - v * sc;

  // Current beacon position from first waypoint, default center
  const wp = cfg.target.waypoints;
  const bu: number = wp.length > 0 ? wp[0][0] : 0;
  const bv: number = wp.length > 0 ? wp[0][1] : 0;

  const svgRef = useRef<SVGSVGElement>(null);
  const dragging = useRef(false);

  const toField = (clientX: number, clientY: number): [number, number] => {
    const r = svgRef.current!.getBoundingClientRect();
    const u = Math.max(-hu, Math.min(hu, (clientX - r.left - W / 2) / sc));
    const v = Math.max(-hv, Math.min(hv, -(clientY - r.top - H / 2) / sc));
    return [Math.round(u * 100) / 100, Math.round(v * 100) / 100];
  };

  const commit = (clientX: number, clientY: number) => {
    const [u, v] = toField(clientX, clientY);
    onChange([[u, v], [u, v]]);
  };

  useEffect(() => {
    const onMove = (e: MouseEvent) => { if (dragging.current) commit(e.clientX, e.clientY); };
    const onUp = (e: MouseEvent) => {
      if (dragging.current) { commit(e.clientX, e.clientY); dragging.current = false; }
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hu, hv]);

  return (
    <div>
      <svg
        ref={svgRef}
        width={W}
        height={H}
        style={{ background: 'rgba(var(--panel-rgb),0.6)', borderRadius: 6, cursor: 'crosshair', border: '1px solid var(--line)', display: 'block' }}
        onMouseDown={(e) => { dragging.current = true; commit(e.clientX, e.clientY); e.preventDefault(); }}
      >
        {/* Field boundary */}
        <rect x={X(-hu)} y={Y(hv)} width={2 * hu * sc} height={2 * hv * sc} fill="none" stroke="rgba(var(--line-rgb),0.18)" strokeWidth={1} rx={3} />
        {/* Crosshair guides */}
        <line style={{ stroke: 'rgba(var(--line-rgb),0.12)' }} x1={X(-hu)} y1={Y(0)} x2={X(hu)} y2={Y(0)} />
        <line style={{ stroke: 'rgba(var(--line-rgb),0.12)' }} x1={X(0)} y1={Y(-hv)} x2={X(0)} y2={Y(hv)} />
        {/* Axis labels */}
        <text x={X(hu) - 2} y={Y(0) - 4} fontSize={8} fill="rgba(var(--line-rgb),0.35)" textAnchor="end">+U</text>
        <text x={X(0) + 3} y={Y(hv) + 9} fontSize={8} fill="rgba(var(--line-rgb),0.35)">+V</text>
        {/* Drag halo */}
        <circle cx={X(bu)} cy={Y(bv)} r={14} fill="rgba(255,255,255,0.06)" />
        {/* Beacon dot */}
        <circle
          cx={X(bu)}
          cy={Y(bv)}
          r={6}
          fill="white"
          stroke="rgba(143,220,255,0.7)"
          strokeWidth={1.5}
          style={{ cursor: 'grab', filter: 'drop-shadow(0 0 4px rgba(143,220,255,0.8))' }}
        />
        {/* Position readout */}
        <text x={X(bu) + 10} y={Y(bv) - 8} fontSize={8.5} fill="var(--ice)" fontFamily="monospace">
          {bu.toFixed(2)}&deg;, {bv.toFixed(2)}&deg;
        </text>
      </svg>
      <p className="note" style={{ marginTop: 5 }}>
        Hold &amp; drag the beacon to reposition it in the field. Updates live in 2-D and 3-D.
      </p>
    </div>
  );
}


function TargetDrawer() {
  const { cfg, patch } = useCfg();
  const t = cfg.target;
  const cam = cfg.camera;
  const periodic = ['circular', 'sinusoidal', 'figure8', 'spiral'].includes(t.trajectory);
  return (
    <>
      <Section title="Flight Path & Kinematics">
        <div className="traj-grid">
          {TRAJ.map((item) => (
            <button
              key={item.v}
              className={`traj-chip ${t.trajectory === item.v ? 'on' : ''}`}
              onClick={() => patch({ target: { trajectory: item.v } })}
            >
              {item.label}
            </button>
          ))}
        </div>
        {(t.trajectory === 'linear' || t.trajectory === 'random' || t.trajectory === 'custom') && (
          <Slider label="Angular velocity" value={t.speedDegS} min={0} max={3} step={0.05} unit=" °/s" onChange={(v) => patch({ target: { speedDegS: v } })} />
        )}
        {periodic && (
          <>
            <Slider label="Pattern radius" value={t.amplitudeDeg} min={0.2} max={4} step={0.05} unit="°" onChange={(v) => patch({ target: { amplitudeDeg: v } })} />
            <Slider label="Cycle period" value={t.periodS} min={4} max={60} step={1} digits={0} unit=" s" onChange={(v) => patch({ target: { periodS: v } })} />
          </>
        )}
        {t.trajectory !== 'orbital' && t.trajectory !== 'custom' && t.trajectory !== 'stationary' && t.trajectory !== 'random' && (
          <Slider label="Flight track heading" value={t.headingDeg} min={0} max={359} step={1} digits={0} unit="°" onChange={(v) => patch({ target: { headingDeg: v } })} />
        )}
        {t.trajectory === 'custom' && <WaypointEditor cfg={cfg} onChange={(w) => patch({ target: { waypoints: w } })} />}
        {t.trajectory === 'orbital' && (
          <>
            <Slider label="Culmination elevation" value={cfg.scene.passMaxElDeg} min={20} max={85} step={1} digits={0} unit="°" onChange={(v) => patch({ scene: { passMaxElDeg: v } })} />
            <Slider label="Ephemeris time offset" value={cfg.scene.ephemerisErrorS} min={0} max={6} step={0.1} digits={1} unit=" s" onChange={(v) => patch({ scene: { ephemerisErrorS: v } })} />
            <p className="note">Circular orbit at {cfg.scene.altitudeKm} km. Sensor field scans the predicted overpass track.</p>
          </>
        )}
      </Section>

      <Section title="Optical Payload & Sensor">
        <Slider label="Horizontal FOV (tracking)" value={cam.hfovDeg} min={1} max={12} step={0.1} digits={1} unit="°" onChange={(v) => patch({ camera: { hfovDeg: v } })} />
        <Toggle label="Wide-field acquisition (zoom in after detection)" on={cam.wideAcquisition} onChange={(v) => patch({ camera: { wideAcquisition: v } })} />
        {cam.wideAcquisition && (
          <>
            <Slider label="Acquisition FOV" value={cam.wideHfovDeg} min={cam.hfovDeg} max={20} step={0.5} digits={1} unit="°" onChange={(v) => patch({ camera: { wideHfovDeg: v } })} />
            <Slider label="Zoom rate" value={cam.zoomRateDegS} min={2} max={30} step={1} digits={0} unit=" °/s" onChange={(v) => patch({ camera: { zoomRateDegS: v } })} />
          </>
        )}
        <Seg
          value={`${cam.width}x${cam.height}`}
          options={[
            { v: '640x480', label: '640×480 (PS)' },
            { v: '800x600', label: '800×600' },
            { v: '1024x768', label: '1024×768' },
          ]}
          onChange={(v) => {
            const [w, h] = v.split('x').map(Number);
            patch({ camera: { width: w, height: h } });
          }}
        />
        <Slider label="Frame rate (PS ≥ 30)" value={cam.frameRateHz} min={15} max={60} step={5} digits={0} unit=" Hz" onChange={(v) => patch({ camera: { frameRateHz: v } })} />
      </Section>
    </>
  );
}

function DisturbanceDrawer() {
  const { cfg, patch } = useCfg();
  const d = cfg.disturbance;
  return (
    <>
      <Section title="Atmospheric Channel & Turbulence">
        <Seg
          value={d.atmosphere}
          options={[
            { v: 'clear', label: 'Clear' },
            { v: 'haze', label: 'Haze' },
            { v: 'fog', label: 'Fog' },
            { v: 'rain', label: 'Rain' },
            { v: 'low_light', label: 'Low light' },
          ]}
          onChange={(v) => patch({ disturbance: { atmosphere: v } })}
        />
        <Slider label="Strength (contrast / brightness loss)" value={d.atmosphereStrength} min={0} max={1} step={0.05} onChange={(v) => patch({ disturbance: { atmosphereStrength: v } })} />
        <Slider label="Turbulence (scintillation + wander)" value={d.turbulence} min={0} max={1} step={0.05} onChange={(v) => patch({ disturbance: { turbulence: v } })} />
      </Section>
      <Section title="Detector & Photonic Noise">
        <Slider label="Gaussian σ" value={d.gaussianNoise} min={0} max={20} step={0.5} digits={1} unit=" DN" onChange={(v) => patch({ disturbance: { gaussianNoise: v } })} />
        <Slider label="Salt & pepper" value={d.saltPepper * 100} min={0} max={10} step={0.1} digits={1} unit=" %" onChange={(v) => patch({ disturbance: { saltPepper: v / 100 } })} />
        <Toggle label="Poisson (shot) noise" on={d.poisson} onChange={(v) => patch({ disturbance: { poisson: v } })} />
      </Section>
      <Section title="Mechanical Jitter & Wind Loads">
        <Slider label="Camera jitter (±/frame)" value={d.jitterPx} min={0} max={20} step={0.5} digits={1} unit=" px" onChange={(v) => patch({ disturbance: { jitterPx: v } })} />
        <Slider label="Platform vibration" value={d.vibrationPx} min={0} max={20} step={0.5} digits={1} unit=" px" onChange={(v) => patch({ disturbance: { vibrationPx: v } })} />
        <Slider label="Vibration frequency" value={d.vibrationHz} min={0.5} max={20} step={0.5} digits={1} unit=" Hz" onChange={(v) => patch({ disturbance: { vibrationHz: v } })} />
        <div className="field">
          <label>Platform motion</label>
          <span />
          <div style={{ gridColumn: '1 / -1' }}>
            <Seg
              value={d.platformMotion}
              options={[
                { v: 'none', label: 'None' },
                { v: 'linear', label: 'Linear' },
                { v: 'circular', label: 'Circular' },
                { v: 'random', label: 'Random' },
              ]}
              onChange={(v) => patch({ disturbance: { platformMotion: v } })}
            />
          </div>
        </div>
        {d.platformMotion !== 'none' && (
          <Slider label="Platform motion amplitude" value={d.platformMotionPx} min={0} max={40} step={1} digits={0} unit=" px" onChange={(v) => patch({ disturbance: { platformMotionPx: v } })} />
        )}
        <Slider label="Wind torque (rate σ)" value={d.windDegS} min={0} max={1} step={0.01} unit=" °/s" onChange={(v) => patch({ disturbance: { windDegS: v } })} />
      </Section>
    </>
  );
}

function TrackingDrawer() {
  const { cfg, patch } = useCfg();
  const c = cfg.control;
  const g = cfg.gimbal;
  const l = cfg.logic;

  return (
    <>

      {/* 5. PID Alignment Controller */}
      <Section title="Gimbal Servo Controller (PID)">
        <Slider label="Kp (Proportional)" value={c.kp} min={0} max={20} step={0.1} digits={1} onChange={(v) => patch({ control: { kp: v } })} />
        <Slider label="Ki (Integral)" value={c.ki} min={0} max={5} step={0.05} digits={2} onChange={(v) => patch({ control: { ki: v } })} />
        <Slider label="Kd (Derivative)" value={c.kd} min={0} max={1} step={0.01} digits={2} onChange={(v) => patch({ control: { kd: v } })} />
        <Slider label="Integral limit" value={c.integralLimit} min={0} max={0.5} step={0.01} digits={2} unit=" °·s" onChange={(v) => patch({ control: { integralLimit: v } })} />
        <Toggle label="Rate feed-forward (Kalman velocity)" on={c.feedForward} onChange={(v) => patch({ control: { feedForward: v } })} />
        <Slider label="Control update rate" value={c.controlRateHz} min={20} max={120} step={10} digits={0} unit=" Hz" onChange={(v) => patch({ control: { controlRateHz: v } })} />
      </Section>

      {/* 6. Hardware Gimbal & State Limits */}
      <Section title="Kinematic Constraints & Lock Gates">
        <Slider label="Max gimbal rate" value={g.maxRateDegS} min={1} max={15} step={0.5} digits={1} unit=" °/s" onChange={(v) => patch({ gimbal: { maxRateDegS: v } })} />
        <Slider label="Max acceleration" value={g.maxAccelDegS2} min={5} max={120} step={5} digits={0} unit=" °/s²" onChange={(v) => patch({ gimbal: { maxAccelDegS2: v } })} />
        <Slider label="Lock threshold" value={l.lockPx} min={2} max={30} step={1} digits={0} unit=" px" onChange={(v) => patch({ logic: { lockPx: v, unlockPx: Math.max(v + 2, l.unlockPx) } })} />
        <Slider label="Frames to lock" value={l.lockFrames} min={1} max={30} step={1} digits={0} onChange={(v) => patch({ logic: { lockFrames: v } })} />
        <Slider label="Coast frames before LOST" value={l.coastFrames} min={1} max={30} step={1} digits={0} onChange={(v) => patch({ logic: { coastFrames: v } })} />
        <Slider label="Reacquisition timeout" value={l.reacquireTimeoutS} min={1} max={10} step={0.5} digits={1} unit=" s" onChange={(v) => patch({ logic: { reacquireTimeoutS: v } })} />
      </Section>
    </>
  );
}

function BatchPanel() {
  const cfg = useApp((s) => s.config);
  const [runs, setRuns] = useState(10);
  const [dur, setDur] = useState(15);
  const [results, setResults] = useState<BatchRunResult[]>([]);
  const [busy, setBusy] = useState(false);
  const worker = useRef<Worker | null>(null);
  useEffect(() => () => worker.current?.terminate(), []);
  const start = () => {
    worker.current?.terminate();
    const w = new Worker(new URL('../engine/batch.worker.ts', import.meta.url), { type: 'module' });
    worker.current = w;
    setResults([]);
    setBusy(true);
    w.onmessage = (e: MessageEvent<BatchMessage>) => {
      if (e.data.type === 'progress') setResults((r: BatchRunResult[]) => [...r, e.data.type === 'progress' ? e.data.result : r[0]]);
      else setBusy(false);
    };
    w.postMessage({ config: cfg, runs, durationS: dur, seed0: cfg.seed * 1000 });
  };
  const summary = useMemo(() => {
    if (!results.length) return null;
    const acq = results.map((r: BatchRunResult) => r.metrics.acquisitionS).filter((x: number | null): x is number => x !== null);
    const rms = results.map((r: BatchRunResult) => r.metrics.errRmsPx).filter((x: number | null): x is number => x !== null);
    const pass = results.filter((r: BatchRunResult) => r.metrics.acceptance.acquisition && r.metrics.acceptance.error && r.metrics.acceptance.loss !== false).length;
    return {
      acqMean: acq.length ? acq.reduce((a: number, b: number) => a + b, 0) / acq.length : null,
      acqMax: acq.length ? Math.max(...acq) : null,
      rmsMean: rms.length ? rms.reduce((a: number, b: number) => a + b, 0) / rms.length : null,
      locked: acq.length,
      pass,
    };
  }, [results]);
  const exportCsv = () => {
    const head = 'seed,final_state,acquisition_s,err_rms_px,err_max_px,loss_pct,reacq_max_s,centroid_rms_px,fps_capacity';
    const rows = results.map((r: BatchRunResult) =>
      [r.seed, r.finalState, r.metrics.acquisitionS ?? '', r.metrics.errRmsPx ?? '', r.metrics.errMaxPx ?? '', r.metrics.lossPct ?? '', r.metrics.reacqMaxS ?? '', r.metrics.centroidRmsPx ?? '', r.metrics.fps.toFixed(0)].join(','),
    );
    const blob = new Blob([[head, ...rows].join('\n')], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `netra-batch-${cfg.scenarioId}.csv`;
    a.click();
  };
  return (
    <Section title="Monte Carlo Batch Trials" right={<span className="analysis-badge-sub">HEADLESS WORKER</span>}>
      <div className="analysis-card">
        <Slider label="Trial runs" value={runs} min={2} max={50} step={1} digits={0} onChange={setRuns} />
        <Slider label="Duration per run" value={dur} min={5} max={60} step={1} digits={0} unit=" s" onChange={setDur} />
        <div className="analysis-btn-row">
          <button className="btn sm primary" onClick={start} disabled={busy} style={{ flex: 1.2 }}>
            <Icon name="play" size={13} /> {busy ? `Running ${results.length}/${runs}…` : 'Run Batch'}
          </button>
          <button className="btn sm" onClick={exportCsv} disabled={!results.length} style={{ flex: 1 }}>
            <Icon name="download" size={13} /> CSV
          </button>
          <button
            className="btn sm"
            disabled={!results.length || busy}
            onClick={() => saveReport(buildReport({ kind: 'batch', source: 'Browser engine (batch worker)', config: cfg, batch: results }), 'html', `netra-batch-report-${cfg.scenarioId}`)}
            style={{ flex: 1 }}
          >
            <Icon name="report" size={13} /> Report
          </button>
        </div>
      </div>
      {summary && (
        <div className="batch-scorecard">
          <div className="scorecard-grid">
            <div className="score-tile">
              <span className="score-label">Lock Success</span>
              <span className="score-val" style={{ color: summary.locked === results.length ? 'var(--lock)' : 'var(--amber)' }}>
                {summary.locked}<small>/{results.length}</small>
              </span>
            </div>
            <div className="score-tile">
              <span className="score-label">PS-169 Pass</span>
              <span className="score-val" style={{ color: summary.pass === results.length ? 'var(--lock)' : 'var(--ice)' }}>
                {summary.pass}<small>/{results.length}</small>
              </span>
            </div>
            <div className="score-tile">
              <span className="score-label">Mean Acq Time</span>
              <span className="score-val">
                {fmt(summary.acqMean, 2)}<small>s (max {fmt(summary.acqMax, 2)}s)</small>
              </span>
            </div>
            <div className="score-tile">
              <span className="score-label">Mean RMS Error</span>
              <span className="score-val">
                {fmt(summary.rmsMean, 2)}<small>px</small>
              </span>
            </div>
          </div>
        </div>
      )}
      {results.length > 0 && (
        <div className="batch-table-wrap">
          <table className="batch-table">
            <thead>
              <tr>
                <th>SEED</th>
                <th>ACQ (S)</th>
                <th>RMS (PX)</th>
                <th>LOSS %</th>
                <th>RE-ACQ</th>
                <th>STATE</th>
              </tr>
            </thead>
            <tbody>
              {results.slice(-12).map((r: BatchRunResult) => (
                <tr key={r.seed}>
                  <td className="mono">{r.seed}</td>
                  <td className="mono">{fmt(r.metrics.acquisitionS, 2)}</td>
                  <td className="mono">{fmt(r.metrics.errRmsPx, 2)}</td>
                  <td className="mono">{fmt(r.metrics.lossPct, 1)}%</td>
                  <td className="mono">{fmt(r.metrics.reacqMaxS, 2)}s</td>
                  <td>
                    <span className={`state-chip-xs ${r.finalState.toLowerCase().includes('track') || r.finalState.toLowerCase().includes('fine') ? 'lock' : 'warn'}`}>
                      {r.finalState.slice(0, 5)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}


function ReportPanel() {
  const autoReport = useApp((s) => s.autoReport);
  const { downloadReport, set } = useApp.getState();
  const rec = useApp((s) => s.recording);
  return (
    <Section title="Mission Performance Analysis" right={<span className="analysis-badge-sub">AUDIT READY</span>}>
      <div className="analysis-card">
        <p className="analysis-card-desc">
          Telemetry audit of link duration, tracking FPS, acquisition latency, RMS/peak pointing error, PS169 compliance & flight state history.
        </p>
        <div className="report-action-group">
          <button className="btn sm primary report-main-btn" onClick={() => downloadReport('live', 'html')}>
            <Icon name="report" size={14} /> Full Audit Report (Live Run)
          </button>
          <div className="report-alt-row">
            <button className="btn sm" onClick={() => downloadReport('live', 'md')}>
              Markdown
            </button>
            <button className="btn sm" onClick={() => downloadReport('live', 'json')}>
              JSON Data
            </button>
            <button className="btn sm" onClick={() => downloadReport('recording', 'html')} disabled={!rec.frames}>
              Rec Report
            </button>
          </div>
        </div>
        <div className="analysis-toggle-wrap">
          <Toggle
            label="Auto-export report when recording finishes"
            on={autoReport}
            onChange={(v) => {
              try {
                localStorage.setItem('netra.autoReport', v ? '1' : '0');
              } catch {
                /* storage unavailable */
              }
              set({ autoReport: v });
            }}
          />
        </div>
      </div>
    </Section>
  );
}

function ExperimentDrawer() {
  const kind = useApp((s) => s.providerKind);
  const status = useApp((s) => s.providerStatus);
  const err = useApp((s) => s.providerError);
  const serverUrl = useApp((s) => s.serverUrl);
  const rec = useApp((s) => s.recording);
  const events = useApp((s) => s.events);
  const { connect, startRecording, stopRecording, exportCsv, exportJson, notify, send } = useApp.getState();
  const running = useApp((s) => s.running);
  const [url, setUrl] = useState(serverUrl);
  const file = useRef<HTMLInputElement>(null);

  const statusTone = status;

  return (
    <>
      <Section
        title="Execution Backend & Connectivity"
        right={
          <span className={`status-indicator-pill ${statusTone}`}>
            <span className="rec-dot-pulse" />
            {status.toUpperCase()}
          </span>
        }
      >
        <div className="analysis-card">
          <Seg
            value={kind === 'replay' ? 'local' : kind}
            options={[
              { v: 'local', label: 'Local (Browser)' },
              { v: 'remote', label: 'FastAPI Server' },
            ]}
            onChange={(v) => connect(v, v === 'remote' ? { url } : undefined)}
          />
          <div className="remote-connect-box">
            <span className="remote-label">FastAPI Endpoint</span>
            <div className="remote-input-row">
              <input
                type="text"
                className="remote-input"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="http://127.0.0.1:8000"
              />
              <button className="btn sm" onClick={() => connect('remote', { url })}>
                Connect
              </button>
            </div>
          </div>
          {err && (
            <div className="backend-err-box">
              <Icon name="warn" size={13} />
              <span>{err}</span>
            </div>
          )}
        </div>
      </Section>

      <Section
        title="Live Session & Recording"
        right={
          <span className={`rec-status-pill ${rec.active ? 'active' : ''}`}>
            {rec.active && <span className="rec-dot-pulse" />}
            {rec.active ? 'REC ACTIVE' : 'IDLE'}
          </span>
        }
      >
        <div className="analysis-card">
          <div className="analysis-btn-row">
            <button className={`btn sm ${running ? '' : 'primary'}`} onClick={() => send({ type: running ? 'pause' : 'start' })} style={{ flex: 1 }}>
              <Icon name={running ? 'pause' : 'play'} size={13} /> {running ? 'Pause Sim' : 'Start Sim'}
            </button>
            <button className="btn sm" onClick={() => send({ type: 'reset' })} disabled={kind === 'replay'} style={{ flex: 1 }}>
              <Icon name="reset" size={13} /> Reset
            </button>
            <button
              className={`btn sm rec ${rec.active ? 'on' : ''}`}
              onClick={() => (rec.active ? stopRecording() : startRecording())}
              style={{ flex: 1.2 }}
            >
              <span className="led" />
              {rec.active ? 'Stop Rec' : 'Record'}
            </button>
          </div>

          <div className="rec-stats-bar">
            <div className="rec-stat-col">
              <span className="stat-sub">Buffer</span>
              <span className="stat-val mono">{rec.frames}<small> pts</small></span>
            </div>
            <div className="rec-stat-col">
              <span className="stat-sub">Duration</span>
              <span className="stat-val mono">{(rec.frames / 30).toFixed(1)}<small> s</small></span>
            </div>
            <div className="rec-stat-col">
              <span className="stat-sub">Rate</span>
              <span className="stat-val mono">30<small> Hz</small></span>
            </div>
          </div>

          <div className="rec-tools-grid">
            <button className="btn sm" onClick={exportCsv}>
              <Icon name="download" size={13} /> CSV Export
            </button>
            <button className="btn sm" onClick={exportJson}>
              <Icon name="download" size={13} /> JSON Export
            </button>
            <button
              className="btn sm"
              onClick={() => {
                if (!recorder.frames.length) return notify('Nothing recorded yet');
                connect('replay', { recording: recorder.toRecording('In-memory recording', useApp.getState().config, kind) });
              }}
            >
              <Icon name="play" size={13} /> Replay
            </button>
            <button className="btn sm" onClick={() => file.current?.click()}>
              <Icon name="upload" size={13} /> Load JSON
            </button>
          </div>

          <input
            ref={file}
            type="file"
            accept="application/json,.json"
            style={{ display: 'none' }}
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              try {
                const data = JSON.parse(await f.text());
                if (!isRecording(data)) throw new Error('Not an NETRA recording');
                connect('replay', { recording: data });
              } catch (x) {
                notify(`Could not load recording: ${(x as Error).message}`);
              }
              e.target.value = '';
            }}
          />
        </div>
      </Section>

      <ReportPanel />
      <BatchPanel />

      <Section title="Flight State Transition Log" right={<span className="analysis-badge-sub">{events.length} EVENTS</span>}>
        <div className="telemetry-log-console">
          {events.length === 0 ? (
            <div className="log-empty">No state transitions recorded yet</div>
          ) : (
            [...events].reverse().slice(0, 80).map((e, i) => {
              const col = e.to ? stateColor(e.to) : 'var(--text-3)';
              return (
                <div key={i} className="log-entry">
                  <span className="log-time mono">T+{e.t.toFixed(2)}s</span>
                  {e.to && (
                    <span
                      className="log-state-tag"
                      style={{
                        color: col,
                        background: `color-mix(in srgb, ${col} 15%, transparent)`,
                        borderColor: `color-mix(in srgb, ${col} 35%, transparent)`,
                      }}
                    >
                      {e.to}
                    </span>
                  )}
                  <span className="log-msg" title={e.message}>
                    {e.message}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </Section>
    </>
  );
}

const TITLES: Record<Exclude<DrawerId, null>, { num: string; code: string; title: string; tag: string }> = {
  target: { num: '01', code: 'TRGT', title: 'Kinematics & Orbit', tag: 'DYNAMICS' },
  optics: { num: '01', code: 'TRGT', title: 'Kinematics & Orbit', tag: 'DYNAMICS' },
  tracking: { num: '02', code: 'LOOP', title: 'Acquisition & Loop', tag: 'PIPELINE' },
  disturbance: { num: '03', code: 'NOIS', title: 'Noise & Atmosphere', tag: 'TURBULENCE' },
  scenario: { num: '04', code: 'SCEN', title: 'Flight Scenarios', tag: 'PROFILES' },
  experiment: { num: '05', code: 'ANLS', title: 'Telemetry & Reports', tag: 'METRICS' },
  plugin: { num: '06', code: 'ALGO', title: 'Algorithm Plugins', tag: 'CUSTOM' },
};

export function RightNavbar() {
  const activeDrawer = useApp((s) => s.drawer);
  const setDrawer = useApp((s) => s.setDrawer);
  const set = useApp((s) => s.set);
  const meta = activeDrawer ? (TITLES[activeDrawer] || TITLES.target) : null;

  return (
    <div className={`right-navbar ${activeDrawer ? 'drawer-open' : 'drawer-closed'}`} aria-label="Controls & Navigation">
      {/* Drawer Content Pane - appears on clicking only */}
      {activeDrawer && meta && (
        <aside className="drawer-panel glass" aria-label={meta.title}>
          <div className="drawer-head">
            <div className="drawer-head-telemetry">
              <div className="drawer-badge-row">
                <span className="drawer-sec-tag">{meta.tag}</span>
                <span className="drawer-status-chip">
                  <span className="pulse-dot" />
                  <span>ARMED</span>
                </span>
              </div>
              <div className="drawer-title-row">
                <h3 className="drawer-title">{meta.title}</h3>
              </div>
            </div>
            <div className="drawer-head-grid-deco">
              <span className="deco-code">{meta.code}</span>
              <span className="deco-line" />
            </div>
            <button
              className="drawer-close-btn"
              onClick={() => setDrawer(activeDrawer)}
              title="Close panel (Esc)"
              aria-label="Close panel"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M2 2L10 10M10 2L2 10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>
          </div>
          <div className="drawer-body">
            {(activeDrawer === 'target' || activeDrawer === 'optics') && <TargetDrawer />}
            {activeDrawer === 'tracking' && <TrackingDrawer />}
            {activeDrawer === 'disturbance' && <DisturbanceDrawer />}
            {activeDrawer === 'scenario' && <ScenarioDrawer />}
            {activeDrawer === 'experiment' && <ExperimentDrawer />}
            {activeDrawer === 'plugin' && <PluginDrawer />}
          </div>
        </aside>
      )}

      {/* Embedded Tool Rail Icon Strip */}
      <nav className="rail-strip glass" aria-label="Tools">
        <div className="rail-strip-header">
          <span>HUD</span>
        </div>
        {TOOLS.map((t) => {
          const isActive = activeDrawer === t.id;
          return (
            <button
              key={t.id}
              className={`rail-btn ${isActive ? 'on' : ''}`}
              onClick={() => setDrawer(t.id)}
              aria-label={t.label}
            >
              <Icon name={t.icon} />
              <span className="rail-indicator" />
              <div className="tip">
                <div className="tip-header">
                  <span className="tip-code">{t.code}</span>
                  <span className="tip-tag">{t.tag}</span>
                </div>
                <div className="tip-label">{t.label}</div>
                <div className="tip-desc">{t.desc}</div>
              </div>
            </button>
          );
        })}
        <div className="sep" />
        <button
          className="rail-btn bench-btn"
          onClick={() => set({ videoOpen: true })}
          aria-label="Video benchmark"
        >
          <Icon name="film" />
          <div className="tip">
            <div className="tip-header">
              <span className="tip-code">BENCH</span>
              <span className="tip-tag">BYPASS</span>
            </div>
            <div className="tip-label">Video Benchmark · Camera Bypass</div>
            <div className="tip-desc">Feed video (.mp4) directly into the detector to benchmark centroid error against truth.</div>
          </div>
        </button>
        <button
          className="rail-btn bench-btn"
          onClick={() => window.open('http://localhost:8000/api/plugins/playground', '_blank')}
          aria-label="Plugin Playground"
        >
          <Icon name="code" />
          <div className="tip">
            <div className="tip-header">
              <span className="tip-code">ALGO</span>
              <span className="tip-tag">GUI</span>
            </div>
            <div className="tip-label">Plugin Playground</div>
            <div className="tip-desc">Open the standalone Algorithm Plugin Playground GUI in a new tab.</div>
          </div>
        </button>
      </nav>
    </div>
  );
}

export function Drawer() {
  return null;
}

const DEFAULT_CODE = {
  tracking: `def track(measurement, dt, state, ctx, params):
    """
    ================================================================================
    TRACKING PLUGIN CONTRACT: State Estimation & Trajectory Filtering
    ================================================================================
    INPUT PARAMETERS EXPLANATION:
    --------------------------------------------------------------------------------
    1. measurement (dict or None):
       - If target is detected by the Vision stage:
         - measurement["x"] (float): Measured horizontal spot centroid in pixels (0.0 to width).
         - measurement["y"] (float): Measured vertical spot centroid in pixels (0.0 to height).
         - measurement["confidence"] (float): Blob detection confidence score (0.0 to 1.0).
       - If target is occluded, lost, or obscured by clouds/haze/noise: None.
       * Objective: Smooth noise when measurement is present; coast when measurement is None.

    2. dt (float):
       - Elapsed time since the last tracking update in seconds (~0.0333 s at 30 Hz).
       * Used to project kinematic state forward: predicted_pos = pos + velocity * dt.

    3. state (dict):
       - Persistent memory dictionary preserved across all simulation frames for this plugin.
       * Stores internal filter variables: estimated position, velocity, covariances, flags.
       * Initialized on the first frame when "x" not in state.

    4. ctx (dict):
       - Real-time engine telemetry and sensor calibration context:
         - ctx["cam_cx"]      (float): Optical boresight center X in pixels (320.0).
         - ctx["cam_cy"]      (float): Optical boresight center Y in pixels (240.0).
         - ctx["frame_index"] (int)  : Monotonically increasing frame counter (0, 1, 2, ...).
         - ctx["timestamp_s"] (float): Elapsed mission time in seconds.
         - ctx["fsm_state"]   (str)  : Current engine state ("TRACK", "ACQUIRE", "LOST").
         - ctx["atmosphere"]  (str)  : Atmospheric weather condition ("clear", "fog", etc.).
         - ctx["candidates"]  (list) : Alternative detection candidates in the current frame.

    5. params (dict):
       - User-tunable hyperparameters extracted via params.get("param_name", default_val).
       * NOTE: Any params.get() defined here automatically creates a live tuning slider in the GUI!
    ================================================================================
    """
    # ── [1. DEMO CODE: FETCH HYPERPARAMETERS] ─────────────────────────────────
    # Live sliders are auto-discovered from these calls:
    alpha = params.get("alpha", 0.85)       # Position innovation weight (0.0 to 1.0)
    beta = params.get("beta", 0.005)        # Velocity innovation gain (> 0.0)

    cam_cx = ctx.get("cam_cx", 320.0)
    cam_cy = ctx.get("cam_cy", 240.0)
    dt_c = max(float(dt), 1e-4)

    # ── [2. DEMO CODE: INITIALIZE STATE ON FIRST FRAME] ──────────────────────
    if "x" not in state:
        if measurement is None:
            # Fallback to boresight center with zero velocity
            return {"x": cam_cx, "y": cam_cy, "vx": 0.0, "vy": 0.0}
        state["x"] = float(measurement["x"])
        state["y"] = float(measurement["y"])
        state["vx"] = 0.0
        state["vy"] = 0.0
        return {"x": state["x"], "y": state["y"], "vx": 0.0, "vy": 0.0}

    # ── [3. DEMO CODE: TIME UPDATE / KINEMATIC PREDICTION] ───────────────────
    pred_x = state["x"] + state["vx"] * dt_c
    pred_y = state["y"] + state["vy"] * dt_c

    # ── [4. DEMO CODE: MEASUREMENT UPDATE OR COASTING] ────────────────────────
    if measurement is not None:
        # Innovation residual: difference between actual measurement and prediction
        res_x = float(measurement["x"]) - pred_x
        res_y = float(measurement["y"]) - pred_y

        # Alpha-Beta correction update
        state["x"] = pred_x + alpha * res_x
        state["y"] = pred_y + alpha * res_y
        state["vx"] = state["vx"] + (beta / dt_c) * res_x
        state["vy"] = state["vy"] + (beta / dt_c) * res_y
    else:
        # Measurement lost: coast smoothly on previous velocity without sudden jumps
        state["x"] = pred_x
        state["y"] = pred_y

    # ── [5. RETURN CONTRACT] ──────────────────────────────────────────────────
    # OUTPUT EXPLANATION:
    # --------------------------------------------------------------------------
    # Return a dictionary with exact keys "x", "y", "vx", "vy":
    #   - "x"  (float): Filtered horizontal target position in image coordinates [0..width].
    #   - "y"  (float): Filtered vertical target position in image coordinates [0..height].
    #   - "vx" (float): Estimated horizontal target velocity in pixels/second.
    #   - "vy" (float): Estimated vertical target velocity in pixels/second.
    # * What the engine does: Feeds x, y, vx, vy into the Control servo loop and evaluates lock status.
    # --------------------------------------------------------------------------
    return {
        "x": float(state["x"]),
        "y": float(state["y"]),
        "vx": float(state["vx"]),
        "vy": float(state["vy"]),
    }`,

  vision: `def detect(image, width, height, ctx, params):
    """
    ================================================================================
    VISION PLUGIN CONTRACT: Target Beacon Detection & Centroiding
    ================================================================================
    INPUT PARAMETERS EXPLANATION:
    --------------------------------------------------------------------------------
    1. image (numpy.ndarray):
       - 2D array of shape (height, width) with dtype uint8 (values from 0 to 255).
       - Grayscale frame captured directly by the telescope camera sensor.
       - Contains background sky, turbulence scintillation, haze, noise, and beacon spot.
       - Access pixel at row y (0..height-1), col x (0..width-1) via: image[y, x].

    2. width (int):
       - Frame width in viewport pixels (typically 640).

    3. height (int):
       - Frame height in viewport pixels (typically 480).

    4. ctx (dict):
       - Real-time engine telemetry and optical context:
         - ctx["frame_index"]   (int)  : Monotonically increasing frame counter (0, 1, 2, ...).
         - ctx["timestamp_s"]   (float): Elapsed mission time in seconds.
         - ctx["cam_cx"]        (float): Optical principal center X in pixels (320.0).
         - ctx["cam_cy"]        (float): Optical principal center Y in pixels (240.0).
         - ctx["scintillation"] (float): Atmospheric turbulence scintillation variance.
         - ctx["atmosphere"]    (str)  : Current weather condition ("clear", "fog", "rain", etc.).

    5. params (dict):
       - User-tunable hyperparameters extracted via params.get("param_name", default_val).
       * NOTE: Any params.get() defined here automatically creates a live tuning slider in the GUI!
    ================================================================================
    """
    import numpy as np

    # ── [1. DEMO CODE: FETCH HYPERPARAMETERS] ─────────────────────────────────
    # Live sliders are auto-discovered from these calls:
    threshold = params.get("threshold", 180)    # Intensity threshold cutoff (0 to 255)
    min_area = params.get("min_area", 1)        # Minimum active pixels to consider valid

    # ── [2. DEMO CODE: INTENSITY THRESHOLDING & MASK CREATION] ────────────────
    mask = image >= threshold
    if not np.any(mask):
        # Target not visible or below intensity threshold -> return None to signal loss
        return None

    # ── [3. DEMO CODE: SUB-PIXEL INTENSITY CENTROIDING (Center of Gravity)] ──
    y_coords, x_coords = np.where(mask)
    if len(x_coords) < min_area:
        return None

    weights = image[y_coords, x_coords].astype(float)
    total_w = np.sum(weights)
    if total_w < 1e-5:
        return None

    # Compute intensity-weighted centroid for sub-pixel accuracy
    cx = float(np.sum(x_coords * weights) / total_w)
    cy = float(np.sum(y_coords * weights) / total_w)
    confidence = min(1.0, float(np.max(weights) / 255.0))

    # ── [4. RETURN CONTRACT] ──────────────────────────────────────────────────
    # OUTPUT EXPLANATION:
    # --------------------------------------------------------------------------
    # Return EITHER:
    #   A dictionary with exact keys "x", "y", "confidence":
    #     - "x"          (float): Sub-pixel horizontal position in image pixels (0.0 to width).
    #     - "y"          (float): Sub-pixel vertical position in image pixels (0.0 to height).
    #     - "confidence" (float): Detection quality score between 0.0 (low) and 1.0 (high).
    #   OR:
    #     None: Indicating target is occluded, lost, or below detection threshold.
    # * What the engine does: Constructs a Detection object for the Tracking filter to consume.
    # --------------------------------------------------------------------------
    return {
        "x": cx,
        "y": cy,
        "confidence": confidence,
    }`,

  control: `def control(error, velocity, dt, state, ctx, params):
    """
    ================================================================================
    CONTROL PLUGIN CONTRACT: Gimbal Pan/Tilt Angular Rate Servo Loop
    ================================================================================
    INPUT PARAMETERS EXPLANATION:
    --------------------------------------------------------------------------------
    1. error (dict):
       - error["ex"] (float): Horizontal boresight tracking error in pixels.
                              Defined as: (target_x - camera_center_x).
                              Positive (+) means target is to the RIGHT of optical axis.
                              Negative (-) means target is to the LEFT of optical axis.
       - error["ey"] (float): Vertical boresight tracking error in pixels.
                              Defined as: (target_y - camera_center_y).
                              Positive (+) means target is BELOW optical axis.
                              Negative (-) means target is ABOVE optical axis.
       * Objective: Drive both ex and ey to 0.0 to keep the beacon on the detector.

    2. velocity (dict):
       - velocity["vx"] (float): Estimated target velocity along X in image plane (pixels/s).
       - velocity["vy"] (float): Estimated target velocity along Y in image plane (pixels/s).
       * Used for derivative/damping action and feedforward tracking of high-speed trajectories.

    3. dt (float):
       - Time step elapsed since the last control execution in seconds (nominal: ~0.0333 s at 30 Hz).
       * Crucial for discrete-time numerical integration (error * dt) and differentiation (de / dt).

    4. state (dict):
       - Persistent memory dictionary preserved across all simulation frames for this plugin.
       * Use state to store loop integrators, previous errors, and filter history between frames.
       * e.g., state["int_ex"], state["prev_ex"], state["initialized"].

    5. ctx (dict):
       - Real-time engine telemetry and sensor calibration context:
         - ctx["px_per_deg_x"] (float): Pixels per physical degree along azimuth (~160.0 px/deg).
         - ctx["px_per_deg_y"] (float): Pixels per physical degree along elevation (~160.0 px/deg).
         - ctx["pan_deg"]      (float): Current physical pan gimbal angle in degrees.
         - ctx["tilt_deg"]     (float): Current physical tilt gimbal angle in degrees.
         - ctx["max_pan_rate"] (float): Motor safety velocity limit for pan (deg/s).
         - ctx["max_tilt_rate"](float): Motor safety velocity limit for tilt (deg/s).
         - ctx["fsm_state"]    (str)  : Finite State Machine mode ("TRACK", "ACQUIRE", "LOST").

    6. params (dict):
       - User-tunable hyperparameters extracted via params.get("param_name", default_val).
       * NOTE: Any params.get() defined here automatically creates a live tuning slider in the GUI!
    ================================================================================
    """
    # ── [1. DEMO CODE: FETCH HYPERPARAMETERS] ─────────────────────────────────
    # Live sliders are auto-discovered from these calls:
    Pp = params.get("Pp", 4.602)            # Position proportional gain
    Ip = params.get("Ip", 0.0865)           # Position integral gain
    Dp = params.get("Dp", 12.29)            # Position derivative gain
    Pv = params.get("Pv", 3.238)            # Velocity loop proportional gain
    Iv = params.get("Iv", 0.000486)         # Velocity loop integral gain
    Dv = params.get("Dv", 14.34)            # Velocity loop derivative gain

    # Read sensor geometry and safe time step
    px_per_deg_x = ctx.get("px_per_deg_x", 160.0)
    px_per_deg_y = ctx.get("px_per_deg_y", 160.0)
    dt_c = max(float(dt), 1e-4)

    # ── [2. DEMO CODE: EXTRACT INPUTS] ───────────────────────────────────────
    ex = float(error.get("ex", 0.0))
    ey = float(error.get("ey", 0.0))
    vx_meas = float(velocity.get("vx", 0.0))
    vy_meas = float(velocity.get("vy", 0.0))

    # ── [3. DEMO CODE: CASCADED POSITION PID LOOP] ───────────────────────────
    # Integrate position error with anti-windup clamping [-60, +60] px*s
    state["int_ex"] = max(-60.0, min(60.0, state.get("int_ex", 0.0) + ex * dt_c))
    state["int_ey"] = max(-60.0, min(60.0, state.get("int_ey", 0.0) + ey * dt_c))

    # Position error derivative
    dex = (ex - state.get("prev_ex", ex)) / dt_c
    dey = (ey - state.get("prev_ey", ey)) / dt_c
    state["prev_ex"] = ex
    state["prev_ey"] = ey

    # Desired pixel velocity command
    v_cmd_x = Pp * ex + Ip * state["int_ex"] + Dp * dex
    v_cmd_y = Pp * ey + Ip * state["int_ey"] + Dp * dey

    # ── [4. DEMO CODE: CASCADED VELOCITY PID LOOP] ───────────────────────────
    e_vx = v_cmd_x - vx_meas
    e_vy = v_cmd_y - vy_meas

    # Integrate velocity error with anti-windup clamping [-100, +100]
    state["int_evx"] = max(-100.0, min(100.0, state.get("int_evx", 0.0) + e_vx * dt_c))
    state["int_evy"] = max(-100.0, min(100.0, state.get("int_evy", 0.0) + e_vy * dt_c))

    devx = (e_vx - state.get("prev_evx", e_vx)) / dt_c
    devy = (e_vy - state.get("prev_evy", e_vy)) / dt_c
    state["prev_evx"] = e_vx
    state["prev_evy"] = e_vy

    u_x = Pv * e_vx + Iv * state["int_evx"] + Dv * devx
    u_y = Pv * e_vy + Iv * state["int_evy"] + Dv * devy

    # Convert pixel-space acceleration/torque command to physical motor angular velocity (deg/s)
    pan_rate = u_x / px_per_deg_x
    tilt_rate = u_y / px_per_deg_y

    # ── [5. RETURN CONTRACT] ──────────────────────────────────────────────────
    # OUTPUT EXPLANATION:
    # --------------------------------------------------------------------------
    # Return a dictionary with exact keys "pan_rate" and "tilt_rate":
    #   - "pan_rate"  (float): Gimbal azimuth angular velocity command in deg/s.
    #                          Positive (+) commands gimbal to pan RIGHT.
    #                          Negative (-) commands gimbal to pan LEFT.
    #   - "tilt_rate" (float): Gimbal elevation angular velocity command in deg/s.
    #                          Positive (+) commands gimbal to tilt DOWN.
    #                          Negative (-) commands gimbal to tilt UP.
    # * What the engine does: Clamps rates to [+/- max_rate] and drives physical motors.
    # --------------------------------------------------------------------------
    return {
        "pan_rate": float(pan_rate),
        "tilt_rate": float(tilt_rate),
    }`
};

const PRESET_OPTIONS: Record<'tracking' | 'vision' | 'control', { id: string; name: string; code: string }[]> = {
  control: [
    {
      id: 'rl_opt1',
      name: 'RL-Tuned Cascaded PID (arXiv:2607.15910 a_opt1)',
      code: `def control(error, velocity, dt, state, ctx, params):
    # DDPG RL-Tuned Cascaded PID (Optimal Set 1, Table II)
    Pp = params.get("Pp", 4.602)
    Ip = params.get("Ip", 0.0865)
    Dp = params.get("Dp", 12.29)
    Pv = params.get("Pv", 3.238)
    Iv = params.get("Iv", 0.000486)
    Dv = params.get("Dv", 14.34)
    px_per_deg_x = ctx.get("px_per_deg_x", 160.0)
    px_per_deg_y = ctx.get("px_per_deg_y", 160.0)
    dt_c = max(float(dt), 1e-4)

    ex = float(error.get("ex", 0.0))
    ey = float(error.get("ey", 0.0))
    state["int_ex"] = max(-60.0, min(60.0, state.get("int_ex", 0.0) + ex * dt_c))
    dex = (ex - state.get("prev_ex", ex)) / dt_c
    state["prev_ex"] = ex
    state["int_ey"] = max(-60.0, min(60.0, state.get("int_ey", 0.0) + ey * dt_c))
    dey = (ey - state.get("prev_ey", ey)) / dt_c
    state["prev_ey"] = ey
    v_cmd_x = Pp * ex + Ip * state["int_ex"] + Dp * dex
    v_cmd_y = Pp * ey + Ip * state["int_ey"] + Dp * dey

    vx_meas = float(velocity.get("vx", 0.0))
    vy_meas = float(velocity.get("vy", 0.0))
    e_vx = v_cmd_x - vx_meas
    e_vy = v_cmd_y - vy_meas
    state["int_evx"] = max(-100.0, min(100.0, state.get("int_evx", 0.0) + e_vx * dt_c))
    devx = (e_vx - state.get("prev_evx", e_vx)) / dt_c
    state["prev_evx"] = e_vx
    state["int_evy"] = max(-100.0, min(100.0, state.get("int_evy", 0.0) + e_vy * dt_c))
    devy = (e_vy - state.get("prev_evy", e_vy)) / dt_c
    state["prev_evy"] = e_vy
    u_x = Pv * e_vx + Iv * state["int_evx"] + Dv * devx
    u_y = Pv * e_vy + Iv * state["int_evy"] + Dv * devy
    return {"pan_rate": u_x / px_per_deg_x, "tilt_rate": u_y / px_per_deg_y}`
    },
    {
      id: 'rl_opt2',
      name: 'RL-Tuned Cascaded PID (arXiv:2607.15910 a_opt2)',
      code: `def control(error, velocity, dt, state, ctx, params):
    # DDPG RL-Tuned Cascaded PID (Optimal Set 2, Table II)
    Pp = params.get("Pp", 4.676)
    Ip = params.get("Ip", 0.0851)
    Dp = params.get("Dp", 12.95)
    Pv = params.get("Pv", 3.119)
    Iv = params.get("Iv", 0.000478)
    Dv = params.get("Dv", 15.32)
    px_per_deg_x = ctx.get("px_per_deg_x", 160.0)
    px_per_deg_y = ctx.get("px_per_deg_y", 160.0)
    dt_c = max(float(dt), 1e-4)

    ex = float(error.get("ex", 0.0))
    ey = float(error.get("ey", 0.0))
    state["int_ex"] = max(-60.0, min(60.0, state.get("int_ex", 0.0) + ex * dt_c))
    dex = (ex - state.get("prev_ex", ex)) / dt_c
    state["prev_ex"] = ex
    state["int_ey"] = max(-60.0, min(60.0, state.get("int_ey", 0.0) + ey * dt_c))
    dey = (ey - state.get("prev_ey", ey)) / dt_c
    state["prev_ey"] = ey
    v_cmd_x = Pp * ex + Ip * state["int_ex"] + Dp * dex
    v_cmd_y = Pp * ey + Ip * state["int_ey"] + Dp * dey

    vx_meas = float(velocity.get("vx", 0.0))
    vy_meas = float(velocity.get("vy", 0.0))
    e_vx = v_cmd_x - vx_meas
    e_vy = v_cmd_y - vy_meas
    state["int_evx"] = max(-100.0, min(100.0, state.get("int_evx", 0.0) + e_vx * dt_c))
    devx = (e_vx - state.get("prev_evx", e_vx)) / dt_c
    state["prev_evx"] = e_vx
    state["int_evy"] = max(-100.0, min(100.0, state.get("int_evy", 0.0) + e_vy * dt_c))
    devy = (e_vy - state.get("prev_evy", e_vy)) / dt_c
    state["prev_evy"] = e_vy
    u_x = Pv * e_vx + Iv * state["int_evx"] + Dv * devx
    u_y = Pv * e_vy + Iv * state["int_evy"] + Dv * devy
    return {"pan_rate": u_x / px_per_deg_x, "tilt_rate": u_y / px_per_deg_y}`
    },
    {
      id: 'baseline_pid',
      name: 'Classical Ziegler-Nichols PID Baseline (a_baseline)',
      code: `def control(error, velocity, dt, state, ctx, params):
    # Classical Cascaded PID Baseline (Table III)
    Pp = params.get("Pp", 4.0)
    Ip = params.get("Ip", 0.07)
    Dp = params.get("Dp", 20.0)
    Pv = params.get("Pv", 3.0)
    Iv = params.get("Iv", 0.0004)
    Dv = params.get("Dv", 20.0)
    px_per_deg_x = ctx.get("px_per_deg_x", 160.0)
    px_per_deg_y = ctx.get("px_per_deg_y", 160.0)
    dt_c = max(float(dt), 1e-4)

    ex = float(error.get("ex", 0.0))
    ey = float(error.get("ey", 0.0))
    state["int_ex"] = max(-60.0, min(60.0, state.get("int_ex", 0.0) + ex * dt_c))
    dex = (ex - state.get("prev_ex", ex)) / dt_c
    state["prev_ex"] = ex
    state["int_ey"] = max(-60.0, min(60.0, state.get("int_ey", 0.0) + ey * dt_c))
    dey = (ey - state.get("prev_ey", ey)) / dt_c
    state["prev_ey"] = ey
    v_cmd_x = Pp * ex + Ip * state["int_ex"] + Dp * dex
    v_cmd_y = Pp * ey + Ip * state["int_ey"] + Dp * dey

    vx_meas = float(velocity.get("vx", 0.0))
    vy_meas = float(velocity.get("vy", 0.0))
    e_vx = v_cmd_x - vx_meas
    e_vy = v_cmd_y - vy_meas
    state["int_evx"] = max(-100.0, min(100.0, state.get("int_evx", 0.0) + e_vx * dt_c))
    devx = (e_vx - state.get("prev_evx", e_vx)) / dt_c
    state["prev_evx"] = e_vx
    state["int_evy"] = max(-100.0, min(100.0, state.get("int_evy", 0.0) + e_vy * dt_c))
    devy = (e_vy - state.get("prev_evy", e_vy)) / dt_c
    state["prev_evy"] = e_vy
    u_x = Pv * e_vx + Iv * state["int_evx"] + Dv * devx
    u_y = Pv * e_vy + Iv * state["int_evy"] + Dv * devy
    return {"pan_rate": u_x / px_per_deg_x, "tilt_rate": u_y / px_per_deg_y}`
    }
  ],
  tracking: [
    {
      id: 'cv_kalman',
      name: 'Kalman Filter Baseline (Constant Velocity CV)',
      code: `def track(measurement, dt, state, ctx, params):
    # Single Constant-Velocity (CV) Kalman Filter Baseline
    q = params.get("process_noise", 10.0)
    r = params.get("meas_noise", 2.0)
    cam_cx = ctx.get("cam_cx", 320.0)
    cam_cy = ctx.get("cam_cy", 240.0)
    import numpy as np
    if "x_hat" not in state:
        mx = float(measurement["x"]) if measurement else cam_cx
        my = float(measurement["y"]) if measurement else cam_cy
        state["x_hat"] = np.array([[mx], [my], [0.0], [0.0]], dtype=float)
        state["P"] = np.eye(4, dtype=float) * 50.0

    x_hat = state["x_hat"]
    P = state["P"]
    F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
    Q = np.eye(4, dtype=float) * q * dt
    x_hat = F @ x_hat
    P = F @ P @ F.T + Q
    if measurement is not None:
        H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        R = np.eye(2, dtype=float) * r
        z = np.array([[measurement["x"]], [measurement["y"]]], dtype=float)
        y = z - H @ x_hat
        S = H @ P @ H.T + R
        K = P @ H.T @ np.linalg.inv(S)
        x_hat = x_hat + K @ y
        P = (np.eye(4) - K @ H) @ P
    state["x_hat"] = x_hat
    state["P"] = P
    return {"x": float(x_hat[0, 0]), "y": float(x_hat[1, 0]), "vx": float(x_hat[2, 0]), "vy": float(x_hat[3, 0])}`
    },
    {
      id: 'alpha_beta',
      name: 'Alpha-Beta Filter Baseline',
      code: `def track(measurement, dt, state, ctx, params):
    alpha = params.get("alpha", 0.85)
    beta = params.get("beta", 0.005)
    cam_cx = ctx.get("cam_cx", 320.0)
    cam_cy = ctx.get("cam_cy", 240.0)
    if "x" not in state:
        mx = float(measurement["x"]) if measurement else cam_cx
        my = float(measurement["y"]) if measurement else cam_cy
        state["x"] = mx
        state["y"] = my
        state["vx"] = 0.0
        state["vy"] = 0.0
        return {"x": mx, "y": my, "vx": 0.0, "vy": 0.0}
    dt_c = max(float(dt), 1e-4)
    pred_x = state["x"] + state["vx"] * dt_c
    pred_y = state["y"] + state["vy"] * dt_c
    if measurement is not None:
        rx = float(measurement["x"]) - pred_x
        ry = float(measurement["y"]) - pred_y
        state["x"] = pred_x + alpha * rx
        state["y"] = pred_y + alpha * ry
        state["vx"] = state["vx"] + (beta / dt_c) * rx
        state["vy"] = state["vy"] + (beta / dt_c) * ry
    else:
        state["x"] = pred_x
        state["y"] = pred_y
    return {"x": state["x"], "y": state["y"], "vx": state["vx"], "vy": state["vy"]}`
    }
  ],
  vision: [
    {
      id: 'threshold_centroid',
      name: 'Sub-pixel Centroiding Baseline',
      code: `def detect(image, width, height, ctx, params):
    import numpy as np
    threshold = params.get("threshold", 180)
    mask = image >= threshold
    if not np.any(mask):
        return None
    y_coords, x_coords = np.where(mask)
    weights = image[y_coords, x_coords].astype(float)
    total_w = np.sum(weights)
    if total_w < 1e-5:
        return None
    x = float(np.sum(x_coords * weights) / total_w)
    y = float(np.sum(y_coords * weights) / total_w)
    return {"x": x, "y": y, "confidence": min(1.0, float(np.max(weights) / 255.0))}`
    }
  ]
};

interface ParamConfig {
  desc: string;
  min: number;
  max: number;
  step: number;
  precision: number;
}

const PARAM_META: Record<string, ParamConfig> = {
  // Cascaded Position & Velocity PID (arXiv:2607.15910)
  Pp: { desc: 'Position Loop Proportional Gain', min: 0, max: 15.0, step: 0.05, precision: 3 },
  Ip: { desc: 'Position Loop Integral Gain', min: 0, max: 0.40, step: 0.001, precision: 4 },
  Dp: { desc: 'Position Loop Derivative Gain', min: 0, max: 40.0, step: 0.1, precision: 2 },
  Pv: { desc: 'Velocity Loop Proportional Gain', min: 0, max: 12.0, step: 0.05, precision: 3 },
  Iv: { desc: 'Velocity Loop Integral Gain (Paper)', min: 0, max: 0.0020, step: 0.00001, precision: 6 },
  Dv: { desc: 'Velocity Loop Derivative Gain', min: 0, max: 40.0, step: 0.1, precision: 2 },

  // Tracking Filters
  alpha: { desc: 'Position Smoothing Gain (α)', min: 0, max: 1.0, step: 0.01, precision: 3 },
  beta: { desc: 'Velocity Smoothing Gain (β)', min: 0, max: 0.05, step: 0.0005, precision: 4 },
  process_noise: { desc: 'Process Noise Covariance (Q)', min: 0.1, max: 50.0, step: 0.1, precision: 2 },
  meas_noise: { desc: 'Measurement Noise Covariance (R)', min: 0.05, max: 20.0, step: 0.05, precision: 2 },
  q: { desc: 'Process Noise Covariance (Q)', min: 0.1, max: 50.0, step: 0.1, precision: 2 },
  r: { desc: 'Measurement Noise Covariance (R)', min: 0.05, max: 20.0, step: 0.05, precision: 2 },

  // Vision Centroiding
  threshold: { desc: 'Intensity Cutoff Threshold (0-255)', min: 0, max: 255, step: 1, precision: 0 },
  min_area: { desc: 'Minimum Centroid Area (px)', min: 0, max: 100, step: 1, precision: 0 },
  max_area: { desc: 'Maximum Centroid Area (px)', min: 50, max: 5000, step: 10, precision: 0 },
  sigma: { desc: 'Gaussian Smoothing Radius', min: 0.1, max: 10.0, step: 0.1, precision: 2 },
};

function getParamConfig(key: string, defaultVal: number, currentVal: number): ParamConfig {
  if (PARAM_META[key]) {
    const m = PARAM_META[key];
    const min = Math.min(m.min, currentVal < 0 ? currentVal * 1.2 : m.min);
    const max = Math.max(m.max, currentVal > m.max ? currentVal * 1.25 : m.max);
    return { desc: m.desc, min, max, step: m.step, precision: m.precision };
  }

  const d = Math.abs(defaultVal);
  let min = 0;
  let max = 10.0;
  let step = 0.01;
  let precision = 3;

  if (d === 0) {
    min = 0; max = 10.0; step = 0.1; precision = 2;
  } else if (d < 0.002) {
    min = 0; max = Math.max(0.002, d * 4); step = 0.00001; precision = 6;
  } else if (d < 0.05) {
    min = 0; max = Math.max(0.1, d * 3); step = 0.0005; precision = 4;
  } else if (d < 1.0) {
    min = 0; max = Math.max(1.0, d * 2.5); step = 0.005; precision = 3;
  } else if (d <= 20.0) {
    min = 0; max = Math.max(20.0, d * 2.5); step = 0.05; precision = 2;
  } else if (d <= 255.0) {
    min = 0; max = Math.max(255.0, d * 1.5); step = 1; precision = 0;
  } else {
    min = 0; max = d * 2; step = Math.pow(10, Math.floor(Math.log10(d)) - 1); precision = 1;
  }

  if (currentVal > max) max = currentVal * 1.25;
  if (currentVal < min) min = currentVal < 0 ? currentVal * 1.2 : 0;

  return {
    desc: `Discovered Parameter (${key})`,
    min,
    max,
    step,
    precision
  };
}

type PluginSlot = 'tracking' | 'vision' | 'control';

function PluginDrawer() {
  const [slot, setSlot] = useState<PluginSlot>('control');
  const [strategy, setStrategy] = useState<'default' | 'preset' | 'custom'>('custom');
  const [presetIndex, setPresetIndex] = useState(0);
  const [code, setCode] = useState(DEFAULT_CODE['control']);
  const [params, setParams] = useState<Record<string, number>>({});
  const [paramDefaults, setParamDefaults] = useState<Record<string, number>>({});
  const [status, setStatus] = useState<'idle' | 'applying' | 'ok' | 'error'>('idle');
  const [msg, setMsg] = useState('');
  const [reportModal, setReportModal] = useState<any | null>(null);
  const [htmlReport, setHtmlReport] = useState<string | null>(null);
  
  useEffect(() => {
    const regex = /params\.get\(\s*["'](\w+)["']\s*,\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*\)/g;
    let match;
    const newDefaults: Record<string, number> = {};
    while ((match = regex.exec(code)) !== null) {
      newDefaults[match[1]] = parseFloat(match[2]);
    }
    setParamDefaults(newDefaults);
    setParams((prev: Record<string, number>) => {
      const next: Record<string, number> = {};
      for (const [k, defVal] of Object.entries(newDefaults)) {
        next[k] = (k in prev && Number.isFinite(prev[k])) ? prev[k] : defVal;
      }
      return next;
    });
  }, [code]);

  const apply = async () => {
    setStatus('applying');
    try {
      if (strategy === 'default') {
        const res = await fetch('/api/plugins/reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slot })
        });
        if (res.ok) {
          setStatus('ok'); setMsg('Reset to NETRA Default (IMM Kalman Filter + Cascaded PID)!');
        } else {
          setStatus('error'); setMsg('Failed to reset');
        }
      } else {
        const activePreset = PRESET_OPTIONS[slot]?.[presetIndex];
        const activeCode = strategy === 'preset' ? (activePreset?.code || DEFAULT_CODE[slot]) : code;
        const activeLabel = strategy === 'preset' ? (activePreset?.name || 'Selected Preset') : 'Custom Algorithm Plugin';

        const res = await fetch('/api/plugins/apply_code', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slot, code: activeCode, params, label: activeLabel })
        });
        
        let json;
        try {
          json = await res.json();
        } catch (e) {
          throw new Error('Failed to parse server response. Is the Python backend running?');
        }

        if (res.ok) {
          setStatus('ok'); setMsg(`Applied seamlessly: ${activeLabel}`);
        } else {
          setStatus('error'); setMsg(json.error || 'Failed to apply');
        }
      }
    } catch (e) {
      setStatus('error'); setMsg((e as Error).message || String(e));
    }
    setTimeout(() => setStatus('idle'), 4000);
  };

  const openComparativeReport = async () => {
    try {
      setStatus('applying');
      const res = await fetch('/api/plugins/report');
      const data = await res.json();
      setStatus('idle');
      if (data.report) {
        setReportModal(data.report);
        setHtmlReport(data.html || null);
      } else {
        alert('No report data returned from server.');
      }
    } catch (e) {
      setStatus('idle');
      alert('Failed to generate Comparative Report. Ensure backend is running.');
    }
  };

  const downloadJson = () => {
    if (!reportModal) return;
    const blob = new Blob([JSON.stringify(reportModal, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `comparative_report_${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const openPrintHtml = () => {
    if (!htmlReport) return;
    const blob = new Blob([htmlReport], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  };

  return (
    <>
      <Section title="Plugin Playground">
        <div style={{ paddingBottom: 10 }}>

          <label className="dim" style={{ display: 'block', marginBottom: 4 }}>1. Pipeline Slot</label>
          <select value={slot} onChange={e => {
             const s = e.target.value as 'tracking'|'vision'|'control';
             setSlot(s);
             setPresetIndex(0);
             setParams({});
             setCode(DEFAULT_CODE[s]);
          }} style={{ width: '100%', marginBottom: 12, background: '#1a1d24', color: '#fff', border: '1px solid #333', padding: 5, borderRadius: 4 }}>
            <option value="control">Control (Cascaded PID Servo Loop)</option>
            <option value="tracking">Tracking (State Estimation)</option>
            <option value="vision">Vision (Centroid Detection)</option>
          </select>

          <label className="dim" style={{ display: 'block', marginBottom: 4 }}>2. Strategy Selection</label>
          <select value={strategy} onChange={e => {
             const st = e.target.value as 'default'|'preset'|'custom';
             setStrategy(st);
             setParams({});
             if (st === 'preset') {
               const p = PRESET_OPTIONS[slot]?.[0];
               if (p) setCode(p.code);
             } else if (st === 'custom' || st === 'default') {
               setCode(DEFAULT_CODE[slot]);
             }
          }} style={{ width: '100%', marginBottom: 12, background: '#1a1d24', color: '#fff', border: '1px solid #333', padding: 5, borderRadius: 4 }}>
            <option value="default">NETRA Default (IMM Kalman Filter + Cascaded PID)</option>
            <option value="preset">Preset Baseline Library (RL-PID / Kalman / PSF)</option>
            <option value="custom">Custom Algorithm Function Injection</option>
          </select>

          {strategy === 'preset' && (
            <div style={{ marginBottom: 12 }}>
              <label className="dim" style={{ display: 'block', marginBottom: 4 }}>Select Baseline / Preset Technique</label>
              <select 
                value={presetIndex} 
                onChange={e => {
                  const idx = parseInt(e.target.value, 10);
                  setPresetIndex(idx);
                  const p = PRESET_OPTIONS[slot]?.[idx];
                  if (p) {
                    setParams({});
                    setCode(p.code);
                  }
                }}
                style={{ width: '100%', background: '#1a1d24', color: '#fff', border: '1px solid #333', padding: 5, borderRadius: 4 }}
              >
                {PRESET_OPTIONS[slot]?.map((p: { id: string; name: string; code: string }, i: number) => (
                  <option key={p.id} value={i}>{p.name}</option>
                ))}
              </select>
            </div>
          )}
          
          <div style={{ marginTop: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <label className="dim" style={{ margin: 0, fontWeight: 600 }}>
                {strategy === 'custom' 
                  ? '3. Write Python Function (Live PAT Code)' 
                  : strategy === 'preset'
                  ? '3. Preset Python Implementation'
                  : '3. NETRA Default Contract (Reference Architecture)'}
              </label>
              <button 
                type="button" 
                className="ghost" 
                onClick={() => {
                  setCode(DEFAULT_CODE[slot]);
                  setParams({});
                }}
                style={{ fontSize: 10, padding: '2px 8px', color: '#00f5d4', border: '1px solid rgba(0,245,212,0.3)', borderRadius: 3, cursor: 'pointer' }}
                title="Reload clean default function contract with all input/output explanations"
              >
                ↺ Reset to Default Contract
              </button>
            </div>

            {strategy === 'default' && (
              <div style={{
                padding: '8px 10px',
                marginBottom: 8,
                background: 'rgba(0, 245, 212, 0.05)',
                border: '1px solid rgba(0, 245, 212, 0.25)',
                borderRadius: 4,
                fontSize: 11,
                color: '#94a3b8',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 8
              }}>
                <span>⚡ Active default algorithm contract. Review specifications or edit:</span>
                <button 
                  type="button" 
                  onClick={() => setStrategy('custom')}
                  style={{ background: '#0284c7', border: 'none', color: '#fff', fontSize: 10, padding: '3px 10px', borderRadius: 3, cursor: 'pointer', fontWeight: 600, whiteSpace: 'nowrap' }}
                >
                  ✏️ Edit as Custom Plugin
                </button>
              </div>
            )}

            <textarea 
               value={code} 
               onChange={e => {
                 setCode(e.target.value);
                 if (strategy === 'default') {
                   setStrategy('custom');
                 }
               }}
               spellCheck={false}
               style={{ width: '100%', height: 260, background: '#0d1117', color: '#c9d1d9', fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace", fontSize: 11, lineHeight: 1.45, border: '1px solid #30363d', padding: 8, borderRadius: 4 }}
            />

            {Object.keys(params).length > 0 && (
              <div style={{ marginTop: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <label className="dim" style={{ margin: 0, fontWeight: 600 }}>4. Tune Coefficients (Auto-Discovered)</label>
                  <button 
                    type="button" 
                    className="ghost" 
                    onClick={() => setParams({ ...paramDefaults })}
                    style={{ fontSize: 10, padding: '2px 8px', color: '#00f5d4', border: '1px solid rgba(0,245,212,0.3)', borderRadius: 3, cursor: 'pointer' }}
                    title="Reset all coefficients to active code defaults"
                  >
                    ↺ Reset All
                  </button>
                </div>
                {Object.keys(params).map(k => {
                  const currentVal = params[k];
                  const defaultVal = paramDefaults[k] ?? currentVal;
                  const cfg = getParamConfig(k, defaultVal, currentVal);
                  const rangeSpan = cfg.max - cfg.min;
                  const percent = rangeSpan > 0 ? Math.min(100, Math.max(0, ((currentVal - cfg.min) / rangeSpan) * 100)) : 0;
                  const isModified = Math.abs(currentVal - defaultVal) > 1e-7;

                  return (
                    <div key={k} style={{
                      marginBottom: 10,
                      padding: '8px 10px',
                      background: 'rgba(255, 255, 255, 0.02)',
                      border: '1px solid rgba(255, 255, 255, 0.07)',
                      borderRadius: 6
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                          <span style={{ color: '#00f5d4', fontFamily: 'monospace', fontWeight: 'bold', fontSize: 12 }}>{k}</span>
                          <span style={{ color: '#8b949e', fontSize: 10 }}>{cfg.desc}</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <input 
                            type="number" 
                            step="any"
                            value={currentVal}
                            onChange={e => {
                              const val = parseFloat(e.target.value);
                              if (!isNaN(val)) {
                                setParams((prev: Record<string, number>) => ({ ...prev, [k]: val }));
                              }
                            }}
                            style={{
                              width: 84,
                              background: '#0d1117',
                              color: isModified ? '#f5a623' : '#00f5d4',
                              fontFamily: 'monospace',
                              fontSize: 11,
                              padding: '2px 6px',
                              border: isModified ? '1px solid #f5a623' : '1px solid #30363d',
                              borderRadius: 4,
                              textAlign: 'right'
                            }}
                          />
                          <button 
                            type="button" 
                            title={`Reset ${k} to default (${defaultVal})`}
                            disabled={!isModified}
                            onClick={() => setParams((prev: Record<string, number>) => ({ ...prev, [k]: defaultVal }))}
                            style={{
                              background: 'transparent',
                              border: 'none',
                              color: isModified ? '#f5a623' : '#444',
                              cursor: isModified ? 'pointer' : 'default',
                              fontSize: 13,
                              padding: '0 2px',
                              lineHeight: 1
                            }}
                          >
                            ↺
                          </button>
                        </div>
                      </div>
                      <input 
                        type="range" 
                        min={cfg.min} 
                        max={cfg.max} 
                        step={cfg.step} 
                        value={currentVal} 
                        onChange={e => setParams((prev: Record<string, number>) => ({ ...prev, [k]: parseFloat(e.target.value) }))} 
                        style={{ width: '100%', ['--p' as string]: `${percent}%` }} 
                      />
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: '#6e7681', fontFamily: 'monospace', marginTop: 2 }}>
                        <span>{cfg.min.toFixed(cfg.precision > 2 ? 2 : cfg.precision)}</span>
                        <span style={{ color: '#8b949e' }}>nominal: {defaultVal}</span>
                        <span>{cfg.max.toFixed(cfg.precision > 2 ? 2 : cfg.precision)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <button 
             className="btn primary" 
             onClick={apply} 
             disabled={status === 'applying'} 
             style={{ width: '100%', marginTop: 12, background: 'linear-gradient(90deg,#f5a623,#e8541e)', border: 'none', color: 'white', fontWeight: 'bold' }}
          >
            <Icon name="code" size={14} />
            {status === 'applying' ? 'APPLYING...' : strategy === 'default' ? 'RESTORE NETRA DEFAULT' : strategy === 'preset' ? 'APPLY SELECTED PRESET' : 'APPLY CUSTOM PLUGIN'}
          </button>

          {status === 'ok' && <p style={{ color: '#00f5d4', fontSize: 11, marginTop: 8 }}>✅ {msg}</p>}
          {status === 'error' && <p style={{ color: '#ff4d6d', fontSize: 11, marginTop: 8 }}>❌ {msg}</p>}
          
          <div style={{ marginTop: 18, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <button 
               className="outline" 
               onClick={openComparativeReport} 
               disabled={status === 'applying'}
               style={{ width: '100%', fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
            >
              <Icon name="report" size={14} /> COMPARATIVE REPORT (NETRA vs CUSTOM)
            </button>
            <button 
               className="ghost" 
               onClick={() => window.open('/api/plugins/report?format=html', '_blank')}
               style={{ width: '100%', fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, color: 'var(--amber)' }}
               title="Open full standalone Comparative Report in a new browser tab"
            >
              🌐 OPEN STANDALONE HTML REPORT (NEW TAB)
            </button>
          </div>
        </div>
      </Section>

      {/* Comparative Report Modal - Rendered via Portal to body to break out of drawer clipping */}
      {reportModal && typeof document !== 'undefined' && createPortal(
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(5, 10, 18, 0.85)',
          backdropFilter: 'blur(8px)',
          WebkitBackdropFilter: 'blur(8px)',
          zIndex: 999999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
        }}>
          <div style={{
            background: '#ffffff',
            color: '#152231',
            borderRadius: 8,
            maxWidth: 1240,
            width: 'min(1180px, 94vw)',
            maxHeight: '90vh',
            overflowY: 'auto',
            padding: '24px 32px',
            boxShadow: '0 25px 60px rgba(0,0,0,0.6)',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '3px solid #c62828', paddingBottom: 12, marginBottom: 16 }}>
              <div>
                <h2 style={{ margin: '0 0 4px', fontSize: 22, color: '#111827', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  COMPARATIVE REPORT
                </h2>
                <p style={{ margin: 0, fontSize: 12.5, color: '#4b5563' }}>
                  Side-by-side performance evaluation: <b>{reportModal.custom_label}</b> vs. <b>{reportModal.baseline_label}</b>
                </p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <button 
                  onClick={() => window.open('/api/plugins/report?format=html', '_blank')}
                  style={{ background: '#0284c7', color: '#fff', border: 'none', borderRadius: 4, padding: '6px 12px', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}
                  title="Open standalone HTML report in a new tab"
                >
                  🌐 OPEN IN NEW TAB
                </button>
                <button 
                  onClick={() => setReportModal(null)}
                  style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer', color: '#6b7280', lineHeight: 1 }}
                >
                  ✕
                </button>
              </div>
            </div>

            <div style={{ background: '#f0f9ff', borderLeft: '4px solid #0284c7', padding: '12px 16px', borderRadius: 4, marginBottom: 18, fontSize: 13, fontWeight: 500, color: '#0369a1' }}>
              {reportModal.verdict}
            </div>

            <h3 style={{ fontSize: 14, margin: '14px 0 10px', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#374151' }}>
              PERFORMANCE SUMMARY COMPARISON
            </h3>

            <div style={{ overflowX: 'auto', border: '1px solid #e5e7eb', borderRadius: 6, marginBottom: 20 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, background: '#fff', minWidth: 800 }}>
                <thead>
                  <tr style={{ background: '#f3f4f6', textAlign: 'left', borderBottom: '2px solid #e5e7eb' }}>
                    <th style={{ padding: '10px 14px', color: '#374151', minWidth: 180 }}>Metric</th>
                    <th style={{ padding: '10px 14px', color: '#374151', minWidth: 160 }}>{reportModal.baseline_label}</th>
                    <th style={{ padding: '10px 14px', color: '#0284c7', minWidth: 160 }}>{reportModal.custom_label}</th>
                    <th style={{ padding: '10px 14px', color: '#374151', minWidth: 140 }}>Difference (Δ)</th>
                    <th style={{ padding: '10px 14px', color: '#374151', minWidth: 120 }}>PS169 limit</th>
                    <th style={{ padding: '10px 14px', color: '#374151', minWidth: 90 }}>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {reportModal.rows?.map((r: any) => (
                    <tr key={r.key} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '8px 14px', fontWeight: 600, color: '#1f2937' }}>{r.label}</td>
                      <td style={{ padding: '8px 14px', fontFamily: 'monospace' }}>
                        {r.baseline !== null ? `${r.baseline} ${r.unit}`.trim() : '—'}
                      </td>
                      <td style={{ padding: '8px 14px', fontFamily: 'monospace', fontWeight: 600, color: '#0284c7' }}>
                        {r.custom !== null ? `${r.custom} ${r.unit}`.trim() : '—'}
                      </td>
                      <td style={{ 
                        padding: '8px 14px', 
                        fontFamily: 'monospace',
                        color: (r.delta || 0) < 0 && ['rmse', 'mae', 'max_err', 'p95', 'acquisition_s', 'loss_pct'].includes(r.key) ? '#16a34a' :
                               (r.delta || 0) > 0 && ['lock_pct', 'aqs', 'fps'].includes(r.key) ? '#16a34a' :
                               (r.delta || 0) > 0 && ['rmse', 'mae', 'max_err', 'loss_pct'].includes(r.key) ? '#dc2626' : '#4b5563',
                        fontWeight: 600
                      }}>
                        {r.delta_str}
                      </td>
                      <td style={{ padding: '8px 14px', color: '#6b7280' }}>{r.limit || ''}</td>
                      <td style={{ padding: '8px 14px' }}>
                        {r.pass === true && (
                          <span style={{ background: '#dcfce7', color: '#15803d', padding: '2px 8px', borderRadius: 10, fontSize: 10, fontWeight: 700 }}>
                            PASS
                          </span>
                        )}
                        {r.pass === false && (
                          <span style={{ background: '#fee2e2', color: '#b91c1c', padding: '2px 8px', borderRadius: 10, fontSize: 10, fontWeight: 700 }}>
                            FAIL
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', alignItems: 'center' }}>
              <button 
                onClick={downloadJson}
                style={{ padding: '8px 16px', borderRadius: 4, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
              >
                📥 DOWNLOAD JSON
              </button>
              <button 
                onClick={openPrintHtml}
                style={{ padding: '8px 16px', borderRadius: 4, border: 'none', background: '#0284c7', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
              >
                🖨️ OPEN STANDALONE REPORT (HTML)
              </button>
              <button 
                onClick={() => setReportModal(null)}
                style={{ padding: '8px 16px', borderRadius: 4, border: '1px solid #d1d5db', background: '#f3f4f6', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
              >
                CLOSE
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}


