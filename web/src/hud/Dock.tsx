/**
 * Bottom dock: the coarse-alignment chain (the loop, left to right, with live values)
 * and the three readout groups TARGET · CAMERA/GIMBAL · LINK.
 */
import { useEffect, useRef } from 'react';
import { history, historySlice, live, useApp } from '../state/store';
import type { Snapshot, TrackState } from '../core/telemetry/types';
import { cssVar, fmt, fmtSigned } from './ui';
import { Chart, TABS } from './Analysis';

const ACTIVE: Record<TrackState, number> = {
  IDLE: 0,
  SEARCHING: 0,
  DETECTED: 2,
  ACQUIRING: 4,
  TRACKING: 5,
  LOCKED: 5,
  LOST: 3,
  REACQUIRING: 3,
};

function Spark({ isLocked = false }: { isLocked?: boolean }) {
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
      const w = (c.width = 240);
      const h = (c.height = 40);
      const ctx = c.getContext('2d')!;
      ctx.clearRect(0, 0, w, h);
      const { v } = historySlice('errPx', 16);
      const max = 60;
      const y = (e: number) => h - 2 - (Math.log10(1 + Math.min(max, e)) / Math.log10(1 + max)) * (h - 4);
      
      // Lock threshold line
      ctx.strokeStyle = (cssVar('--lock') || '#2DD36F') + '66';
      ctx.setLineDash([2, 3]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, y(lockPx));
      ctx.lineTo(w, y(lockPx));
      ctx.stroke();
      ctx.setLineDash([]);

      // Error curve - transitions to theme lock color when locked
      const lockCol = cssVar('--lock') || '#2DD36F';
      const serACol = cssVar('--ser-a') || '#FF8C1A';
      ctx.strokeStyle = isLocked ? lockCol : serACol;
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
        if (isLocked) {
          grad.addColorStop(0, lockCol + '47');
          grad.addColorStop(1, lockCol + '00');
        } else {
          grad.addColorStop(0, serACol + '38');
          grad.addColorStop(1, serACol + '00');
        }
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
  }, [lockPx, isLocked]);
  return <canvas ref={ref} className="chain-spark" />;
}

import type { ReactNode } from 'react';

interface ChainNode {
  k: string;
  v: ReactNode;
  s: ReactNode;
  spark?: boolean;
  isLockNode?: boolean;
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

  const nodes: ChainNode[] = [
    {
      k: 'INITIAL ERROR',
      v: live.initialErrPx ? <>{fmt(live.initialErrPx, 0)}<small>px</small></> : '—',
      s: 'Acquisition T₀',
    },
    {
      k: 'DETECTION',
      v: d ? <>{(d.confidence * 100).toFixed(1)}<small>%</small></> : s?.state === 'SEARCHING' ? 'Scanning' : '—',
      s: d ? <>Centroid ({d.x.toFixed(0)}, {d.y.toFixed(0)})<small>px</small></> : 'Centroid Fix',
    },
    {
      k: 'ERROR ESTIMATE',
      v: ex !== null && ey !== null ? (
        <span className="mono-subgrid">
          <span>ΔX {fmtSigned(ex, 1)}</span>
          <span className="dot-sep">·</span>
          <span>ΔY {fmtSigned(ey, 1)}</span>
        </span>
      ) : '—',
      s: ex !== null && ey !== null ? <>{(Math.hypot(ex, ey) * ifov).toFixed(3)}° · Kalman KF</> : 'State Est.',
    },
    {
      k: 'PAN-TILT / GIMBAL',
      v: s ? (
        <span className="mono-subgrid">
          <span>Az {s.gimbal.pan.toFixed(1)}°</span>
          <span className="dot-sep">·</span>
          <span>El {s.gimbal.tilt.toFixed(1)}°</span>
        </span>
      ) : '—',
      s: s ? <>Rate: {fmtSigned(s.gimbal.panCmd, 2)}, {fmtSigned(s.gimbal.tiltCmd, 2)}<small>°/s</small></> : 'PID + Encoders',
    },
    {
      k: 'PIXEL ERROR',
      v: <>{fmt(s?.error.magPx, 1)}<small>px</small></>,
      s: isLocked ? 'Optical Lock' : isTracking ? 'Tracking Active' : 'Realtime Trace',
      spark: true,
      isLockNode: true,
    },
  ];

