import { useState } from 'react';
import { SCENARIO_PRESETS } from '../core/presets';
import { stateColor, useApp, ViewPreset } from '../state/store';
import { BrandMark, Icon, fmt, fmtClock } from './ui';
import { cameraApi } from '../scene/CameraRig';

export function TopBar() {
  const hud = useApp((s) => s.hud);
  const cfg = useApp((s) => s.config);
  const running = useApp((s) => s.running);
  const demo = useApp((s) => s.demo);
  const kind = useApp((s) => s.providerKind);
  const status = useApp((s) => s.providerStatus);
  const fps = useApp((s) => s.engineFps);
  const rec = useApp((s) => s.recording);
  const themeOpen = useApp((s) => s.themeOpen);
  const currentDrawer = useApp((s) => s.drawer);
  const { send, setDrawer, startRecording, stopRecording, set } = useApp.getState();
  const preset = SCENARIO_PRESETS.find((p) => p.id === cfg.scenarioId);
  const state = hud?.state ?? 'IDLE';
  const inState = hud ? hud.t - hud.stateSince : 0;
  const src = kind === 'local' ? 'Local engine' : kind === 'remote' ? 'FastAPI engine' : 'Replay';
  const isReplay = kind === 'replay';

  return (
    <header className="topbar">
      {/* Left: NETRA + scenario */}
      <div className="topbar-left">
        <div className="brand">
          <BrandMark />
          <div>
            <div className="brand-word">NETRA</div>
            <div className="brand-sub">Next-generation Emulation for Tracking & Real-time Alignment</div>
          </div>
        </div>
        <button className="chip" onClick={() => setDrawer('scenario')} title="Change scenario">
          <span className="dim">Scenario:</span> <b>{preset?.name ?? 'Open Sky'}</b>
        </button>
      </div>

      {/* Center: T+ + FPS */}
      <div className="topbar-center">
        <span className="chip mono" title="Mission elapsed time">
          T+ <b>{fmtClock(hud?.t ?? 0)}</b>
        </span>
        <span
          className="chip opt"
          title="Telemetry Engine & Connection Status (Click to reconnect or open Plugin Architecture)"
          onClick={() => {
            if (status !== 'online') {
              useApp.getState().connect('remote');
            } else {
              setDrawer(currentDrawer === 'plugin' ? null : 'plugin');
            }
          }}
          style={{ cursor: 'pointer' }}
        >
          <span
            className="dot"
            style={{
              color: status === 'online' ? 'var(--lock)' : status === 'error' ? 'var(--lost)' : 'var(--amber)',
              background: 'currentColor',
            }}
          />
          <b>{src}</b>
          <span className="mono dim">
            {status === 'online' ? `${fmt(fps, 0)} fps · ${fmt(hud?.procMs, 1)} ms` : status === 'error' ? 'RECONNECT ↻' : 'CONNECTING…'}
          </span>
        </span>
      </div>

      {/* Right: LOCKED + simulation controls */}
      <div className="topbar-right">
        <div
          className="state-badge"
          style={{ color: stateColor(state) }}
          title="Acquisition & tracking state (driven by the state machine)"
        >
          <span className="pulse" style={{ background: 'currentColor' }} />
          <span className="state-name">{state}</span>
          <span className="state-time">{inState.toFixed(1)} s</span>
        </div>
        <div className="topbar-controls">
          <button
            className="btn icon"
            onClick={() => send({ type: running ? 'pause' : 'start' })}
            title={running ? 'Pause (Space)' : 'Run (Space)'}
          >
            <Icon name={running ? 'pause' : 'play'} />
          </button>
          <button
            className="btn icon"
            onClick={() => send({ type: 'reset' })}
            title="Reset run — new random start (R)"
            disabled={isReplay}
          >
            <Icon name="reset" />
          </button>
          <button
            className={`btn rec ${rec.active ? 'on' : ''}`}
            onClick={() => (rec.active ? stopRecording() : startRecording())}
            title="Record telemetry for export / replay"
          >
            <span className="led" />
            {rec.active ? `REC ${(rec.frames / 30).toFixed(0)} s` : 'Record'}
          </button>
          <button
            className="btn primary"
            onClick={() => send({ type: 'demo', on: !demo })}
            disabled={isReplay}
            title="90 s guided demonstration (D)"
          >
            {demo ? 'End demo' : 'Run demo'}
          </button>
          <button
            className={`btn icon ghost ${themeOpen ? 'on' : ''}`}
            onClick={() => set({ themeOpen: !themeOpen })}
            title="Interface Themes (T)"
            aria-label="Themes"
          >
            <Icon name="palette" />
          </button>
          <button
            className="btn icon ghost"
            onClick={() => set({ helpOpen: true })}
            title="What am I looking at? (?)"
          >
            <Icon name="help" />
          </button>
        </div>
      </div>
    </header>
  );
}

