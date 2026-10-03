/**
 * Tool rail + contextual drawers (progressive disclosure: every advanced parameter
 * lives here, hidden until needed).
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { DrawerId, recorder, useApp } from '../state/store';
import { SCENARIO_PRESETS, presetConfig } from '../core/presets';
import { buildReport } from '../core/analysis/report';
import { saveReport } from '../state/store';
import { SimConfig, TrajectoryKind } from '../core/config';
import { isRecording } from '../core/telemetry/recorder';
import type { BatchMessage, BatchRunResult } from '../engine/batch.worker';
import { Icon, Section, Seg, Slider, Toggle, fmt } from './ui';

const TOOLS: { id: Exclude<DrawerId, null>; icon: string; label: string }[] = [
  { id: 'scenario', icon: 'scenario', label: 'Test Cases' },
  { id: 'target', icon: 'target', label: 'Kinematics' },
  { id: 'disturbance', icon: 'disturbance', label: 'Noise Injection' },
  { id: 'tracking', icon: 'tracking', label: 'Detection, Kalman & Servo Loop' },
  { id: 'optics', icon: 'optics', label: 'Optical Sensor & Link Budget' },
  { id: 'experiment', icon: 'experiment', label: 'Analysis' },
];

export function ToolRail() {
  const drawer = useApp((s) => s.drawer);
  const setDrawer = useApp((s) => s.setDrawer);
  const set = useApp((s) => s.set);
  return (
    <nav className="rail glass" aria-label="Tools">
      {TOOLS.map((t) => (
        <button key={t.id} className={drawer === t.id ? 'on' : ''} onClick={() => setDrawer(t.id)} aria-label={t.label}>
          <Icon name={t.icon} />
          <span className="tip">{t.label}</span>
        </button>
      ))}
      <div className="sep" />
      <button onClick={() => set({ videoOpen: true })} aria-label="Video benchmark">
        <Icon name="film" />
        <span className="tip">Video benchmark — analyse an MP4 (camera bypass, PS Benchmark-2) · V</span>
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
      <Section title="Simulation Clock & Speed">
        <div className="row compact-row">
          <span className="muted" style={{ fontSize: 11.5 }}>
            Noise seed
          </span>
          <input
            type="number"
            value={cfg.seed}
            style={{ width: 75, height: 24, fontSize: 11 }}
            onChange={(e) => replace({ ...cfg, seed: parseInt(e.target.value || '0', 10) })}
          />
          <button className="btn sm" style={{ height: 24, padding: '0 8px', fontSize: 11 }} onClick={() => replace({ ...cfg, seed: cfg.seed + 1 })}>
            Shuffle seed
          </button>
        </div>
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

function OpticsDrawer() {
  const { cfg, patch } = useCfg();
  const cam = cfg.camera;
  return (
    <div className="section">
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
    </div>
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
      if (e.data.type === 'progress') setResults((r) => [...r, e.data.type === 'progress' ? e.data.result : r[0]]);
      else setBusy(false);
    };
    w.postMessage({ config: cfg, runs, durationS: dur, seed0: cfg.seed * 1000 });
  };
  const summary = useMemo(() => {
    if (!results.length) return null;
    const acq = results.map((r) => r.metrics.acquisitionS).filter((x): x is number => x !== null);
    const rms = results.map((r) => r.metrics.errRmsPx).filter((x): x is number => x !== null);
    const pass = results.filter((r) => r.metrics.acceptance.acquisition && r.metrics.acceptance.error && r.metrics.acceptance.loss !== false).length;
    return {
      acqMean: acq.length ? acq.reduce((a, b) => a + b, 0) / acq.length : null,
      acqMax: acq.length ? Math.max(...acq) : null,
      rmsMean: rms.length ? rms.reduce((a, b) => a + b, 0) / rms.length : null,
      locked: acq.length,
      pass,
    };
  }, [results]);
  const exportCsv = () => {
    const head = 'seed,final_state,acquisition_s,err_rms_px,err_max_px,loss_pct,reacq_max_s,centroid_rms_px,fps_capacity';
    const rows = results.map((r) =>
      [r.seed, r.finalState, r.metrics.acquisitionS ?? '', r.metrics.errRmsPx ?? '', r.metrics.errMaxPx ?? '', r.metrics.lossPct ?? '', r.metrics.reacqMaxS ?? '', r.metrics.centroidRmsPx ?? '', r.metrics.fps.toFixed(0)].join(','),
    );
    const blob = new Blob([[head, ...rows].join('\n')], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `netra-batch-${cfg.scenarioId}.csv`;
    a.click();
  };
  return (
    <Section title="Monte Carlo Batch Trials" right={<span className="dim">headless worker</span>}>
      <Slider label="Runs" value={runs} min={2} max={50} step={1} digits={0} onChange={setRuns} />
      <Slider label="Duration per run" value={dur} min={5} max={60} step={1} digits={0} unit=" s" onChange={setDur} />
      <div className="row">
        <button className="btn sm primary" onClick={start} disabled={busy}>
          {busy ? `Running ${results.length}/${runs}…` : 'Run batch'}
        </button>
        <button className="btn sm" onClick={exportCsv} disabled={!results.length}>
          <Icon name="download" size={14} /> CSV
        </button>
        <button
          className="btn sm"
          disabled={!results.length || busy}
          onClick={() => saveReport(buildReport({ kind: 'batch', source: 'Browser engine (batch worker)', config: cfg, batch: results }), 'html', `netra-batch-report-${cfg.scenarioId}`)}
        >
          <Icon name="report" size={14} /> Report
        </button>
      </div>
      {summary && (
        <p className="note">
          Locked <b>{summary.locked}/{results.length}</b> · passing acquisition+error+loss <b>{summary.pass}/{results.length}</b> · acquisition mean <b>{fmt(summary.acqMean, 2, ' s')}</b> (max {fmt(summary.acqMax, 2, ' s')}) · RMS error mean <b>{fmt(summary.rmsMean, 2, ' px')}</b>
        </p>
      )}
      {results.length > 0 && (
        <table className="batch-table">
          <thead>
            <tr>
              <th>seed</th>
              <th>acq s</th>
              <th>rms px</th>
              <th>loss %</th>
              <th>re-acq</th>
              <th>end</th>
            </tr>
          </thead>
          <tbody>
            {results.slice(-12).map((r) => (
              <tr key={r.seed}>
                <td>{r.seed}</td>
                <td>{fmt(r.metrics.acquisitionS, 2)}</td>
                <td>{fmt(r.metrics.errRmsPx, 2)}</td>
                <td>{fmt(r.metrics.lossPct, 1)}</td>
                <td>{fmt(r.metrics.reacqMaxS, 2)}</td>
                <td>{r.finalState.slice(0, 4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  );
}

function ReportPanel() {
  const autoReport = useApp((s) => s.autoReport);
  const { downloadReport, set } = useApp.getState();
  const rec = useApp((s) => s.recording);
  return (
    <Section title="Mission Performance Analysis" right={<span className="tag ai">auto</span>}>
      <p className="note" style={{ marginTop: 0 }}>
        Duration, FPS, acquisition time, average / max tracking error, lock retention, loss, re-acquisition, processing time, PS169 pass/fail, configuration and the state log.
      </p>
      <div className="row">
        <button className="btn sm primary" onClick={() => downloadReport('live', 'html')}>
          <Icon name="report" size={14} /> Report (live run)
        </button>
        <button className="btn sm" onClick={() => downloadReport('live', 'md')}>
          Markdown
        </button>
        <button className="btn sm" onClick={() => downloadReport('live', 'json')}>
          JSON
        </button>
      </div>
      <div className="row" style={{ marginTop: 6 }}>
        <button className="btn sm" onClick={() => downloadReport('recording', 'html')} disabled={!rec.frames}>
          <Icon name="report" size={14} /> Report (recording)
        </button>
      </div>
      <Toggle
        label="Save a report automatically when a recording stops"
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
  return (
    <>
      <Section title="Execution Backend & Connectivity">
        <Seg
          value={kind === 'replay' ? 'local' : kind}
          options={[
            { v: 'local', label: 'Local (browser)' },
            { v: 'remote', label: 'FastAPI server' },
          ]}
          onChange={(v) => connect(v, v === 'remote' ? { url } : undefined)}
        />
        <div className="row" style={{ marginTop: 8 }}>
          <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} style={{ flex: 1 }} />
          <button className="btn sm" onClick={() => connect('remote', { url })}>
            Connect
          </button>
        </div>
        <p className="note">
          Status: <b>{status}</b> · source <b>{kind}</b>
          {err && (
            <>
              <br />
              <span style={{ color: 'var(--lost)' }}>{err}</span>
            </>
          )}
        </p>
      </Section>
      <Section title="Live Session & Recording">
        <div className="row">
          <button className="btn sm" onClick={() => send({ type: running ? 'pause' : 'start' })}>
            {running ? 'Stop' : 'Start'}
          </button>
          <button className="btn sm" onClick={() => send({ type: 'reset' })} disabled={kind === 'replay'}>
            Reset
          </button>
          <button className={`btn sm rec ${rec.active ? 'on' : ''}`} onClick={() => (rec.active ? stopRecording() : startRecording())}>
            <span className="led" />
            {rec.active ? 'Stop recording' : 'Record'}
          </button>
        </div>
        <p className="note">
          Recorded: <b>{rec.frames}</b> frames ({(rec.frames / 30).toFixed(1)} s). Every snapshot is kept (no images) for CSV / JSON export and replay.
        </p>
        <div className="row">
          <button className="btn sm" onClick={exportCsv}>
            <Icon name="download" size={14} /> CSV
          </button>
          <button className="btn sm" onClick={exportJson}>
            <Icon name="download" size={14} /> JSON
          </button>
          <button
            className="btn sm"
            onClick={() => {
              if (!recorder.frames.length) return notify('Nothing recorded yet');
              connect('replay', { recording: recorder.toRecording('In-memory recording', useApp.getState().config, kind) });
            }}
          >
            <Icon name="play" size={14} /> Replay
          </button>
          <button className="btn sm" onClick={() => file.current?.click()}>
            <Icon name="upload" size={14} /> Load JSON
          </button>
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
      <Section title="Flight State Transition Log" right={<span className="dim">{events.length}</span>}>
        <div style={{ maxHeight: 220, overflowY: 'auto', fontSize: 11.5 }}>
          {[...events].reverse().slice(0, 80).map((e, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, padding: '3px 0', borderBottom: '1px solid var(--hair)' }}>
              <span className="mono dim" style={{ flex: 'none', width: 48 }}>
                {e.t.toFixed(2)}
              </span>
              <span className="muted">
                {e.to && <b style={{ color: 'var(--text)' }}>{e.to} </b>}
                {e.message}
              </span>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}

const TITLES: Record<Exclude<DrawerId, null>, string> = {
  scenario: 'Test Cases',
  target: 'Kinematics',
  disturbance: 'Noise Injection',
  tracking: 'Acquisition & Tracking',
  optics: 'Optical Payload & Link',
  experiment: 'Analysis',
};

export function RightNavbar() {
  const activeDrawer = useApp((s) => s.drawer) || 'scenario';
  const setDrawer = useApp((s) => s.setDrawer);
  const set = useApp((s) => s.set);

  return (
    <div className="right-navbar" aria-label="Controls & Navigation">
      {/* Embedded Drawer Content Pane */}
      <aside className="drawer-panel glass">
        <div className="drawer-head">
          <h3>{TITLES[activeDrawer] || 'Scenario'}</h3>
        </div>
        <div className="drawer-body">
          {activeDrawer === 'scenario' && <ScenarioDrawer />}
          {activeDrawer === 'target' && <TargetDrawer />}
          {activeDrawer === 'disturbance' && <DisturbanceDrawer />}
          {activeDrawer === 'tracking' && <TrackingDrawer />}
          {activeDrawer === 'optics' && <OpticsDrawer />}
          {activeDrawer === 'experiment' && <ExperimentDrawer />}
        </div>
      </aside>

      {/* Embedded Tool Rail Icon Strip */}
      <nav className="rail-strip glass" aria-label="Tools">
        {TOOLS.map((t) => (
          <button key={t.id} className={activeDrawer === t.id ? 'on' : ''} onClick={() => setDrawer(t.id)} aria-label={t.label}>
            <Icon name={t.icon} />
            <span className="tip">{t.label}</span>
          </button>
        ))}
        <div className="sep" />
        <button onClick={() => set({ videoOpen: true })} aria-label="Video benchmark">
          <Icon name="film" />
          <span className="tip">Video benchmark · V</span>
        </button>
      </nav>
    </div>
  );
}

export function Drawer() {
  return null;
}


