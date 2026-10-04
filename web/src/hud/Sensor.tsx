/**
 * Optical sensor feed: the actual 8-bit frame rendered by the engine and processed by
 * the detector, with measurement overlays. Nothing here is decorative imagery.
 */
import { useEffect, useRef } from 'react';
import { live, stateColor, STATE_HEX, useApp } from '../state/store';
import type { Snapshot, TrackState } from '../core/telemetry/types';
import { Icon, fmt, fmtSigned } from './ui';

const STEPS: { key: keyof Snapshot['timeline']; label: string; states: TrackState[] }[] = [
  { key: 'search', label: 'SEARCH', states: ['SEARCHING', 'REACQUIRING'] },
  { key: 'detect', label: 'DETECT', states: ['DETECTED'] },
  { key: 'acquire', label: 'ACQUIRE', states: ['ACQUIRING'] },
  { key: 'track', label: 'TRACK', states: ['TRACKING', 'LOST'] },
  { key: 'lock', label: 'LOCK', states: ['LOCKED'] },
];

function drawOverlay(ctx: CanvasRenderingContext2D, s: Snapshot, W: number, H: number, sc: number, opts: { truth: boolean; calibration: boolean; roi: boolean; lockPx: number; acqPx: number }) {
  const cw = s.camera.width;
  const ch = s.camera.height;
  const cx = cw / 2;
  const cy = ch / 2;
  const X = (x: number) => x * sc;
  const Y = (y: number) => y * sc;
  const col = STATE_HEX[s.state];
  ctx.lineWidth = 1;
  ctx.font = `${Math.max(10, 10.5 * Math.min(1.4, sc))}px "IBM Plex Mono", monospace`;
  ctx.textBaseline = 'top';

  // Calibration grid: gnomonic degree lines from the camera model (x = cx + fx·tan u).
  if (opts.calibration) {
    ctx.strokeStyle = 'rgba(143,220,255,0.18)';
    ctx.fillStyle = 'rgba(143,220,255,0.55)';
    const stepDeg = s.camera.hfovDeg > 8 ? 2 : 0.5;
    for (let k = -40; k <= 40; k++) {
      const a = (k * stepDeg * Math.PI) / 180;
      const x = cx + s.camera.fx * Math.tan(a);
      const y = cy - s.camera.fx * Math.tan(a);
      if (x > 0 && x < cw) {
        ctx.beginPath();
        ctx.moveTo(X(x), 0);
        ctx.lineTo(X(x), H);
        ctx.stroke();
        if (k !== 0) ctx.fillText(`${(k * stepDeg).toFixed(1)}°`, X(x) + 3, H - 40);
      }
      if (y > 0 && y < ch) {
        ctx.beginPath();
        ctx.moveTo(0, Y(y));
        ctx.lineTo(W, Y(y));
        ctx.stroke();
      }
    }
    ctx.fillText(`principal point (${cx}, ${cy}) · f = ${s.camera.fx.toFixed(0)} px`, 8, 24);
  }

  // Reticle: centre cross with gap, corner brackets, lock + acquisition circles.
  ctx.strokeStyle = 'rgba(232,240,247,0.55)';
  const g = 6;
  const L = 18;
  ctx.beginPath();
  ctx.moveTo(X(cx) - L - g, Y(cy));
  ctx.lineTo(X(cx) - g, Y(cy));
  ctx.moveTo(X(cx) + g, Y(cy));
  ctx.lineTo(X(cx) + L + g, Y(cy));
  ctx.moveTo(X(cx), Y(cy) - L - g);
  ctx.lineTo(X(cx), Y(cy) - g);
  ctx.moveTo(X(cx), Y(cy) + g);
  ctx.lineTo(X(cx), Y(cy) + L + g);
  ctx.stroke();
  const m = 14;
  const b = 22;
  ctx.strokeStyle = 'rgba(232,240,247,0.35)';
  for (const [sx, sy] of [
    [0, 0],
    [1, 0],
    [0, 1],
    [1, 1],
  ]) {
    const x0 = sx ? W - m : m;
    const y0 = sy ? H - m : m;
    ctx.beginPath();
    ctx.moveTo(x0 + (sx ? -b : b), y0);
    ctx.lineTo(x0, y0);
    ctx.lineTo(x0, y0 + (sy ? -b : b));
    ctx.stroke();
  }
  ctx.strokeStyle = s.state === 'LOCKED' ? 'rgba(156,245,200,0.85)' : 'rgba(156,245,200,0.4)';
  ctx.beginPath();
  ctx.arc(X(cx), Y(cy), opts.lockPx * sc, 0, Math.PI * 2);
  ctx.stroke();
  ctx.setLineDash([3, 4]);
  ctx.strokeStyle = 'rgba(232,240,247,0.22)';
  ctx.beginPath();
  ctx.arc(X(cx), Y(cy), opts.acqPx * sc, 0, Math.PI * 2);
  ctx.stroke();

  // ROI
  if (opts.roi && s.roi && (s.roi[2] - s.roi[0] < cw - 2 || s.roi[3] - s.roi[1] < ch - 2)) {
    ctx.strokeStyle = 'rgba(143,220,255,0.35)';
    ctx.strokeRect(X(s.roi[0]), Y(s.roi[1]), X(s.roi[2] - s.roi[0]), Y(s.roi[3] - s.roi[1]));
    ctx.fillStyle = 'rgba(143,220,255,0.55)';
    ctx.fillText('ROI', X(s.roi[0]) + 3, Y(s.roi[1]) + 3);
  }
  ctx.setLineDash([]);

  // Other candidates (rejected blobs).
  ctx.strokeStyle = 'rgba(255,208,138,0.35)';
  for (const c of s.candidates.slice(1)) {
    ctx.beginPath();
    ctx.arc(X(c.x), Y(c.y), 6, 0, Math.PI * 2);
    ctx.stroke();
  }

  // Kalman prediction + 3σ ellipse.
  if (s.kalman.predPx) {
    const [px, py] = s.kalman.predPx;
    ctx.strokeStyle = 'rgba(255,208,138,0.75)';
    ctx.beginPath();
    ctx.moveTo(X(px), Y(py) - 6);
    ctx.lineTo(X(px) + 6, Y(py));
    ctx.lineTo(X(px), Y(py) + 6);
    ctx.lineTo(X(px) - 6, Y(py));
    ctx.closePath();
    ctx.stroke();
    const [sx, sy] = s.kalman.sigmaPx;
    if (sx > 0.3 && sy > 0.3) {
      ctx.setLineDash([2, 3]);
      ctx.beginPath();
      ctx.ellipse(X(px), Y(py), Math.min(3 * sx * sc, W), Math.min(3 * sy * sc, H), 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  // Ground truth (simulation only; off by default).
  if (opts.truth && s.target.truthPx) {
    ctx.strokeStyle = 'rgba(255,255,255,0.8)';
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.arc(X(s.target.truthPx[0]), Y(s.target.truthPx[1]), 9, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = 'rgba(255,255,255,0.8)';
    ctx.fillText('truth (sim)', X(s.target.truthPx[0]) + 12, Y(s.target.truthPx[1]) - 14);
  }

  // Detection: bbox corners, centroid, error vector.
  const d = s.detection;
  if (d) {
    const dc = d.accepted ? col : 'rgba(255,107,94,0.9)';
    const [x0, y0, x1, y1] = d.bbox;
    const pad = 4;
    const bx0 = X(x0) - pad;
    const by0 = Y(y0) - pad;
    const bx1 = X(x1 + 1) + pad;
    const by1 = Y(y1 + 1) + pad;
    const k = Math.min(9, (bx1 - bx0) / 3);
    ctx.strokeStyle = dc;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (const [ax, ay, dx, dy] of [
      [bx0, by0, 1, 1],
      [bx1, by0, -1, 1],
      [bx0, by1, 1, -1],
      [bx1, by1, -1, -1],
    ]) {
      ctx.moveTo(ax + dx * k, ay);
      ctx.lineTo(ax, ay);
      ctx.lineTo(ax, ay + dy * k);
    }
    ctx.stroke();
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(X(d.x) - 4, Y(d.y));
    ctx.lineTo(X(d.x) + 4, Y(d.y));
    ctx.moveTo(X(d.x), Y(d.y) - 4);
    ctx.lineTo(X(d.x), Y(d.y) + 4);
    ctx.stroke();
    // error vector from the image centre
    ctx.strokeStyle = 'rgba(255,181,71,0.8)';
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(X(cx), Y(cy));
    ctx.lineTo(X(d.x), Y(d.y));
    ctx.stroke();
    ctx.setLineDash([]);
    const ex = d.x - cx;
    const ey = d.y - cy;
    ctx.fillStyle = dc;
    const lx = Math.min(W - 170, bx1 + 6);
    const ly = Math.max(4, by0 - 2);
    ctx.fillText(`DET (${d.x.toFixed(1)}, ${d.y.toFixed(1)})`, lx, ly);
    ctx.fillStyle = 'rgba(232,240,247,0.85)';
    ctx.fillText(`Δ (${fmtSigned(ex)}, ${fmtSigned(ey)}) px`, lx, ly + 14);
    ctx.fillText(`${(d.confidence * 100).toFixed(0)} % · SNR ${d.snr.toFixed(0)}`, lx, ly + 28);
  }

  // Text frame.
  ctx.fillStyle = 'rgba(232,240,247,0.75)';
  ctx.fillText(`FSOC-CAM · ${cw}×${ch} · MONO 8-bit`, 8, 8);
  ctx.textAlign = 'right';
  ctx.fillStyle = col;
  ctx.fillText(s.state, W - 8, 8);
  ctx.fillStyle = 'rgba(232,240,247,0.6)';
  ctx.fillText(`centre (${cx}, ${cy})`, W - 8, 22);
  ctx.textBaseline = 'bottom';
  ctx.fillText(`frame ${s.frame} · t ${s.t.toFixed(2)} s`, W - 8, H - 6);
  ctx.textAlign = 'left';
  ctx.fillText(`FOV ${s.camera.hfovDeg.toFixed(2)}° × ${s.camera.vfovDeg.toFixed(2)}°`, 8, H - 6);
  ctx.textBaseline = 'top';
}

/**
 * The problem statement's own picture: a 2000 × 2000 px "screen" (the search field at
 * 0.00625 °/px) with the camera's 640 × 480 viewport moving over it.
 */
function ScreenCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);
  const cfg = useApp((s) => s.config);
  const cfgRef = useRef(cfg);
  cfgRef.current = cfg;
  useEffect(() => {
    let raf = 0;
    let last = -1;
    const trail: [number, number][] = [];
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const c = ref.current;
      const s = live.snap;
      if (!c || !s || s.frame === last) return;
      if (s.frame < last) {
        trail.length = 0;
      }
      last = s.frame;
      const conf = cfgRef.current;
      const ifov = conf.camera.hfovDeg / conf.camera.width;
      const halfPx = conf.logic.searchHalfUDeg / ifov;
      const N = Math.round(2 * halfPx);
      const toPx = (u: number, v: number): [number, number] => [halfPx + u / ifov, halfPx - v / ifov];
      const rawU = Number.isFinite(s.gimbal?.boresightU)
        ? s.gimbal.boresightU
        : Number.isFinite(s.gimbal?.pan)
        ? s.gimbal.pan
        : 0;
      const rawV = Number.isFinite(s.gimbal?.boresightV)
        ? s.gimbal.boresightV
        : Number.isFinite(s.gimbal?.tilt)
        ? s.gimbal.tilt
        : 0;
      // Robust angle handling in case backend emitted pixels or degrees
      const parseU = (val: number) => (Math.abs(val) > 50 ? (val - halfPx) * ifov : val);
      const parseV = (val: number) => (Math.abs(val) > 50 ? (halfPx - val) * ifov : val);
      const safeBu = parseU(rawU);
      const safeBv = parseV(rawV);
      trail.push(toPx(s.target.u, s.target.v));
      if (trail.length > 30 * 12) trail.shift();
      const rect = c.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const W = Math.round(rect.width * dpr);
      const H = Math.round(rect.height * dpr);
      if (c.width !== W || c.height !== H) {
        c.width = W;
        c.height = H;
      }
      const ctx = c.getContext('2d')!;
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, W, H);
      const padL = 34 * dpr;
      const padR = 12 * dpr;
      const padT = 18 * dpr;
      const padB = 14 * dpr;
      const side = Math.floor(Math.min(H - padT - padB, W - padL - padR));
      const ox = Math.floor(padL + (W - padL - padR - side) / 2);
      const oy = padT;
      const k = side / N;
      const X = (p: number) => ox + p * k;
      const Y = (p: number) => oy + p * k;
      ctx.fillStyle = '#04080e';
      ctx.fillRect(ox, oy, side, side);
      ctx.strokeStyle = 'rgba(170,214,255,0.07)';
      ctx.lineWidth = 1;
      ctx.font = `${9 * dpr}px "IBM Plex Mono", monospace`;
      ctx.fillStyle = 'rgba(170,214,255,0.45)';
      for (let p = 0; p <= N; p += 250) {
        ctx.beginPath();
        ctx.moveTo(X(p), oy);
        ctx.lineTo(X(p), oy + side);
        ctx.moveTo(ox, Y(p));
        ctx.lineTo(ox + side, Y(p));
        ctx.stroke();
      }
      ctx.textAlign = 'right';
      for (let p = 0; p <= N; p += 500) ctx.fillText(String(p), ox - 4 * dpr, Y(p) + 3 * dpr);
      ctx.textAlign = 'left';
      ctx.strokeRect(ox, oy, side, side);

      // Dedicated screen title pill above grid (never collides with inside content)
      const drawPill = (x: number, y: number, w: number, h: number, r: number) => {
        ctx.beginPath();
        if ((ctx as any).roundRect) (ctx as any).roundRect(x, y, w, h, r);
        else ctx.rect(x, y, w, h);
      };

      const tagText = `SCREEN ${N}×${N} px · ${ifov.toFixed(5)}°/px`;
      ctx.font = `600 ${8.5 * dpr}px "IBM Plex Mono", monospace`;
      const tagW = ctx.measureText(tagText).width + 12 * dpr;
      const tagH = 15 * dpr;
      const tagY = Math.max(2 * dpr, oy - 16 * dpr);

      ctx.fillStyle = 'rgba(10, 16, 26, 0.88)';
      drawPill(ox, tagY, tagW, tagH, 3 * dpr);
      ctx.fill();
      ctx.strokeStyle = 'rgba(170,214,255,0.22)';
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.fillStyle = 'rgba(215, 235, 255, 0.9)';
      ctx.fillText(tagText, ox + 6 * dpr, tagY + 11 * dpr);
      // Beacon trail (strictly the red beacon trajectory)
      ctx.strokeStyle = 'rgba(255, 68, 68, 0.85)';
      ctx.lineWidth = 1.5 * dpr;
      ctx.beginPath();
      trail.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))));
      ctx.stroke();
      // Camera viewport (640 × 480 at 4°, wider during wide-field search).
      const [bx, by] = toPx(safeBu, safeBv);
      const vw = s.camera.hfovDeg / ifov;
      const vh = s.camera.vfovDeg / ifov;
      const col = STATE_HEX[s.state] || '#38bdf8';
      const boxLeft = X(bx - vw / 2);
      const boxTop = Y(by - vh / 2);
      const boxW = vw * k;
      const boxH = vh * k;

      // Glow fill for camera viewport
      ctx.fillStyle = col + '22';
      ctx.fillRect(boxLeft, boxTop, boxW, boxH);
      
      // Main camera frame boundary
      ctx.strokeStyle = col;
      ctx.lineWidth = 2 * dpr;
      ctx.strokeRect(boxLeft, boxTop, boxW, boxH);

      // Corner accent brackets to highlight camera tracking frame
      const cornerLen = Math.min(14 * dpr, boxW * 0.18);
      ctx.lineWidth = 3.5 * dpr;
      ctx.beginPath();
      // Top-left
      ctx.moveTo(boxLeft, boxTop + cornerLen);
      ctx.lineTo(boxLeft, boxTop);
      ctx.lineTo(boxLeft + cornerLen, boxTop);
      // Top-right
      ctx.moveTo(boxLeft + boxW - cornerLen, boxTop);
      ctx.lineTo(boxLeft + boxW, boxTop);
      ctx.lineTo(boxLeft + boxW, boxTop + cornerLen);
      // Bottom-left
      ctx.moveTo(boxLeft, boxTop + boxH - cornerLen);
      ctx.lineTo(boxLeft, boxTop + boxH);
      ctx.lineTo(boxLeft + cornerLen, boxTop + boxH);
      // Bottom-right
      ctx.moveTo(boxLeft + boxW - cornerLen, boxTop + boxH);
      ctx.lineTo(boxLeft + boxW, boxTop + boxH);
      ctx.lineTo(boxLeft + boxW, boxTop + boxH - cornerLen);
      ctx.stroke();

      // Optical boresight crosshair + center ring
      ctx.lineWidth = 1.5 * dpr;
      ctx.beginPath();
      ctx.moveTo(X(bx) - 7 * dpr, Y(by));
      ctx.lineTo(X(bx) + 7 * dpr, Y(by));
      ctx.moveTo(X(bx), Y(by) - 7 * dpr);
      ctx.lineTo(X(bx), Y(by) + 7 * dpr);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(X(bx), Y(by), 3 * dpr, 0, Math.PI * 2);
      ctx.stroke();

      // Viewport Label with dedicated dark glass pill to prevent text collisions
      const camText = `CAM FOV ${Math.round(vw)}×${Math.round(vh)}`;
      ctx.font = `700 ${8.5 * dpr}px "IBM Plex Mono", monospace`;
      const camW = ctx.measureText(camText).width + 10 * dpr;
      const camH = 14 * dpr;
      const camX = Math.max(ox + 3 * dpr, Math.min(ox + side - camW - 3 * dpr, boxLeft + 3 * dpr));
      const camY = boxTop > oy + 18 * dpr ? boxTop - 16 * dpr : boxTop + 4 * dpr;

      ctx.fillStyle = 'rgba(7, 12, 20, 0.92)';
      drawPill(camX, camY, camW, camH, 3 * dpr);
      ctx.fill();
      ctx.strokeStyle = col;
      ctx.lineWidth = 1 * dpr;
      ctx.stroke();

      ctx.fillStyle = col;
      ctx.fillText(camText, camX + 5 * dpr, camY + 10.5 * dpr);
      // Beacon (true position, drawn at its real 10 px size, with a glow so it is visible).
      const [tx, ty] = toPx(s.target.u, s.target.v);
      const g = ctx.createRadialGradient(X(tx), Y(ty), 0, X(tx), Y(ty), 10 * dpr);
      g.addColorStop(0, s.disturbance.occluded ? 'rgba(255,90,90,0.25)' : 'rgba(255,70,70,0.95)');
      g.addColorStop(1, 'rgba(255,70,70,0)');
      ctx.fillStyle = g;
      ctx.fillRect(X(tx) - 10 * dpr, Y(ty) - 10 * dpr, 20 * dpr, 20 * dpr);
      const sp = Math.max(2 * dpr, conf.target.spotSizePx * k);
      ctx.fillStyle = s.disturbance.occluded ? 'rgba(255,255,255,0.3)' : '#fff';
      ctx.fillRect(X(tx) - sp / 2, Y(ty) - sp / 2, sp, sp);
      // Clean telemetry pill in bottom-right corner (never overlaps camera or grid)
      const errPx = Math.hypot(tx - bx, ty - by);
      const statText = `BEACON ${tx.toFixed(0)},${ty.toFixed(0)} · ERR ${errPx.toFixed(1)} px${s.disturbance.occluded ? ' · OUTAGE' : ''}`;
      ctx.font = `500 ${8 * dpr}px "IBM Plex Mono", monospace`;
      const statW = ctx.measureText(statText).width + 10 * dpr;
      const statH = 14 * dpr;
      const statX = ox + side - statW - 4 * dpr;
      const statY = oy + side - statH - 4 * dpr;

      ctx.fillStyle = 'rgba(7, 12, 20, 0.88)';
      drawPill(statX, statY, statW, statH, 3 * dpr);
      ctx.fill();
      ctx.strokeStyle = s.disturbance.occluded ? 'rgba(255,90,90,0.4)' : 'rgba(170,214,255,0.2)';
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.fillStyle = s.disturbance.occluded ? '#ff7b7b' : 'rgba(232,240,247,0.85)';
      ctx.fillText(statText, statX + 5 * dpr, statY + 10 * dpr);
      ctx.textAlign = 'left';
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);
  return <canvas ref={ref} />;
}

