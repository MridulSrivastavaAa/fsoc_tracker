/**
 * Tool rail + contextual drawers (progressive disclosure: every advanced parameter
 * lives here, hidden until needed).
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { DrawerId, recorder, useApp } from '../state/store';
import { SCENARIO_PRESETS, presetConfig } from '../core/presets';
import { DETECTION_PROVIDERS } from '../core/detection/registry';
import { VERIFIER } from '../core/detection/verifier';
import { buildReport } from '../core/analysis/report';
import { saveReport } from '../state/store';
import { intrinsics, SimConfig, TrajectoryKind } from '../core/config';
import { acquisitionProbability } from '../core/analysis/link';
import { isRecording } from '../core/telemetry/recorder';
import type { BatchMessage, BatchRunResult } from '../engine/batch.worker';
import { Icon, Section, Seg, Slider, Toggle, fmt } from './ui';
import { ThemeList } from './Theme';

const TOOLS: { id: Exclude<DrawerId, null>; icon: string; label: string }[] = [
  { id: 'scenario', icon: 'scenario', label: 'Mission Profile & Orbital Geometry' },
  { id: 'target', icon: 'target', label: 'Target Kinematics & Beacon' },
  { id: 'disturbance', icon: 'disturbance', label: 'Atmosphere, Noise & Channel Dynamics' },
  { id: 'tracking', icon: 'tracking', label: 'Detection, Kalman & Servo Loop' },
  { id: 'optics', icon: 'optics', label: 'Sensor Calibration & Link Budget' },
  { id: 'experiment', icon: 'experiment', label: 'Telemetry, Batch & Analysis' },
  { id: 'plugin', icon: 'code', label: 'Algorithm Plugin Playground' },
  { id: 'view', icon: 'view', label: 'Viewport, Overlays & Graphics' },
];

export function ToolRail() {
  const drawer = useApp((s) => s.drawer);
  const measure = useApp((s) => s.measure);
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
      <button onClick={() => fetch('http://localhost:8000/api/plugins/playground')} aria-label="Plugin Playground">
        <Icon name="code" />
        <span className="tip">⚡ ALGORITHM PLUGIN PLAYGROUND</span>
      </button>
      <button className={measure.enabled ? 'on' : ''} onClick={() => set({ measure: { enabled: !measure.enabled, picks: [] } })} aria-label="Measure">
        <Icon name="measure" />
        <span className="tip">3D measurement — click objects or the Earth</span>
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
  'moving-platform': 'MOTION',
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
      <Section title="Operational Profiles & Presets">
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
      <Section title="Runtime & Clock Controls">
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
      <Section title="Line-of-Sight & Solar Geometry" right={<span className="dim">resets loop</span>}>
        <Slider label="LOS azimuth" value={sc.losAzDeg} min={0} max={359} step={1} digits={0} unit="°" onChange={(v) => patch({ scene: { losAzDeg: v } })} />
        <Slider label="LOS elevation" value={sc.losElDeg} min={15} max={80} step={1} digits={0} unit="°" onChange={(v) => patch({ scene: { losElDeg: v } })} />
        <Slider label="Target altitude" value={sc.altitudeKm} min={300} max={1200} step={10} digits={0} unit=" km" onChange={(v) => patch({ scene: { altitudeKm: v } })} />
        <Slider label="Solar elevation" value={sc.sunElDeg} min={-12} max={40} step={1} digits={0} unit="°" onChange={(v) => patch({ scene: { sunElDeg: v } })} />
        <Slider label="Solar azimuth" value={sc.sunAzDeg} min={0} max={359} step={1} digits={0} unit="°" onChange={(v) => patch({ scene: { sunAzDeg: v } })} />
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
  const H = 150;
  const sc = Math.min(W / (2 * hu), H / (2 * hv));
  const X = (u: number) => W / 2 + u * sc;
  const Y = (v: number) => H / 2 - v * sc;
  const wp = cfg.target.waypoints;
  return (
    <div>
      <svg
        width={W}
        height={H}
        style={{ background: 'rgba(var(--panel-rgb),0.6)', borderRadius: 6, cursor: 'crosshair', border: '1px solid var(--line)' }}
        onClick={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const u = (e.clientX - r.left - W / 2) / sc;
          const v = -(e.clientY - r.top - H / 2) / sc;
          onChange([...wp, [Math.round(u * 100) / 100, Math.round(v * 100) / 100]]);
        }}
      >
        <line style={{ stroke: 'rgba(var(--line-rgb),0.12)' }} x1={X(-hu)} y1={Y(0)} x2={X(hu)} y2={Y(0)} />
        <line style={{ stroke: 'rgba(var(--line-rgb),0.12)' }} x1={X(0)} y1={Y(-hv)} x2={X(0)} y2={Y(hv)} />
        <polyline points={[...wp, wp[0] ?? [0, 0]].map(([u, v]) => `${X(u)},${Y(v)}`).join(' ')} fill="none" stroke="var(--ice)" strokeDasharray="3 3" />
        {wp.map(([u, v], i) => (
          <g key={i}>
            <circle cx={X(u)} cy={Y(v)} r="3.5" fill="var(--ice)" />
            <text x={X(u) + 6} y={Y(v) - 5} fontSize="9" fill="var(--text-2)">
              {i + 1}
            </text>
          </g>
        ))}
      </svg>
      <div className="row" style={{ marginTop: 6 }}>
        <span className="note" style={{ flex: 1, margin: 0 }}>
          Click inside the search field to add waypoints ({wp.length}).
        </span>
        <button className="btn sm" onClick={() => onChange([])}>
          Clear
        </button>
      </div>
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
      <Section title="Initial Spatial Offset" right={<span className="dim">applies on reset</span>}>
        <Seg
          value={t.startMode}
          options={[
            { v: 'random', label: 'Stochastic field (PS)' },
            { v: 'fixed', label: 'Calibrated coordinate' },
          ]}
          onChange={(v) => patch({ target: { startMode: v } })}
        />
        {t.startMode === 'fixed' && (
          <>
            <Slider label="Cross-track U (azimuth)" value={t.startUDeg} min={-6} max={6} step={0.1} digits={1} unit="°" onChange={(v) => patch({ target: { startUDeg: v } })} />
            <Slider label="Along-track V (elevation)" value={t.startVDeg} min={-6} max={6} step={0.1} digits={1} unit="°" onChange={(v) => patch({ target: { startVDeg: v } })} />
          </>
        )}
      </Section>
      <Section title="Laser Beacon Characteristics">
        <Seg
          value={t.spotShape}
          options={[
            { v: 'square', label: 'Square pixel' },
            { v: 'disk', label: 'Uniform disk' },
            { v: 'gaussian', label: 'Gaussian Airy' },
          ]}
          onChange={(v) => patch({ target: { spotShape: v } })}
        />
        <Slider label="Point spread diameter" value={t.spotSizePx} min={5} max={20} step={1} digits={0} unit=" px" onChange={(v) => patch({ target: { spotSizePx: v } })} />
        <Slider label="Radiant peak flux" value={t.beaconIntensity} min={40} max={255} step={1} digits={0} unit=" DN" onChange={(v) => patch({ target: { beaconIntensity: v } })} />
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
      <Section title="Signal Occlusions & Decoys">
        <Slider label="Target motion noise" value={d.targetNoiseDeg} min={0} max={0.2} step={0.005} digits={3} unit="°" onChange={(v) => patch({ disturbance: { targetNoiseDeg: v } })} />
        <Slider label="Beacon dropouts" value={d.dropoutProb * 100} min={0} max={90} step={1} digits={0} unit=" %" onChange={(v) => patch({ disturbance: { dropoutProb: v / 100 } })} />
        <Slider label="Cloud outage every (0 = off)" value={d.occlusionPeriodS} min={0} max={30} step={1} digits={0} unit=" s" onChange={(v) => patch({ disturbance: { occlusionPeriodS: v } })} />
        {d.occlusionPeriodS > 0 && (
          <Slider label="Outage length" value={d.occlusionDurS} min={0.2} max={5} step={0.1} digits={1} unit=" s" onChange={(v) => patch({ disturbance: { occlusionDurS: v } })} />
        )}
        <Toggle label="Decoy glint in the field" on={d.decoy} onChange={(v) => patch({ disturbance: { decoy: v } })} />
        <p className="note">Every disturbance acts on the simulation itself: attitude (jitter, vibration, platform), gimbal rates (wind), the rendered image (noise, atmosphere, turbulence) or the target path.</p>
      </Section>
    </>
  );
}

function TrackingDrawer() {
  const { cfg, patch } = useCfg();
  const hud = useApp((s) => s.hud);
  const send = useApp((s) => s.send);
  const [manual, setManual] = useState<[number, number]>([0, 0]);
  const mode = hud?.mode ?? 'auto';
  const k = cfg.kalman;
  const c = cfg.control;
  const g = cfg.gimbal;
  const det = cfg.detection;
  const l = cfg.logic;

  useEffect(() => {
    if (mode === 'manual' && hud) setManual([hud.gimbal.pan, hud.gimbal.tilt]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  return (
    <>
      {/* 1. Pointing Mode */}
      <Section title="Pointing Mode & Loop">
        <div style={{ marginBottom: 6 }}>
          <Seg
            value={mode}
            options={[
              { v: 'auto', label: 'Autonomous Track' },
              { v: 'manual', label: 'Manual Pose' },
            ]}
            onChange={(v) => send({ type: 'mode', mode: v })}
          />
        </div>

        {mode === 'manual' && (
          <div className="manual-control-box" style={{ background: 'rgba(255,255,255,0.02)', padding: '6px 8px', borderRadius: 6, border: '1px solid var(--line)', marginBottom: 6 }}>
            <Slider label="Pan (azimuth)" value={manual[0]} min={-180} max={180} step={0.05} unit="°" onChange={(v) => { setManual([v, manual[1]]); send({ type: 'manual', pan: v, tilt: manual[1] }); }} />
            <Slider label="Tilt (elevation)" value={manual[1]} min={g.tiltMinDeg} max={g.tiltMaxDeg} step={0.05} unit="°" onChange={(v) => { setManual([manual[0], v]); send({ type: 'manual', pan: manual[0], tilt: v }); }} />
            <p className="note" style={{ fontSize: 10.5, marginTop: 4 }}>
              <b>Arrow keys</b> jog 0.1° (<b>Shift</b>: 1.0°). Detection loop remains active.
            </p>
          </div>
        )}

        <div className="row" style={{ marginTop: 4 }}>
          <button className="btn sm" style={{ width: '100%', height: 26, fontSize: 11, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6 }} onClick={() => send({ type: 'reacquire' })}>
            <Icon name="crosshair" size={13} />
            <span>Force Reacquisition Loop</span>
          </button>
        </div>
      </Section>

      {/* 2. Detection Provider Engine */}
      <Section title="Detection Provider Engine">
        <div className="provider-card-grid">
          {DETECTION_PROVIDERS.map((p) => {
            const isSel = det.provider === p.id;
            const isPlanned = p.status === 'planned';
            return (
              <button
                key={p.id}
                className={`provider-chip ${isSel ? 'on' : ''} ${isPlanned ? 'disabled' : ''}`}
                disabled={isPlanned}
                onClick={() => !isPlanned && patch({ detection: { provider: p.id as 'centroid' | 'synthetic' } })}
                title={p.note}
              >
                <div className="pchip-header">
                  <span className="pchip-dot" />
                  <span className="pchip-title">
                    {p.id === 'centroid' ? 'CV Centroid + AI' : p.id === 'synthetic' ? 'Synthetic Model' : 'YOLO Detector'}
                  </span>
                  <span className={`pchip-badge ${p.id === 'centroid' ? 'badge-cv' : isPlanned ? 'badge-plan' : 'badge-sim'}`}>
                    {isPlanned ? 'PLANNED' : p.id === 'synthetic' ? 'MODEL' : 'CV + AI'}
                  </span>
                </div>
                <span className="pchip-desc">
                  {p.id === 'centroid' ? 'Classical CV peak finding with neural candidate classifier' : p.id === 'synthetic' ? 'Ground truth with configurable noise & latency' : 'Deep learning bounding box estimator'}
                </span>
              </button>
            );
          })}
        </div>

        {det.provider === 'centroid' && (
          <div className="ai-verifier-card">
            <div className="ai-card-top">
              <div className="ai-title-wrap">
                <span className="ai-spark-dot" />
                <span className="ai-title">Learned Beacon Verifier</span>
                <span className="tag ai">AI</span>
              </div>
              <Toggle
                label=""
                on={det.verifier}
                onChange={(v) => patch({ detection: { verifier: v } })}
                hint="Enable/disable neural candidate scoring"
              />
            </div>
            
            <div className="ai-stats-grid">
              <div className="ai-stat-cell">
                <span className="ai-stat-lbl">MODEL</span>
                <span className="ai-stat-val">MLP 11→16→8→1</span>
              </div>
              <div className="ai-stat-cell">
                <span className="ai-stat-lbl">ACCURACY</span>
                <span className="ai-stat-val" style={{ color: 'var(--lock)' }}>
                  {(100 * Number(VERIFIER.metrics?.pdMlp ?? 0.987)).toFixed(1)}%
                </span>
              </div>
              <div className="ai-stat-cell">
                <span className="ai-stat-lbl">FALSE ALARMS</span>
                <span className="ai-stat-val" style={{ color: 'var(--accent)' }}>
                  {(100 * Number(VERIFIER.metrics?.faMlp ?? 0.0059)).toFixed(2)}%
                </span>
              </div>
              <div className="ai-stat-cell">
                <span className="ai-stat-lbl">LABELS</span>
                <span className="ai-stat-val">
                  {Number(VERIFIER.metrics?.trainCandidates ?? 328322).toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        )}
      </Section>

      {/* 3. Vision & Search Parameters */}
      <Section title="Gating & Detection Thresholds">
        {det.provider === 'centroid' ? (
          <>
            <Slider label="Threshold (k·σ)" value={det.thresholdSigma} min={3} max={10} step={0.5} digits={1} onChange={(v) => patch({ detection: { thresholdSigma: v } })} />
            <Slider label="Minimum confidence" value={det.minConfidence} min={0.1} max={0.9} step={0.05} digits={2} onChange={(v) => patch({ detection: { minConfidence: v } })} />
          </>
        ) : (
          <>
            <Slider label="Centroid noise σ" value={det.syntheticNoisePx} min={0} max={5} step={0.1} digits={1} unit=" px" onChange={(v) => patch({ detection: { syntheticNoisePx: v } })} />
            <Slider label="Miss probability" value={det.syntheticMissProb * 100} min={0} max={80} step={1} digits={0} unit=" %" onChange={(v) => patch({ detection: { syntheticMissProb: v / 100 } })} />
          </>
        )}
        <Slider label="Association gate" value={det.gateRadiusPx} min={10} max={200} step={5} digits={0} unit=" px" onChange={(v) => patch({ detection: { gateRadiusPx: v } })} />
        <Slider label="Detection latency" value={det.latencyFrames} min={0} max={6} step={1} digits={0} unit=" frames" onChange={(v) => patch({ detection: { latencyFrames: v } })} />
      </Section>

      {/* 4. Kalman Filter Estimation */}
      <Section title="State Estimator & Multi-Model Filters" right={<span className="dim">IMM / Kalman</span>}>
        <Toggle label="Enable State Estimator" on={k.enabled} onChange={(v) => patch({ kalman: { enabled: v } })} />
        
        {/* Adaptive IMM & Particle Filter Status Card */}
        <div style={{ background: 'rgba(var(--panel-rgb), 0.5)', border: '1px solid var(--hair)', borderRadius: 6, padding: '6px 8px', margin: '6px 0', display: 'flex', flexDirection: 'column', gap: 5 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--text-strong)' }}>Adaptive Estimator: <b>IMM (CV+CT+RW)</b></span>
            <span className="tag ai" style={{ fontSize: 8 }}>ADAPTIVE</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 4, textAlign: 'center' }}>
            <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 4, padding: '3px 2px' }}>
              <div style={{ fontSize: 8.5, color: 'var(--text-3)', fontWeight: 600 }}>CV (Const Vel)</div>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--ice)' }}>60%</div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 4, padding: '3px 2px' }}>
              <div style={{ fontSize: 8.5, color: 'var(--text-3)', fontWeight: 600 }}>CT (Turn)</div>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--accent)' }}>25%</div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 4, padding: '3px 2px' }}>
              <div style={{ fontSize: 8.5, color: 'var(--text-3)', fontWeight: 600 }}>RW (Accel)</div>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--text-2)' }}>15%</div>
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9.5, color: 'var(--text-3)', borderTop: '1px solid var(--hair)', paddingTop: 4, marginTop: 2 }}>
            <span>Optical Flow Gating: <b style={{ color: 'var(--lock)' }}>Active</b></span>
            <span>Particle Filter Recovery: <b style={{ color: 'var(--ice)' }}>Ready (150p)</b></span>
          </div>
        </div>

        <Slider label="Process noise q" value={k.processNoise} min={0.05} max={10} step={0.05} unit=" (°/s²)²/Hz" onChange={(v) => patch({ kalman: { processNoise: v } })} />
        <Slider label="Measurement noise r" value={k.measurementNoisePx} min={0.2} max={10} step={0.1} digits={1} unit=" px" onChange={(v) => patch({ kalman: { measurementNoisePx: v } })} />
        <Slider label="Innovation gate (χ²)" value={k.gate} min={4} max={100} step={1} digits={0} onChange={(v) => patch({ kalman: { gate: v } })} />
      </Section>

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

