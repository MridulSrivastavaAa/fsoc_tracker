/** "What am I looking at" help overlay. */
import { useApp } from '../state/store';
import { Icon } from './ui';

export function Help() {
  const open = useApp((s) => s.helpOpen);
  const set = useApp((s) => s.set);
  if (!open) return null;
  return (
    <div className="help" onClick={() => set({ helpOpen: false })}>
      <div className="help-card glass" onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div>
            <h2>NETRA</h2>
            <div className="muted">Autonomous Spatial Tracking &amp; Alignment for Optical Links — coarse pointing of a mobile free-space optical terminal.</div>
          </div>
          <button className="btn icon ghost" onClick={() => set({ helpOpen: false })}>
            <Icon name="close" />
          </button>
        </div>
        <div className="help-grid">
          <div>
            <h5>What you are looking at</h5>
            <ol>
              <li>A <b>mobile ground terminal</b> carries a telescope camera on a pan/tilt gimbal.</li>
              <li>A <b>remote terminal</b> (here a LEO spacecraft) shines an <b>optical beacon</b> toward it.</li>
              <li>The <b>camera</b> images the sky; the frame at top right is exactly what it records.</li>
              <li>The <b>detector</b> finds the beacon spot and measures its pixel offset from the image centre.</li>
              <li>A <b>Kalman filter</b> estimates where the beacon is going; a <b>PID</b> commands pan and tilt rates.</li>
              <li>When the error stays under 10 px the terminal is <b>LOCKED</b> — coarse alignment is done and a fine-pointing stage could take over the <b>optical link</b>.</li>
            </ol>
          </div>
          <div>
            <h5>Legend</h5>
            <ul style={{ listStyle: 'none', padding: 0 }}>
              <li>
                <span className="legend-sw" style={{ background: 'var(--amber)' }} />
                Searching / acquiring · search field · scan path
              </li>
              <li>
                <span className="legend-sw" style={{ background: 'var(--ice)' }} />
                Tracking · camera FOV frustum · beacon trajectory
              </li>
              <li>
                <span className="legend-sw" style={{ background: 'var(--lock)' }} />
                Locked · optical link (pulses = data)
              </li>
              <li>
                <span className="legend-sw" style={{ background: 'var(--lost)' }} />
                Lost — coasting on the Kalman prediction
              </li>
              <li>
                <span className="legend-sw" style={{ background: 'var(--amber-hi)' }} />
                Kalman estimate (diamond) and its 3σ ellipse
              </li>
            </ul>
            <p style={{ marginTop: 8 }}>Distances and directions are true (km). The terminal and spacecraft are enlarged when far away, the Moon is ×3 and the beacon cone is widened for visibility.</p>
          </div>
          <div>
            <h5>What is real and what is not</h5>
            <ul>
              <li>Real: camera projection, rendered sensor image, image detector, Kalman filter, PID, gimbal limits, state machine, disturbances, metrics, recording, video benchmark.</li>
              <li>AI: a trained neural network (learned beacon verifier) scores every detected blob; switch it off in Tracking to compare.</li>
              <li>Simplified: link budget, acquisition probability, atmosphere model.</li>
              <li>Synthetic detector = a statistical model (clearly labelled).</li>
              <li>YOLO detection and hardware cameras are <b>planned</b>, not implemented.</li>
            </ul>
          </div>
          <div>
            <h5>Keyboard</h5>
            <ul>
              <li>
                <span className="mono">Space</span> run / pause · <span className="mono">R</span> reset · <span className="mono">D</span> demo
              </li>
              <li>
                <span className="mono">1–5</span> views · <span className="mono">S</span> sensor · <span className="mono">A</span> analysis · <span className="mono">M</span> manual mode
              </li>
              <li>
                <span className="mono">←↑→↓</span> jog the gimbal in manual mode (Shift ×10) · <span className="mono">?</span> this help
              </li>
              <li>
                <span className="mono">+ / −</span> zoom (the mouse wheel zooms towards the cursor) · <span className="mono">G</span> 2000² screen view
              </li>
              <li>
                <span className="mono">V</span> video benchmark · <span className="mono">P</span> performance report · <span className="mono">T</span> theme
              </li>
              <li>
                <span className="mono">F</span> fly to SAT-3 relay spacecraft · <span className="mono">1</span> back to overview
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