export function SensorView() {
  const overlays = useApp((s) => s.overlays);
  const logic = useApp((s) => s.config.logic);
  const kind = useApp((s) => s.providerKind);
  const hud = useApp((s) => s.hud);
  const set = useApp((s) => s.set);
  const toggleOverlay = useApp((s) => s.toggleOverlay);
  const tab = useApp((s) => s.sensorTab);
  const canvas = useRef<HTMLCanvasElement>(null);
  const off = useRef<HTMLCanvasElement | null>(null);
  const opts = useRef({ truth: false, calibration: false, roi: true, lockPx: 10, acqPx: 30 });
  opts.current = { truth: overlays.truth, calibration: overlays.calibration, roi: overlays.roi, lockPx: logic.lockPx, acqPx: logic.acquirePx };

  useEffect(() => {
    let raf = 0;
    let lastImg = -1;
    let lastFrame = -1;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const c = canvas.current;
      const snap = live.snap;
      if (!c || !snap) return;
      const img = live.image;
      if (live.imageVersion === lastImg && snap.frame === lastFrame) return;
      lastFrame = snap.frame;
      const rect = c.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const W = Math.round(rect.width * dpr);
      const H = Math.round(rect.height * dpr);
      if (c.width !== W || c.height !== H) {
        c.width = W;
        c.height = H;
      }
      const ctx = c.getContext('2d')!;
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, W, H);
      // Choose the snapshot that matches the displayed image (images arrive at a lower rate).
      let s = snap;
      if (img) {
        if (live.imageVersion !== lastImg) {
          lastImg = live.imageVersion;
          if (!off.current) off.current = document.createElement('canvas');
          const o = off.current;
          if (o.width !== img.width || o.height !== img.height) {
            o.width = img.width;
            o.height = img.height;
          }
          const octx = o.getContext('2d')!;
          const id = octx.createImageData(img.width, img.height);
          const d = id.data;
          const src = img.data;
          for (let i = 0, j = 0; i < src.length; i++, j += 4) {
            const v = src[i];
            d[j] = v * 0.94;
            d[j + 1] = v * 0.98;
            d[j + 2] = v;
            d[j + 3] = 255;
          }
          octx.putImageData(id, 0, 0);
        }
        const match = live.recent.find((r) => r.frame === img.frame);
        if (match) s = match;
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(off.current!, 0, 0, W, H);
      } else {
        ctx.fillStyle = 'rgba(232,240,247,0.5)';
        ctx.font = `${12 * dpr}px "IBM Plex Mono", monospace`;
        ctx.textAlign = 'center';
        ctx.fillText(useApp.getState().providerKind === 'replay' ? 'REPLAY · images are not recorded — overlays only' : 'NO SIGNAL', W / 2, H / 2 - 20);
        ctx.textAlign = 'left';
      }
      drawOverlay(ctx, s, W, H, W / s.camera.width, opts.current);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);

  const d = hud?.detection;
  const e = hud?.error;
  return (
    <section className="sensor glass">
      <div className="sensor-head">
        <div className="sensor-tabs">
          <button className={tab === 'camera' ? 'on' : ''} onClick={() => set({ sensorTab: 'camera' })} title="The real 640×480 camera image">
            Camera {kind === 'replay' ? <span className="tag">recorded</span> : <span className="tag sim">live</span>}
          </button>
          <button className={tab === 'screen' ? 'on' : ''} onClick={() => set({ sensorTab: 'screen' })} title="The 2000×2000 px search screen with the moving camera window (G)">
            Screen 2000²
          </button>
        </div>
        <div className="row">
          <button className={`btn icon sm ghost ${overlays.calibration ? 'on' : ''}`} title="Calibration grid (degrees)" onClick={() => toggleOverlay('calibration')}>
            <Icon name="crosshair" size={15} />
          </button>
        </div>
      </div>
        <div className="sensor-canvas-wrap">
          <canvas ref={canvas} style={tab === 'screen' ? { visibility: 'hidden' } : undefined} />
          {tab === 'screen' && <ScreenCanvas />}
        </div>
        <div className="sensor-foot">
          <div>
            <div className="eyebrow">Centroid</div>
            <div className="v">{d ? `${d.x.toFixed(1)}, ${d.y.toFixed(1)}` : '—'}</div>
          </div>
          <div>
            <div className="eyebrow">Pixel error</div>
            <div className="v" style={{ color: e?.magPx !== null && (e?.magPx ?? 99) < logic.lockPx ? 'var(--lock)' : undefined }}>{fmt(e?.estMagPx, 1, ' px')}</div>
          </div>
          <div>
            <div className="eyebrow">Angular err</div>
            <div className="v">{fmt(e?.angDeg, 3, '°')}</div>
          </div>
          <div>
            <div className="eyebrow">Confidence</div>
            <div className="v">{d ? `${(d.confidence * 100).toFixed(0)} %` : '—'}</div>
          </div>
        </div>
      </section>
    );
  }

