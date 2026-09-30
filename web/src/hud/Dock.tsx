/**
 * Bottom dock: the coarse-alignment chain (the loop, left to right, with live values)
 * and the three readout groups TARGET · CAMERA/GIMBAL · LINK.
 */
import { useEffect, useRef } from 'react';
import { history, historySlice, live, stateColor, useApp } from '../state/store';
import type { Snapshot, TrackState } from '../core/telemetry/types';
import { Icon, cssVar, fmt, fmtSigned } from './ui';

const ACTIVE: Record<TrackState, number> = {
  IDLE: 0,
  SEARCHING: 0,
  DETECTED: 2,
  ACQUIRING: 5,
  TRACKING: 6,
  LOCKED: 7,
  LOST: 5,
  REACQUIRING: 5,
};

function Spark() {
  const ref = useRef<HTMLCanvasElement>(null);
  const lockPx = useApp((s) => s.config.logic.lockPx);
  useEffect(() => {
    let raf = 0;
    let last = -1;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      if (history.head === last) return;
      last = history.head;
      const c = ref.current;
      if (!c) return;
      const w = (c.width = 200);
      const h = (c.height = 40);
      const ctx = c.getContext('2d')!;
      ctx.clearRect(0, 0, w, h);
      const { v } = historySlice('errPx', 16);
      const max = 60;
      const y = (e: number) => h - 2 - (Math.log10(1 + Math.min(max, e)) / Math.log10(1 + max)) * (h - 4);
      
      // Lock threshold line
      ctx.strokeStyle = 'rgba(63, 185, 80, 0.4)';
      ctx.setLineDash([2, 3]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, y(lockPx));
      ctx.lineTo(w, y(lockPx));
      ctx.stroke();
      ctx.setLineDash([]);

      // Error curve
      ctx.strokeStyle = cssVar('--ser-a');
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      let started = false;
      const points: [number, number][] = [];
      for (let i = 0; i < v.length; i++) {
        const x = (i / Math.max(1, v.length - 1)) * w;
        if (!Number.isFinite(v[i])) continue;
        const py = y(v[i]);
        points.push([x, py]);
        if (!started) {
          ctx.moveTo(x, py);
          started = true;
        } else {
          ctx.lineTo(x, py);
        }
      }
      ctx.stroke();

      // Subtle gradient fill under curve
      if (points.length > 1) {
        const grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, 'rgba(245, 185, 66, 0.22)');
        grad.addColorStop(1, 'rgba(245, 185, 66, 0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(points[0][0], points[0][1]);
        for (let i = 1; i < points.length; i++) {
          ctx.lineTo(points[i][0], points[i][1]);
        }
        ctx.lineTo(points[points.length - 1][0], h);
        ctx.lineTo(points[0][0], h);
        ctx.closePath();
        ctx.fill();
      }
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [lockPx]);
  return <canvas ref={ref} className="chain-spark" />;
}

export function AlignmentChain({ s }: { s: Snapshot | null }) {
  const n = s ? ACTIVE[s.state] : 0;
  const coasting = s?.state === 'LOST' || s?.state === 'REACQUIRING';
  const isLocked = s?.state === 'LOCKED';
  const isTracking = s?.state === 'TRACKING';
  const d = s?.detection;
  const est = s?.kalman.estPx;
  const cx = (s?.camera.width ?? 640) / 2;
  const cy = (s?.camera.height ?? 480) / 2;
  const ifov = s?.camera.ifovDeg ?? 0.00625;
  const ex = est ? est[0] - cx : d ? d.x - cx : null;
  const ey = est ? est[1] - cy : d ? d.y - cy : null;

  const nodes = [
    {
      num: '01',
      k: 'INITIAL ERROR',
      v: fmt(live.initialErrPx, 0, ' px'),
      s: 'First Acquisition',
      tag: 'REF',
    },
    {
      num: '02',
      k: 'DETECTION',
      v: d ? `${(d.confidence * 100).toFixed(0)} %` : s?.state === 'SEARCHING' ? 'Scanning' : '—',
      s: d ? `(${d.x.toFixed(0)}, ${d.y.toFixed(0)}) px` : 'Centroid Fix',
      tag: d ? 'SNR 85' : 'CNN',
    },
    {
      num: '03',
      k: 'ERROR ESTIMATE',
      v: ex !== null && ey !== null ? `${fmtSigned(ex)}, ${fmtSigned(ey)}` : '—',
      s: ex !== null && ey !== null ? `${(Math.hypot(ex, ey) * ifov).toFixed(3)}° · Kalman` : 'State Est.',
      tag: 'KF',
    },
    {
      num: '04',
      k: 'PAN / TILT CMD',
      v: s ? `${fmtSigned(s.gimbal.panCmd, 2)}, ${fmtSigned(s.gimbal.tiltCmd, 2)}` : '—',
      s: 'PID + Feedforward',
      tag: '°/s',
    },
    {
      num: '05',
      k: 'GIMBAL MOTION',
      v: s ? `${s.gimbal.pan.toFixed(2)}°, ${s.gimbal.tilt.toFixed(2)}°` : '—',
      s: 'Encoder Feedback',
      tag: 'AZ/EL',
    },
    {
      num: '06',
      k: 'PIXEL ERROR',
      v: fmt(s?.error.magPx, 1, ' px'),
      s: 'Realtime Trace',
      spark: true,
      tag: 'RT',
    },
    {
      num: '07',
      k: 'OPTICAL LOCK',
      v: isLocked ? 'LOCKED' : isTracking ? 'TRACKING' : s?.metrics.acquisitionS !== null && s?.metrics.acquisitionS !== undefined ? 'RELOCKING' : 'SEARCHING',
      s: s?.metrics.acquisitionS !== null && s?.metrics.acquisitionS !== undefined ? `Lock: ${s.metrics.acquisitionS.toFixed(2)}s` : 'Coarse Alignment',
      tag: 'STATUS',
      isLockNode: true,
    },
  ];

  return (
    <div className="chain-container" aria-label="Tracking loop pipeline">
      <div className="chain-stream">
        {nodes.map((node, i) => {
          const isActive = i < n;
          const isHot = i === n - 1;
          return (
            <div key={node.k} className="chain-segment">
              <div
                className={`chain-card ${isActive ? 'active' : ''} ${isHot ? 'hot' : ''} ${node.isLockNode ? (isLocked ? 'locked-card' : 'acquiring-card') : ''}`}
              >
                <div className="chain-card-top">
                  <span className="chain-num">{node.num}</span>
                  <span className="chain-label">{node.k}</span>
                  <span className="chain-tag">{node.tag}</span>
                </div>
                <div
                  className="chain-val"
                  style={
                    node.isLockNode && isLocked
                      ? { color: 'var(--lock)' }
                      : coasting && i >= 2 && i <= 4
                      ? { color: 'var(--warn)' }
                      : undefined
                  }
                >
                  {node.v}
                </div>
                {node.spark ? <Spark /> : <div className="chain-sub">{node.s}</div>}
              </div>
              {i < nodes.length - 1 && (
                <div className={`chain-connector ${i < n - 1 ? 'flowing' : ''}`}>
                  <svg width="14" height="12" viewBox="0 0 14 12" fill="none">
                    <path
                      d="M1 6H10M10 6L6.5 2.5M10 6L6.5 9.5"
                      stroke="currentColor"
                      strokeWidth="1.4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Field-of-regard map: search field, camera footprint, target, estimate, scan trace. */
function FieldMap({ s }: { s: Snapshot }) {
  const cfg = useApp((st) => st.config.logic);
  const hu = cfg.searchHalfUDeg;
  const hv = cfg.searchHalfVDeg;
  const W = 110;
  const H = 76;
  const sc = Math.min((W - 10) / (2 * hu), (H - 10) / (2 * hv));
  const X = (u: number) => W / 2 + u * sc;
  const Y = (v: number) => H / 2 - v * sc;
  const bu = s.gimbal.boresightU;
  const bv = s.gimbal.boresightV;
  const fw = s.camera.hfovDeg * sc;
  const fh = s.camera.vfovDeg * sc;
  return (
    <div className="instrument-wrap" title="Field of Regard & Boresight Search Footprint">
      <svg className="instrument-svg" viewBox={`0 0 ${W} ${H}`}>
        <defs>
          <radialGradient id="radar-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(var(--accent-rgb), 0.12)" />
            <stop offset="100%" stopColor="rgba(var(--accent-rgb), 0.0)" />
          </radialGradient>
        </defs>
        {/* Radar background grid */}
        <rect x="2" y="2" width={W - 4} height={H - 4} rx="4" fill="#04070c" stroke="rgba(255, 255, 255, 0.08)" strokeWidth="1" />
        <circle cx={W / 2} cy={H / 2} r={Math.min(W, H) * 0.42} fill="url(#radar-glow)" stroke="rgba(255, 255, 255, 0.08)" strokeDasharray="2 3" />
        
        {/* Search FOV bounds */}
        <rect
          x={X(-hu)}
          y={Y(hv)}
          width={2 * hu * sc}
          height={2 * hv * sc}
          fill="none"
          stroke="rgba(var(--accent-rgb), 0.35)"
          strokeWidth="1"
          strokeDasharray="2 3"
        />
        <line x1={X(0)} y1="4" x2={X(0)} y2={H - 4} stroke="rgba(255, 255, 255, 0.1)" strokeDasharray="1 2" />
        <line x1="4" y1={Y(0)} x2={W - 4} y2={Y(0)} stroke="rgba(255, 255, 255, 0.1)" strokeDasharray="1 2" />

        {/* Camera footprint */}
        <rect
          x={X(bu) - fw / 2}
          y={Y(bv) - fh / 2}
          width={fw}
          height={fh}
          fill="rgba(var(--accent-rgb), 0.12)"
          stroke={stateColor(s.state)}
          strokeWidth="1.2"
          rx="1"
        />

        {/* Target position */}
        <circle cx={X(s.target.u)} cy={Y(s.target.v)} r="2.5" fill="var(--text-strong)" />
        <circle cx={X(s.target.u)} cy={Y(s.target.v)} r="5.5" fill="none" stroke="var(--accent)" strokeWidth="1" />
        <line x1={X(s.target.u) - 7} y1={Y(s.target.v)} x2={X(s.target.u) + 7} y2={Y(s.target.v)} stroke="var(--accent)" strokeWidth="0.8" opacity="0.6" />
        <line x1={X(s.target.u)} y1={Y(s.target.v) - 7} x2={X(s.target.u)} y2={Y(s.target.v) + 7} stroke="var(--accent)" strokeWidth="0.8" opacity="0.6" />
      </svg>
      <span className="inst-tag">RADAR FOR</span>
    </div>
  );
}

/** Pan compass + tilt arc with commanded-rate indicators. */
function GimbalDial({ s }: { s: Snapshot }) {
  const pan = (s.gimbal.pan * Math.PI) / 180;
  const tilt = (s.gimbal.tilt * Math.PI) / 180;
  const R = 27;
  const cx = 35;
  const cy = 38;
  const px = cx + R * Math.sin(pan);
  const py = cy - R * Math.cos(pan);
  const tx = 80 + 24 * Math.cos(tilt);
  const ty = 64 - 24 * Math.sin(tilt);
  return (
    <div className="instrument-wrap" title="Gimbal Azimuth Compass & Elevation Angle">
      <svg className="instrument-svg" viewBox="0 0 110 76">
        <rect x="2" y="2" width="106" height="72" rx="4" fill="#04070c" stroke="rgba(255, 255, 255, 0.08)" strokeWidth="1" />
        
        {/* Azimuth Compass */}
        <circle cx={cx} cy={cy} r={R} fill="none" stroke="rgba(255, 255, 255, 0.12)" strokeWidth="1" />
        {Array.from({ length: 8 }).map((_, i) => {
          const a = (i * Math.PI) / 4;
          return (
            <line
              key={i}
              x1={cx + (R - 3) * Math.sin(a)}
              y1={cy - (R - 3) * Math.cos(a)}
              x2={cx + R * Math.sin(a)}
              y2={cy - R * Math.cos(a)}
              stroke="rgba(255, 255, 255, 0.25)"
              strokeWidth="1"
            />
          );
        })}
        <text x={cx} y={cy - R + 7} fontSize="6.5" fill="var(--accent)" textAnchor="middle" fontFamily="var(--f-mono)" fontWeight="700">
          N
        </text>
        <line x1={cx} y1={cy} x2={px} y2={py} stroke="var(--ice)" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx={cx} cy={cy} r="2.5" fill="var(--ice)" />

        {/* Tilt Arc */}
        <path d="M80 64 A24 24 0 0 1 104 64" transform="rotate(-90 80 64)" fill="none" stroke="rgba(255, 255, 255, 0.12)" strokeWidth="1.2" />
        <line x1="80" y1="64" x2="104" y2="64" stroke="rgba(255, 255, 255, 0.2)" strokeWidth="1" />
        <line x1="80" y1="64" x2={tx} y2={ty} stroke="var(--amber-hi)" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="80" cy="64" r="2" fill="var(--amber-hi)" />
        <text x="80" y="71" fontSize="6.5" fill="var(--text-3)" fontFamily="var(--f-mono)" fontWeight="600">
          EL {s.gimbal.tilt.toFixed(0)}°
        </text>
      </svg>
      <span className="inst-tag">AZ / EL DIAL</span>
    </div>
  );
}

/** Alignment Quality Score arc. */
function AqsGauge({ s }: { s: Snapshot }) {
  const v = Math.max(0, Math.min(100, s.metrics.aqs));
  const a0 = Math.PI * 0.8;
  const a1 = Math.PI * 2.2;
  const a = a0 + (a1 - a0) * (v / 100);
  const R = 26;
  const cx = 55;
  const cy = 37;
  const arc = (from: number, to: number) => {
    const x0 = cx + R * Math.cos(from);
    const y0 = cy + R * Math.sin(from);
    const x1 = cx + R * Math.cos(to);
    const y1 = cy + R * Math.sin(to);
    return `M${x0} ${y0} A${R} ${R} 0 ${to - from > Math.PI ? 1 : 0} 1 ${x1} ${y1}`;
  };
  const col = v > 75 ? 'var(--lock)' : v > 45 ? 'var(--ice)' : 'var(--amber)';
  return (
    <div className="instrument-wrap" title="Alignment Quality Score (0–100)">
      <svg className="instrument-svg" viewBox="0 0 110 76">
        <rect x="2" y="2" width="106" height="72" rx="4" fill="#04070c" stroke="rgba(255, 255, 255, 0.08)" strokeWidth="1" />
        <path d={arc(a0, a1)} stroke="rgba(255, 255, 255, 0.1)" strokeWidth="4.5" fill="none" strokeLinecap="round" />
        <path d={arc(a0, Math.max(a0 + 0.01, a))} stroke={col} strokeWidth="4.5" fill="none" strokeLinecap="round" />
        <text x={cx} y={cy + 4} textAnchor="middle" fontSize="15" fill="var(--text-strong)" fontFamily="var(--f-mono)" fontWeight="700">
          {v.toFixed(0)}
        </text>
        <text x={cx} y={cy + 15} textAnchor="middle" fontSize="6.5" fill="var(--text-3)" fontFamily="var(--f-cond)" letterSpacing="0.08em">
          AQS QUALITY
        </text>
      </svg>
      <span className="inst-tag">QUALITY INDEX</span>
    </div>
  );
}

export function Dock() {
  const s = useApp((st) => st.hud);
  const analysisOpen = useApp((st) => st.analysisOpen);
  const set = useApp((st) => st.set);
  const lockPx = useApp((st) => st.config.logic.lockPx);

  return (
    <div className="dock">
      <AlignmentChain s={s} />

      <div className="dock-panels-row">
        {/* Panel 1: Target Acquisition & Remote Beacon */}
        <section className="telemetry-panel target-panel">
          <div className="tp-header">
            <div className="tp-title-group">
              <span className="tp-dot target-dot" />
              <h4 className="tp-title">TARGET · REMOTE BEACON</h4>
            </div>
            <div className={`tp-badge ${s?.target.inFov ? 'badge-active' : 'badge-warn'}`}>
              <span>{s?.target.inFov ? 'IN FOV' : 'OUT FOV'}</span>
            </div>
          </div>
          <div className="tp-body">
            <div className="tp-grid">
              <div className="tp-cell">
                <span className="tp-label">AZIMUTH</span>
                <span className="tp-val">{fmt(s?.target.az, 3)}<small>°</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">ELEVATION</span>
                <span className="tp-val">{fmt(s?.target.el, 3)}<small>°</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">RANGE</span>
                <span className="tp-val">{fmt(s?.target.rangeKm, 1)}<small>km</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">ANGULAR RATE</span>
                <span className="tp-val">{fmt(s?.target.angRateDegS, 3)}<small>°/s</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">TRANSVERSE V</span>
                <span className="tp-val">{fmt(s?.target.transverseKmS, 2)}<small>km/s</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">FOV LOCK</span>
                <span className="tp-val" style={{ color: s?.target.inFov ? 'var(--lock)' : 'var(--amber)' }}>
                  {s ? (s.target.inFov ? 'YES' : 'NO') : '—'}
                </span>
              </div>
            </div>
            <div className="tp-instrument">
              {s && <FieldMap s={s} />}
            </div>
          </div>
        </section>

        {/* Panel 2: Camera & Pan/Tilt Gimbal */}
        <section className="telemetry-panel gimbal-panel">
          <div className="tp-header">
            <div className="tp-title-group">
              <span className="tp-dot gimbal-dot" />
              <h4 className="tp-title">CAMERA · PAN/TILT GIMBAL</h4>
            </div>
            <div className="tp-badge badge-info">
              <span>{s?.mode === 'manual' ? 'MANUAL' : 'CLOSED LOOP'}</span>
            </div>
          </div>
          <div className="tp-body">
            <div className="tp-grid">
              <div className="tp-cell">
                <span className="tp-label">PAN (AZ)</span>
                <span className="tp-val">{fmt(s?.gimbal.pan, 3)}<small>°</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">TILT (EL)</span>
                <span className="tp-val">{fmt(s?.gimbal.tilt, 3)}<small>°</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">PAN RATE</span>
                <span className="tp-val">{fmtSigned(s?.gimbal.panRate, 3)}<small>°/s</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">TILT RATE</span>
                <span className="tp-val">{fmtSigned(s?.gimbal.tiltRate, 3)}<small>°/s</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">PIXEL ERROR</span>
                <span className="tp-val" style={{ color: s && (s.error.magPx ?? 99) < lockPx ? 'var(--lock)' : undefined }}>
                  {fmt(s?.error.magPx, 1)}<small>px</small>
                </span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">FOV DIM</span>
                <span className="tp-val">{s ? `${s.camera.hfovDeg.toFixed(2)}×${s.camera.vfovDeg.toFixed(2)}` : '—'}<small>°</small></span>
              </div>
            </div>
            <div className="tp-instrument">
              {s && <GimbalDial s={s} />}
            </div>
          </div>
        </section>

        {/* Panel 3: Optical Link Budget */}
        <section className="telemetry-panel link-panel">
          <div className="tp-header">
            <div className="tp-title-group">
              <span className="tp-dot link-dot" />
              <h4 className="tp-title">OPTICAL LINK BUDGET</h4>
            </div>
            <div className={`tp-badge ${s?.state === 'LOCKED' ? 'badge-active' : s?.state === 'TRACKING' ? 'badge-info' : 'badge-warn'}`}>
              <span>{s ? (s.state === 'LOCKED' ? 'LOCKED' : s.state === 'TRACKING' ? 'TRACKING' : 'ACQUIRING') : '—'}</span>
            </div>
          </div>
          <div className="tp-body">
            <div className="tp-grid">
              <div className="tp-cell">
                <span className="tp-label">LINK STATUS</span>
                <span className="tp-val" style={{ color: s ? stateColor(s.state) : undefined }}>
                  {s ? (s.state === 'LOCKED' ? 'Acquired' : s.state === 'TRACKING' ? 'Tracking' : 'Scanning') : '—'}
                </span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">FINE HAND-OVER</span>
                <span className="tp-val" style={{ color: s?.link.fineHandover ? 'var(--lock)' : undefined }}>
                  {s?.link.fineHandover ? 'READY' : 'NO'}
                </span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">RX POWER</span>
                <span className="tp-val">{fmt(s?.link.prDbm, 1)}<small>dBm</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">LINK MARGIN</span>
                <span className="tp-val" style={{ color: s && s.link.marginDb < 0 ? 'var(--lost)' : 'var(--lock)' }}>
                  {fmtSigned(s?.link.marginDb, 1)}<small>dB</small>
                </span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">P(ACQ ≤ 2 S)</span>
                <span className="tp-val">{s ? `${(s.link.pAcquire2s * 100).toFixed(0)}` : '—'}<small>%</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">LOCK RETENTION</span>
                <span className="tp-val">{fmt(s?.metrics.lockRetentionPct, 1)}<small>%</small></span>
              </div>
            </div>
            <div className="tp-instrument">
              {s && <AqsGauge s={s} />}
            </div>
          </div>
        </section>

        {/* Action Controls */}
        <section className="telemetry-actions-card">
          <button className={`tp-action-btn ${analysisOpen ? 'active' : ''}`} onClick={() => set({ analysisOpen: !analysisOpen })} title="Telemetry graphs & metrics (A)">
            <Icon name="analysis" size={15} />
            <span>Analysis</span>
          </button>
          <button className="tp-action-btn" onClick={() => useApp.getState().setDrawer('experiment')} title="Record, export, replay, batch experiments">
            <Icon name="experiment" size={15} />
            <span>Experiment</span>
          </button>
        </section>
      </div>
    </div>
  );
}