  return (
    <div className="chain-container" aria-label="Tracking loop pipeline">
      <div className="chain-stream">
        {nodes.map((node, i) => {
          const isActive = i < n;
          const isHot = i === n - 1;
          const isConnectorLocked = isLocked && i === nodes.length - 2;
          return (
            <div key={node.k} className="chain-segment">
              <div
                className={`chain-card ${isActive ? 'active' : ''} ${isHot ? 'hot' : ''} ${node.isLockNode ? (isLocked ? 'locked-card' : 'acquiring-card') : ''}`}
              >
                <div className="chain-card-top">
                  <span className="chain-label">{node.k}</span>
                </div>
                <div
                  className="chain-val"
                  style={
                    node.isLockNode && isLocked
                      ? { color: 'var(--lock)' }
                      : coasting && i >= 2 && i <= 3
                      ? { color: 'var(--warn)' }
                      : undefined
                  }
                >
                  <span className="chain-val-inner">{node.v}</span>
                  {node.isLockNode && isLocked && (
                    <span className="chain-lock-badge">LOCKED</span>
                  )}
                </div>
                {node.spark ? <Spark isLocked={isLocked} /> : <div className="chain-sub">{node.s}</div>}
              </div>
              {i < nodes.length - 1 && (
                <div className={`chain-connector ${i < n - 1 ? 'flowing' : ''} ${isConnectorLocked ? 'flowing-lock' : ''}`}>
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

export function Dock() {
  const s = useApp((st) => st.hud);
  const set = useApp((st) => st.set);
  const lockPx = useApp((st) => st.config.logic.lockPx);
  const analysisTab = useApp((st) => st.analysisTab);
  const m = s?.metrics;
  const currentTab = TABS.find((t) => t.id === analysisTab) ?? TABS[0];

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
              <span className="tp-badge-dot" />
              <span>{s?.target.inFov ? 'IN FOV' : 'OUT OF FOV'}</span>
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
                <span className="tp-label">SLEW RATE</span>
                <span className="tp-val">{fmt(s?.target.angRateDegS, 3)}<small>°/s</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">TRANS. VEL</span>
                <span className="tp-val">{fmt(s?.target.transverseKmS, 2)}<small>km/s</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">FOV STATUS</span>
                <span className="tp-val">
                  {s?.target.inFov ? (
                    <span className="tp-status-pill locked"><span className="tp-status-dot" />LOCKED</span>
                  ) : (
                    <span className="tp-status-pill search"><span className="tp-status-dot" />ACQ SCAN</span>
                  )}
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* Panel 2: Error Analysis & Key Metrics */}
        <section className="telemetry-panel analysis-opt-panel">
          <div className="tp-header">
            <div className="tp-title-group">
              <span className="tp-dot analysis-dot" />
              <h4 className="tp-title">ERROR ANALYSIS</h4>
            </div>
            <div className="tp-badge badge-active">
              <span className="tp-badge-dot" />
              <span>RMS {fmt(m?.errRmsPx, 2)} px</span>
            </div>
          </div>
          <div className="tp-body">
            {/* Key Error Metrics */}
            <div className="tp-grid analysis-metrics-grid">
              <div className="tp-cell">
                <span className="tp-label">RMS ERROR</span>
                <span className="tp-val" style={{ color: (m?.errRmsPx ?? 99) < lockPx ? 'var(--lock)' : undefined }}>
                  {fmt(m?.errRmsPx, 2)}<small>px</small>
                </span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">MEAN ERROR</span>
                <span className="tp-val">{fmt(m?.errMeanPx, 2)}<small>px</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">MAX ERROR</span>
                <span className="tp-val">{fmt(m?.errMaxPx, 2)}<small>px</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">P95 ERROR</span>
                <span className="tp-val">{fmt(m?.errP95Px, 2)}<small>px</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">CENTROID RMS</span>
                <span className="tp-val">{fmt(m?.centroidRmsPx, 2)}<small>px</small></span>
              </div>
              <div className="tp-cell">
                <span className="tp-label">LOCK RETENTION</span>
                <span className="tp-val" style={{ color: (m?.lockRetentionPct ?? 0) >= 95 ? 'var(--lock)' : undefined }}>
                  {fmt(m?.lockRetentionPct, 1)}<small>%</small>
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* Panel 3: Live Interactive Telemetry Chart */}
        <section className="telemetry-panel analysis-chart-panel">
          <div className="tp-header">
            <div className="tp-title-group">
              <span className="tp-dot chart-dot" />
              <h4 className="tp-title">LIVE CHART · {currentTab.label.toUpperCase()}</h4>
            </div>
            <div className="chart-legend-inline">
              {currentTab.series.map((ser) => (
                <span key={ser.key} className="chart-leg-item">
                  <i style={{ background: cssVar(ser.color) }} />
                  <span>{ser.label}</span>
                </span>
              ))}
              {currentTab.threshold && (
                <span className="chart-leg-item thr">
                  <i style={{ background: 'var(--lock)' }} />
                  <span>Lock ≤ {currentTab.unit === 'px' ? `${lockPx} px` : `${(lockPx * (s?.camera.ifovDeg ?? 0.00625)).toFixed(3)}°`}</span>
                </span>
              )}
            </div>
          </div>
          {/* Chart Selection Tabs: all 6 horizontal on top of graph */}
          <div className="analysis-tabs-row chart-tabs-bar" role="tablist" aria-label="Telemetry Chart Selection">
            {TABS.map((t) => {
              const label = t.id === 'rates' ? 'PAN / TILT' : t.label.toUpperCase();
              return (
                <button
                  key={t.id}
                  className={`analysis-tab-chip ${currentTab.id === t.id ? 'active' : ''}`}
                  onClick={() => set({ analysisTab: t.id })}
                  title={t.label}
                  role="tab"
                  aria-selected={currentTab.id === t.id}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <div className="tp-body chart-panel-body">
            <div className="tp-chart-canvas-wrap">
              <Chart tab={currentTab} compact />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