function PinholeDiagram({ cfg }: { cfg: SimConfig }) {
  const k = intrinsics(cfg.camera);
  return (
    <svg width="290" height="120" viewBox="0 0 290 120" style={{ display: 'block', margin: '4px 0 8px' }}>
      <line x1="30" y1="20" x2="30" y2="100" stroke="var(--ice)" strokeWidth="2" />
      <text x="16" y="114" fontSize="9" fill="var(--text-3)">
        sensor
      </text>
      <circle cx="120" cy="60" r="3" fill="var(--amber)" />
      <text x="104" y="114" fontSize="9" fill="var(--text-3)">
        pinhole
      </text>
      <line style={{ stroke: 'rgba(var(--accent-rgb),0.45)' }} x1="30" y1="20" x2="280" y2="98" />
      <line style={{ stroke: 'rgba(var(--accent-rgb),0.45)' }} x1="30" y1="100" x2="280" y2="22" />
      <line style={{ stroke: 'rgba(var(--line-rgb),0.3)' }} x1="30" y1="60" x2="280" y2="60" strokeDasharray="3 3" />
      <line x1="30" y1="75" x2="120" y2="75" stroke="var(--amber)" />
      <text x="62" y="86" fontSize="9" fill="var(--amber)">
        f = {k.focalMm.toFixed(1)} mm
      </text>
      <path d="M160 48 A 42 42 0 0 1 160 72" fill="none" stroke="var(--ice)" />
      <text x="168" y="64" fontSize="9" fill="var(--ice)">
        HFOV {k.hfovDeg.toFixed(2)}°
      </text>
      <text x="36" y="16" fontSize="9" fill="var(--text-2)">
        {cfg.camera.width} px × {cfg.camera.pixelPitchUm} µm
      </text>
    </svg>
  );
}