const VIEWS: { v: ViewPreset; name: string; key: string; hint: string }[] = [
  { v: 'overview', name: 'Overview', key: '1', hint: 'Global Stage' },
  { v: 'terminal', name: 'Terminal', key: '2', hint: 'Ground OGS' },
  { v: 'link', name: 'Sat 3D', key: '3', hint: 'FSOC Spacecraft' },
  { v: 'sensor', name: 'POV', key: '4', hint: 'Camera Boresight' },
  { v: 'orbit', name: 'Orbit', key: '5', hint: 'Track Plane' },
];

export function ViewSwitch() {
  const view = useApp((s) => s.view);
  const setView = useApp((s) => s.setView);
  const activeView = VIEWS.find((x) => x.v === view) ?? { name: 'Free', key: '0', hint: 'Orbit' };
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className={`viewswitch-bar glass ${collapsed ? 'collapsed' : ''}`} aria-label="Camera sightline presets">
      <div 
        className="vs-bar-head" 
        onClick={() => setCollapsed(!collapsed)} 
        style={{ cursor: 'pointer', userSelect: 'none' }}
        title={collapsed ? 'Expand Sightline Presets' : 'Collapse Sightline Presets'}
      >
        <Icon name="crosshair" size={13} />
        <span className="vs-bar-title">SIGHTLINE</span>
        <div className="vs-active-pill">
          <span className="vs-live-dot" />
          <span>{activeView.name.toUpperCase()}</span>
          <span style={{ fontSize: 9, opacity: 0.6, marginLeft: 2 }}>{collapsed ? '▼' : '▲'}</span>
        </div>
      </div>

      {!collapsed && (
        <div className="vs-bar-body">
          <div className="vs-bar-divider" />
          <div className="vs-bar-btns">
            {VIEWS.map((v) => {
              const isSel = view === v.v;
              return (
                <button
                  key={v.v}
                  className={`vs-card-btn ${isSel ? 'on' : ''}`}
                  onClick={() => setView(v.v)}
                  title={`${v.name} (${v.key}) — ${v.hint}`}
                >
                  <span className="vs-btn-title">{v.name}</span>
                  <kbd className="vs-kbd">{v.key}</kbd>
                </button>
              );
            })}

            <button
              className="vs-card-btn vs-reset-btn"
              onClick={() => {
                setView('overview');
                cameraApi.zoom(1);
              }}
              title="Reset to default overview angle (R)"
            >
              <span className="vs-btn-title">Reset</span>
              <kbd className="vs-kbd">R</kbd>
            </button>
          </div>

          <div className="vs-bar-divider" />

          <div className="vs-zoom-controls">
            <button className="vs-zoom-act" onClick={() => cameraApi.zoom(1.6)} title="Zoom out (−)" aria-label="Zoom out">
              <Icon name="minus" size={11} />
            </button>
            <button className="vs-zoom-act" onClick={() => cameraApi.zoom(0.62)} title="Zoom in (+)" aria-label="Zoom in">
              <Icon name="plus" size={11} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function DemoCaption() {
  const demo = useApp((s) => s.hud?.demo);
  if (!demo) return null;
  return (
    <div className="caption glass">
      <div className="eyebrow">
        Demonstration · phase {demo.phase + 1} / {demo.phases}
      </div>
      <div className="title">{demo.title}</div>
      <p>{demo.caption}</p>
      <div className="prog">
        <i style={{ width: `${demo.progress * 100}%` }} />
      </div>
    </div>
  );
}

export function ReplayBar() {
  const replay = useApp((s) => s.replay);
  const running = useApp((s) => s.running);
  const { send, seekReplay, connect } = useApp.getState();
  if (!replay) return null;
  return (
    <div className="replaybar glass">
      <span className="tag sim">Replay</span>
      <button className="btn icon sm" onClick={() => send({ type: running ? 'pause' : 'start' })}>
        <Icon name={running ? 'pause' : 'play'} size={15} />
      </button>
      <input type="range" min={0} max={Math.max(1, replay.length - 1)} value={replay.position} onChange={(e) => seekReplay(parseInt(e.target.value, 10))} />
      <span className="mono dim" style={{ fontSize: 11 }}>
        {replay.position + 1}/{replay.length}
      </span>
      <button className="btn sm" onClick={() => connect('local')}>
        Exit replay
      </button>
    </div>
  );
}

export function Toast() {
  const toast = useApp((s) => s.toast);
  if (!toast) return null;
  return <div className="toast glass">{toast}</div>;
}