export function Timeline() {
  const hud = useApp((s) => s.hud);
  const events = useApp((s) => s.events);
  const state = hud?.state ?? 'IDLE';
  const lastTr = [...events].reverse().find((e) => e.kind === 'transition');
  return (
    <section className="timeline glass">
      <div className="eyebrow">Mission timeline · first time reached</div>
      <div className="tl-track">
        {STEPS.map((st) => {
          const t = hud?.timeline[st.key] ?? null;
          const active = st.states.includes(state);
          const color = active ? stateColor(state) : t !== null ? 'var(--text)' : 'var(--text-3)';
          return (
            <div key={st.key} className={`tl-step ${active ? 'active' : ''}`} style={{ color }}>
              <div className="bar">
                <i style={{ transform: `scaleX(${t !== null || active ? 1 : 0})`, opacity: active ? 1 : 0.45 }} />
              </div>
              <div className="n">{st.label}</div>
              <div className="t">{t !== null ? `${t.toFixed(2)} s` : '—'}</div>
            </div>
          );
        })}
      </div>
      {lastTr && (
        <div className="tl-reason">
          <span className="mono">{lastTr.t.toFixed(2)}s</span>
          <span>
            <b style={{ color: stateColor(lastTr.to) }}>{lastTr.to}</b> — {lastTr.message}
          </span>
        </div>
      )}
    </section>
  );
}