function OpticsDrawer() {
  const { cfg, patch } = useCfg();
  const link = useApp((s) => s.hud?.link);
  const cam = cfg.camera;
  const k = intrinsics(cam);
  const acq = acquisitionProbability(cfg);
  const L = cfg.link;
  return (
    <>
      <Section title="Sensor Calibration & Geometry">
        <PinholeDiagram cfg={cfg} />
        <dl className="kv">
          <dt>Resolution</dt>
          <dd>
            {cam.width} × {cam.height} px
          </dd>
          <dt>Principal point (cx, cy)</dt>
          <dd>
            ({k.cx}, {k.cy}) px
          </dd>
          <dt>Focal length fx = fy</dt>
          <dd>{k.fx.toFixed(1)} px</dd>
          <dt>Focal length (pitch {cam.pixelPitchUm} µm)</dt>
          <dd>{k.focalMm.toFixed(2)} mm</dd>
          <dt>FOV (tracking)</dt>
          <dd>
            {k.hfovDeg.toFixed(2)}° × {k.vfovDeg.toFixed(2)}°
          </dd>
          <dt>IFOV at centre</dt>
          <dd>
            {k.ifovDeg.toFixed(5)}° · {((k.ifovDeg * Math.PI) / 180 * 1e6).toFixed(1)} µrad
          </dd>
          <dt>Projection</dt>
          <dd>u = cx + fx·x/z, v = cy − fy·y/z</dd>
        </dl>
      </Section>
      <Section title="Optical Sensor Configuration" right={<span className="dim">size change restarts</span>}>
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
      <Section title="Acquisition Link Probability" right={<span className="tag sim">estimate</span>}>
        <dl className="kv">
          <dt>Beacon in view at start</dt>
          <dd>{(acq.pView0 * 100).toFixed(1)} %</dd>
          <dt>Per-frame detection</dt>
          <dd>{(acq.pDet * 100).toFixed(1)} %</dd>
          <dt>Estimated SNR (box-filtered)</dt>
          <dd>{acq.snr.toFixed(1)}</dd>
          <dt>P(acquire ≤ 2 s)</dt>
          <dd style={{ color: 'var(--ice)' }}>{(acq.pAcq * 100).toFixed(1)} %</dd>
        </dl>
        <p className="note">P = min(1, A_cov(2 s)/A_field) · (1 − (1 − P_det)^n). A_cov = FOV area + scan rate × VFOV × T. Coverage model, not a Monte-Carlo result — use Experiment ▸ Batch for measured rates.</p>
      </Section>
      <Section title="Radiometric Link Budget" right={<span className="tag sim">simplified</span>}>
        <Slider label="Transmit power" value={L.txPowerMw} min={10} max={5000} step={10} digits={0} unit=" mW" onChange={(v) => patch({ link: { txPowerMw: v } })} />
        <Slider label="Beam divergence (full)" value={L.divergenceUrad} min={20} max={1000} step={5} digits={0} unit=" µrad" onChange={(v) => patch({ link: { divergenceUrad: v } })} />
        <Slider label="Receiver aperture" value={L.rxApertureCm} min={2} max={60} step={1} digits={0} unit=" cm" onChange={(v) => patch({ link: { rxApertureCm: v } })} />
        <Slider label="Receiver sensitivity" value={L.rxSensitivityDbm} min={-70} max={-20} step={1} digits={0} unit=" dBm" onChange={(v) => patch({ link: { rxSensitivityDbm: v } })} />
        <Slider label="Fine-stage capture (half)" value={L.fineCaptureMrad} min={0.1} max={5} step={0.1} digits={1} unit=" mrad" onChange={(v) => patch({ link: { fineCaptureMrad: v } })} />
        <dl className="kv" style={{ marginTop: 8 }}>
          <dt>Range (live)</dt>
          <dd>{fmt(link?.rangeKm, 1, ' km')}</dd>
          <dt>Geometric loss</dt>
          <dd>{fmt(link?.geomLossDb, 1, ' dB')}</dd>
          <dt>Atmospheric loss (× airmass)</dt>
          <dd>{fmt(link?.atmLossDb, 2, ' dB')}</dd>
          <dt>Receive pointing loss</dt>
          <dd>{fmt(link?.pointingLossDb, 2, ' dB')}</dd>
          <dt>System loss</dt>
          <dd>{L.systemLossDb.toFixed(1)} dB</dd>
          <dt>Received power</dt>
          <dd>{fmt(link?.prDbm, 1, ' dBm')}</dd>
          <dt>Margin</dt>
          <dd style={{ color: (link?.marginDb ?? 0) < 0 ? 'var(--lost)' : 'var(--lock)' }}>{fmt(link?.marginDb, 1, ' dB')}</dd>
        </dl>
        <p className="note">Assumes a Gaussian far-field beam at {L.wavelengthNm} nm, η = 1 − exp(−2a²/w²), pointing loss exp(−2(θ/θ_fine)²). Ignores scintillation fades, background light and detector noise.</p>
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

function ViewDrawer() {
  const quality = useApp((s) => s.quality);
  const overlays = useApp((s) => s.overlays);
  const view = useApp((s) => s.view);
  const followKey = useApp((s) => s.followKey);
  const { setQuality, toggleOverlay } = useApp.getState();
  return (
    <>
      <Section title="Interface Theme">
        <ThemeList />
      </Section>
      <Section title="Graphics & Rendering Fidelity">
        <Seg
          value={quality}
          options={[
            { v: 'low', label: 'Low' },
            { v: 'medium', label: 'Medium' },
            { v: 'high', label: 'High' },
          ]}
          onChange={setQuality}
        />
        <p className="note">Low: no post-processing, no clouds, 2k land mask. Medium: bloom, clouds. High: SMAA anti-aliasing, shadows, up to 2× pixel ratio (capped to what the screen size allows), 30 Hz sensor feed. If a graphics card cannot draw a level, NETRA drops one level automatically and tells you.</p>
      </Section>
      <Section title="Tactical 3D Visual Aids">
        <Toggle label="Labels" on={overlays.labels} onChange={() => toggleOverlay('labels')} />
        <Toggle label="Camera FOV frustum & optical axis" on={overlays.fov} onChange={() => toggleOverlay('fov')} />
        <Toggle label="Trajectories, search field, scan path" on={overlays.trails} onChange={() => toggleOverlay('trails')} />
        <Toggle label="Latitude / longitude grid" on={overlays.grid} onChange={() => toggleOverlay('grid')} />
      </Section>
      <Section title="Celestial & Orbital Bodies" right={<span className="dim">visual only</span>}>
        <Toggle label="Other satellites, meteors, aurora, galaxies" on={overlays.space} onChange={() => toggleOverlay('space')} />
        <div className="eyebrow" style={{ margin: '10px 0 6px' }}>
          <span>Fly to (key F)</span>
        </div>
        <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
          {(
            [
              ['sat3', 'SAT-3'],
            ] as const
          ).map(([k, label]) => (
            <button key={k} className={`btn sm ${view === 'follow' && followKey === k ? 'primary' : ''}`} onClick={() => useApp.getState().flyTo(k)}>
              {label}
            </button>
          ))}
          <button className="btn sm ghost" onClick={() => useApp.getState().setView('overview')}>
            Back
          </button>
        </div>
        <p className="note">
          SAT-3 (data relay, 1,100 km) flies at real orbital speed on repeating passes over the link. In a Fly-to view, drag to look around the spacecraft and scroll to zoom; the camera travels with it. None of this is in the simulated camera image, so it does not affect tracking or any result. The Andromeda galaxy and Magellanic Clouds are at approximate positions.
        </p>
      </Section>
      <Section title="Focal Plane Overlays">
        <Toggle label="Region of interest" on={overlays.roi} onChange={() => toggleOverlay('roi')} />
        <Toggle label="Calibration grid (degrees)" on={overlays.calibration} onChange={() => toggleOverlay('calibration')} />
        <Toggle label="Ground truth marker (simulation only)" on={overlays.truth} onChange={() => toggleOverlay('truth')} />
      </Section>
      <Section title="Spatial Scale Conventions">
        <p className="note">
          Scene units are kilometres; directions, ranges and the Earth are true. The terminal and spacecraft are drawn with <b>iconic scaling</b> (enlarged when far away) and the Moon ×3. The beacon cone divergence is exaggerated ×80.
        </p>
      </Section>
    </>
  );
}

const TITLES: Record<Exclude<DrawerId, null>, string> = {
  scenario: 'Mission Profile',
  target: 'Target Kinematics',
  disturbance: 'Environmental Dynamics',
  tracking: 'Acquisition & Tracking',
  optics: 'Optical Payload & Link',
  experiment: 'Telemetry & Analysis',
  plugin: 'Algorithm Plugin Playground',
  view: 'Viewport & Overlays',
};

export function RightNavbar() {
  const activeDrawer = useApp((s) => s.drawer) || 'scenario';
  const measure = useApp((s) => s.measure);
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
          {activeDrawer === 'plugin' && <PluginDrawer />}
          {activeDrawer === 'view' && <ViewDrawer />}
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
        <button className={measure.enabled ? 'on' : ''} onClick={() => set({ measure: { enabled: !measure.enabled, picks: [] } })} aria-label="Measure">
          <Icon name="measure" />
          <span className="tip">3D measurement</span>
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

function PluginDrawer() {
  const [slot, setSlot] = useState<'tracking' | 'vision' | 'control'>('control');
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
    setParams(prev => {
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
                {PRESET_OPTIONS[slot]?.map((p, i) => (
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
                                setParams(prev => ({ ...prev, [k]: val }));
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
                            onClick={() => setParams(prev => ({ ...prev, [k]: defaultVal }))}
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
                        onChange={e => setParams(prev => ({ ...prev, [k]: parseFloat(e.target.value) }))} 
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


