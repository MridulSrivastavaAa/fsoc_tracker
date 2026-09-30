/**
 * Video benchmark panel (PS "Benchmark-2"): bypass the simulated pan/tilt camera and
 * run the coarse-pointing pipeline on a recorded video.
 *
 *   · Browser: the video is decoded by the browser (seek → draw → grey) and analysed
 *     frame by frame with the same detector + learned verifier + Kalman as the engine.
 *   · FastAPI server: the file is uploaded to /api/video/analyze (OpenCV decoding).
 *   · Built-in stream: a synthetic full-screen (2000×2000) noisy video with a moving
 *     beacon and a cloud outage, generated in the browser, with exact ground truth.
 */
import { useEffect, useRef, useState } from 'react';
import { useApp, saveReport, download } from '../state/store';
import { DEFAULT_VIDEO_PARAMS, VideoAnalyzer, VideoParams, VideoRow, parseTruthCsv, rgbaToGray } from '../core/video/analyzer';
import { buildReport, fmtVal, VideoReportSummary } from '../core/analysis/report';
import { Rng } from '../core/math';
import { syntheticFrame } from '../core/video/synthetic';
import { Icon, Seg, Slider, Toggle } from './ui';

type Source = 'browser' | 'server';

interface Progress {
  i: number;
  n: number;
  row: VideoRow | null;
  fps: number;
}

export interface TrajectoryPoint {
  frame: number;
  time_s: number;
  state: string;
  est_x: number | null;
  est_y: number | null;
  gt_x: number | null;
  gt_y: number | null;
  error_px: number | null;
}

function drawPreview(
  cv: HTMLCanvasElement,
  gray: Uint8Array | Uint8ClampedArray,
  W: number,
  H: number,
  row: VideoRow | null,
  spot: number
) {
  const maxW = 560;
  const maxH = 400;
  const k = Math.min(maxW / W, maxH / H);
  const w = Math.max(1, Math.round(W * k));
  const h = Math.max(1, Math.round(H * k));
  cv.width = w;
  cv.height = h;
  const ctx = cv.getContext('2d')!;
  const img = ctx.createImageData(w, h);

  const step = 1 / k;
  for (let y = 0; y < h; y++) {
    const y0 = Math.floor(y * step);
    const y1 = Math.min(H, Math.max(y0 + 1, Math.floor((y + 1) * step)));
    for (let x = 0; x < w; x++) {
      const x0 = Math.floor(x * step);
      const x1 = Math.min(W, Math.max(x0 + 1, Math.floor((x + 1) * step)));
      let sum = 0;
      let cnt = 0;
      for (let yy = y0; yy < y1; yy += 1) {
        for (let xx = x0; xx < x1; xx += 1) {
          sum += gray[yy * W + xx];
          cnt++;
        }
      }
      const o = (y * w + x) * 4;
      img.data[o] = img.data[o + 1] = img.data[o + 2] = Math.min(255, (1.8 * sum) / cnt);
      img.data[o + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);

  // Center crosshair
  ctx.lineWidth = 1.2;
  ctx.strokeStyle = 'rgba(232,240,247,0.35)';
  ctx.beginPath();
  ctx.moveTo(w / 2 - 10, h / 2);
  ctx.lineTo(w / 2 + 10, h / 2);
  ctx.moveTo(w / 2, h / 2 - 10);
  ctx.lineTo(w / 2, h / 2 + 10);
  ctx.stroke();

  if (!row) return;

  // Ground Truth Circle
  if (row.truthX !== null && row.truthY !== null) {
    ctx.strokeStyle = 'rgba(255,208,138,0.95)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(row.truthX * k, row.truthY * k, 10, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = '#ffd08a';
    ctx.font = '10px monospace';
    ctx.fillText('TRUTH', row.truthX * k + 12, row.truthY * k + 3);
  }

  // Detected spot & Kalman bounding box
  if (row.x !== null && row.y !== null) {
    const s = Math.max(12, spot * k * 2.2);
    const isLock = row.state === 'TRACKING';
    ctx.strokeStyle = isLock ? '#34d399' : '#fbbf24';
    ctx.lineWidth = 1.8;
    ctx.strokeRect(row.x * k - s / 2, row.y * k - s / 2, s, s);
    ctx.beginPath();
    ctx.moveTo(row.x * k - s, row.y * k);
    ctx.lineTo(row.x * k + s, row.y * k);
    ctx.moveTo(row.x * k, row.y * k - s);
    ctx.lineTo(row.x * k, row.y * k + s);
    ctx.stroke();

    // Spot core
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(row.x * k, row.y * k, 2.5, 0, Math.PI * 2);
    ctx.fill();
  }

  // Kalman predicted diamond
  if (row.kfX !== null && row.kfY !== null) {
    ctx.fillStyle = '#38bdf8';
    ctx.beginPath();
    ctx.moveTo(row.kfX * k, row.kfY * k - 6);
    ctx.lineTo(row.kfX * k + 6, row.kfY * k);
    ctx.lineTo(row.kfX * k, row.kfY * k + 6);
    ctx.lineTo(row.kfX * k - 6, row.kfY * k);
    ctx.closePath();
    ctx.fill();
  }
}

function drawTrajectoryCanvas(
  cv: HTMLCanvasElement,
  W: number,
  H: number,
  index: number,
  points: TrajectoryPoint[],
  spotSize: number = 8
) {
  if (!points || points.length === 0) return;
  const maxW = 560;
  const maxH = 400;
  const k = Math.min(maxW / W, maxH / H);
  const w = Math.max(1, Math.round(W * k));
  const h = Math.max(1, Math.round(H * k));
  cv.width = w;
  cv.height = h;
  const ctx = cv.getContext('2d');
  if (!ctx) return;

  // Background space gradient
  const grad = ctx.createRadialGradient(w / 2, h / 2, 20, w / 2, h / 2, Math.max(w, h));
  grad.addColorStop(0, '#0f172a');
  grad.addColorStop(1, '#020617');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  // Radar Grid
  ctx.strokeStyle = 'rgba(56, 189, 248, 0.1)';
  ctx.lineWidth = 1;
  const step = 45;
  for (let x = 0; x < w; x += step) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
  for (let y = 0; y < h; y += step) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  // Crosshair
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
  ctx.beginPath();
  ctx.moveTo(w / 2 - 12, h / 2);
  ctx.lineTo(w / 2 + 12, h / 2);
  ctx.moveTo(w / 2, h / 2 - 12);
  ctx.lineTo(w / 2, h / 2 + 12);
  ctx.stroke();

  const cur = points[Math.min(index, points.length - 1)];
  if (!cur) return;

  // Motion Trail (Past 60 positions)
  const startIdx = Math.max(0, index - 60);
  ctx.lineWidth = 2;
  for (let i = startIdx; i < index; i++) {
    const p1 = points[i];
    const p2 = points[i + 1];
    if (p1 && p2 && p1.est_x !== null && p1.est_y !== null && p2.est_x !== null && p2.est_y !== null) {
      const alpha = (i - startIdx) / (index - startIdx + 1e-3);
      ctx.strokeStyle = `rgba(56, 189, 248, ${alpha * 0.8})`;
      ctx.beginPath();
      ctx.moveTo(p1.est_x * k, p1.est_y * k);
      ctx.lineTo(p2.est_x * k, p2.est_y * k);
      ctx.stroke();
    }
  }

  // Ground Truth Circle
  if (cur.gt_x !== null && cur.gt_y !== null) {
    ctx.strokeStyle = 'rgba(255, 208, 138, 0.95)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(cur.gt_x * k, cur.gt_y * k, 10, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = '#ffd08a';
    ctx.font = '10px monospace';
    ctx.fillText('TRUTH', cur.gt_x * k + 12, cur.gt_y * k + 3);
  }

  // Current Estimated Centroid & Kalman Box
  if (cur.est_x !== null && cur.est_y !== null) {
    const s = Math.max(14, (spotSize || 8) * k * 2.5);
    const isLocked = cur.state === 'TRACK' || cur.state === 'TRACKING';
    const col = isLocked ? '#34d399' : '#fbbf24';

    ctx.shadowColor = col;
    ctx.shadowBlur = 10;
    ctx.strokeStyle = col;
    ctx.lineWidth = 2;
    ctx.strokeRect(cur.est_x * k - s / 2, cur.est_y * k - s / 2, s, s);

    ctx.beginPath();
    ctx.moveTo(cur.est_x * k - s * 0.7, cur.est_y * k);
    ctx.lineTo(cur.est_x * k + s * 0.7, cur.est_y * k);
    ctx.moveTo(cur.est_x * k, cur.est_y * k - s * 0.7);
    ctx.lineTo(cur.est_x * k, cur.est_y * k + s * 0.7);
    ctx.stroke();

    ctx.shadowBlur = 0;
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(cur.est_x * k, cur.est_y * k, 3, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = col;
    ctx.font = 'bold 11px monospace';
    ctx.fillText(isLocked ? 'LOCKED' : cur.state, cur.est_x * k + s / 2 + 5, cur.est_y * k - s / 2);
  }

  // Top HUD Overlay
  ctx.fillStyle = 'rgba(4, 7, 13, 0.85)';
  ctx.fillRect(8, 8, 260, 48);
  ctx.strokeStyle = 'rgba(56, 189, 248, 0.4)';
  ctx.strokeRect(8, 8, 260, 48);

  ctx.fillStyle = '#e2e8f0';
  ctx.font = '11px monospace';
  ctx.fillText(`FRAME: ${cur.frame}/${points.length}  TIME: ${cur.time_s.toFixed(2)}s`, 16, 24);

  const isLock = cur.state === 'TRACK' || cur.state === 'TRACKING';
  ctx.fillStyle = isLock ? '#34d399' : '#fbbf24';
  ctx.fillText(`STATE: ${cur.state}`, 16, 42);

  if (cur.error_px !== null) {
    ctx.fillStyle = '#38bdf8';
    ctx.fillText(`ERROR: ${cur.error_px.toFixed(2)} px`, 140, 42);
  }
}

export function VideoBench() {
  const open = useApp((s) => s.videoOpen);
  const serverUrl = useApp((s) => s.serverUrl);
  const set = useApp((s) => s.set);
  const notify = useApp((s) => s.notify);

  const [source, setSource] = useState<Source>('browser');
  const [file, setFile] = useState<File | null>(null);
  const [truthText, setTruthText] = useState<string | null>(null);
  const [truthName, setTruthName] = useState<string>('');
  const [params, setParams] = useState<VideoParams>({ ...DEFAULT_VIDEO_PARAMS });
  const [fps, setFps] = useState(30);
  const [exact, setExact] = useState(false);
  const [busy, setBusy] = useState(false);
  const [prog, setProg] = useState<Progress | null>(null);
  const [result, setResult] = useState<{
    summary: VideoReportSummary;
    analyzer: VideoAnalyzer | null;
    server?: { csv: string; report: string };
  } | null>(null);

  // Live Trajectory & Interactive Replay State
  const [trajectory, setTrajectory] = useState<TrajectoryPoint[]>([]);
  const [playbackIndex, setPlaybackIndex] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);

  const cancel = useRef(false);
  const preview = useRef<HTMLCanvasElement>(null);
  const vidIn = useRef<HTMLInputElement>(null);
  const truthIn = useRef<HTMLInputElement>(null);

  useEffect(() => () => void (cancel.current = true), []);

  // Replay animation loop
  useEffect(() => {
    if (!isPlaying || trajectory.length === 0) return;
    const interval = 1000 / (fps * playbackSpeed);
    const timer = setInterval(() => {
      setPlaybackIndex((prev) => {
        const next = prev + 1;
        if (next >= trajectory.length) {
          return 0; // loop
        }
        return next;
      });
    }, interval);
    return () => clearInterval(timer);
  }, [isPlaying, trajectory, fps, playbackSpeed]);

  // Update canvas on trajectory change or scrub
  useEffect(() => {
    if (trajectory.length > 0 && preview.current && !busy) {
      const W = result?.summary.width || 1000;
      const H = result?.summary.height || 1000;
      drawTrajectoryCanvas(preview.current, W, H, playbackIndex, trajectory, params.spotSizePx);
    }
  }, [playbackIndex, trajectory, result, busy, params.spotSizePx]);

  if (!open) return null;

  const close = () => {
    cancel.current = true;
    setIsPlaying(false);
    set({ videoOpen: false });
  };

  /** Full Reset / Refresh for analyzing another video */
  const handleReset = () => {
    cancel.current = true;
    setIsPlaying(false);
    setBusy(false);
    setFile(null);
    setTruthText(null);
    setTruthName('');
    setProg(null);
    setResult(null);
    setTrajectory([]);
    setPlaybackIndex(0);
    if (vidIn.current) vidIn.current.value = '';
    if (truthIn.current) truthIn.current.value = '';
    if (preview.current) {
      const ctx = preview.current.getContext('2d');
      if (ctx) {
        ctx.fillStyle = '#060a12';
        ctx.fillRect(0, 0, preview.current.width || 560, preview.current.height || 380);
      }
    }
    notify('Reset complete! Ready to choose and analyze a new video.');
  };

  async function runBrowser(synthetic: boolean) {
    cancel.current = false;
    setIsPlaying(false);
    setBusy(true);
    setResult(null);
    setTrajectory([]);

    const truth = truthText ? parseTruthCsv(truthText) : null;
    const a = new VideoAnalyzer({ ...params }, fps);
    let W = 2000;
    let H = 2000;
    let n = 180;
    let video: HTMLVideoElement | null = null;
    let url = '';
    let canvas: HTMLCanvasElement | null = null;
    let c2d: CanvasRenderingContext2D | null = null;

    try {
      if (!synthetic) {
        if (!file) return;
        url = URL.createObjectURL(file);
        video = document.createElement('video');
        video.muted = true;
        video.preload = 'auto';
        video.src = url;
        let canPlay = true;
        try {
          await new Promise<void>((res, rej) => {
            video!.onloadedmetadata = () => res();
            video!.onerror = () => rej(new Error('HTML5 video decoding unsupported'));
          });
        } catch {
          canPlay = false;
        }

        if (!canPlay || !video.videoWidth || !video.videoHeight) {
          notify('Browser cannot decode this video directly. Automatically delegating to FastAPI OpenCV engine...');
          if (url) URL.revokeObjectURL(url);
          url = '';
          return await runServer();
        }

        W = video.videoWidth;
        H = video.videoHeight;
        n = Math.max(1, Math.floor(video.duration * fps + 1e-6));
        canvas = document.createElement('canvas');
        canvas.width = W;
        canvas.height = H;
        c2d = canvas.getContext('2d', { willReadFrequently: true });
      }

      const gray = new Uint8Array(W * H);
      const rng = new Rng(7);
      const t0 = performance.now();
      let lastDraw = 0;

      const step = async (i: number, tr: [number, number] | null, idx?: number) => {
        const row = a.process(gray, W, H, tr, idx);
        const now = performance.now();
        if (now - lastDraw > 30 || i === n - 1) {
          lastDraw = now;
          if (preview.current) drawPreview(preview.current, gray, W, H, row, a.spotSizePx);
          setProg({ i: i + 1, n, row, fps: (1000 * (i + 1)) / (now - t0) });
          await new Promise((r) => setTimeout(r, 0));
        }
      };

      type RVFC = (cb: (now: number, meta: { mediaTime: number }) => void) => number;
      const rvfc = video ? ((video as unknown as { requestVideoFrameCallback?: RVFC }).requestVideoFrameCallback?.bind(video) ?? null) : null;

      if (synthetic) {
        for (let i = 0; i < n && !cancel.current; i++) {
          await step(i, syntheticFrame(i, fps, W, H, rng, gray));
        }
      } else if (video && c2d && rvfc && !exact) {
        const v = video;
        const cx = c2d;
        const queue: { idx: number; g: Uint8Array }[] = [];
        let ended = false;
        let lastFrameAt = performance.now();
        const play = () => void v.play().catch(() => undefined);
        const onFrame = (_now: number, meta: { mediaTime: number }) => {
          lastFrameAt = performance.now();
          cx.drawImage(v, 0, 0, W, H);
          const g = new Uint8Array(W * H);
          rgbaToGray(cx.getImageData(0, 0, W, H).data, g);
          queue.push({ idx: Math.round(meta.mediaTime * fps), g });
          if (queue.length > (W * H > 1e6 ? 6 : 24)) v.pause();
          if (!ended && !cancel.current) rvfc(onFrame);
        };
        v.onended = () => {
          ended = true;
        };
        v.playbackRate = W * H > 1e6 ? 0.25 : 0.5;
        rvfc(onFrame);
        play();
        let i = 0;
        while (!cancel.current) {
          const item = queue.shift();
          if (!item) {
            if (ended || performance.now() - lastFrameAt > 8000) break;
            if (v.paused && !ended) play();
            await new Promise((r) => setTimeout(r, 4));
            continue;
          }
          gray.set(item.g);
          await step(i++, truth?.get(item.idx) ?? null, item.idx);
          if (v.paused && !ended && queue.length < 3) play();
        }
        v.pause();
      } else if (video && c2d) {
        for (let i = 0; i < n && !cancel.current; i++) {
          video.currentTime = Math.min(video.duration - 1e-3, (i + 0.5) / fps);
          await new Promise<void>((res) => {
            video!.onseeked = () => res();
          });
          c2d.drawImage(video, 0, 0, W, H);
          rgbaToGray(c2d.getImageData(0, 0, W, H).data, gray);
          await step(i, truth?.get(i) ?? null, i);
        }
      }

      const summary = a.summary(synthetic ? 'built-in synthetic stream (2000×2000)' : (file?.name ?? 'video'), synthetic || !!truth);
      const traj: TrajectoryPoint[] = a.rows.map((r, i) => ({
        frame: r.frame !== undefined ? r.frame : i,
        time_s: (r.frame !== undefined ? r.frame : i) / fps,
        state: r.state,
        est_x: r.x,
        est_y: r.y,
        gt_x: r.truthX,
        gt_y: r.truthY,
        error_px: r.centroidErr,
      }));

      setTrajectory(traj);
      setPlaybackIndex(0);
      setIsPlaying(true);
      setResult({ summary, analyzer: a });
    } catch (e) {
      notify((e as Error).message);
    } finally {
      if (url) URL.revokeObjectURL(url);
      setBusy(false);
    }
  }

  const loadPresetVideo = async (videoUrl: string, truthUrl: string, name: string) => {
    try {
      setBusy(true);
      notify(`Loading ${name}...`);
      const vResp = await fetch(videoUrl);
      if (!vResp.ok) throw new Error(`Could not load ${videoUrl} (status ${vResp.status})`);
      const vBlob = await vResp.blob();
      const f = new File([vBlob], videoUrl.split('/').pop() || 'test_video.mp4', { type: 'video/mp4' });
      setFile(f);

      if (truthUrl) {
        const tResp = await fetch(truthUrl);
        if (tResp.ok) {
          const tText = await tResp.text();
          setTruthText(tText);
          setTruthName(truthUrl.split('/').pop() || 'truth.csv');
        }
      }
      notify(`${name} loaded! Click 'Analyse video' to run tracking.`);
    } catch (e) {
      notify(`Failed to load preset video: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  async function runServer() {
    if (!file) return;
    setIsPlaying(false);
    setBusy(true);
    setResult(null);
    setProg(null);
    setTrajectory([]);

    try {
      const fd = new FormData();
      fd.append('file', file);
      if (truthText) fd.append('truth', new Blob([truthText], { type: 'text/csv' }), truthName || 'truth.csv');
      fd.append('hfovDeg', String(params.hfovDeg));
      fd.append('spotSizePx', String(params.spotSizePx));
      fd.append('thresholdSigma', String(params.thresholdSigma));
      fd.append('verifier', String(params.verifier));

      let base = serverUrl.replace(/\/$/, '');
      let r: Response | null = null;
      try {
        r = await fetch(`${base}/api/video/analyze`, { method: 'POST', body: fd });
      } catch (err) {
        // Intelligent fallback: try http://127.0.0.1:8000 or current window origin
        const altBase = base.includes('8000')
          ? (typeof window !== 'undefined' && window.location.origin.startsWith('http') ? window.location.origin : 'http://127.0.0.1:8000')
          : 'http://127.0.0.1:8000';
        if (altBase !== base) {
          try {
            r = await fetch(`${altBase}/api/video/analyze`, { method: 'POST', body: fd });
            base = altBase;
          } catch {
            throw err;
          }
        } else {
          throw err;
        }
      }

      if (!r.ok) throw new Error(`Server: ${r.status} ${await r.text()}`);
      const j = await r.json();
      const s = j.summary;

      if (j.trajectory && Array.isArray(j.trajectory)) {
        setTrajectory(j.trajectory);
        setPlaybackIndex(0);
        setIsPlaying(true);
      }

      setResult({
        summary: {
          fileName: file.name,
          width: s.width,
          height: s.height,
          fps: s.videoFps,
          frames: s.frames,
          detectionRate: (s.detectionRatePct ?? 0) / 100,
          acquisitionS: s.acquisitionS,
          lossPct: s.lossPct,
          reacqMaxS: s.reacqMaxS,
          centroidRmsePx: s.centroidRmsePx,
          centroidMaxPx: s.centroidMaxPx,
          procMeanMs: s.procMeanMs ?? 0,
          processingFps: s.processingFps ?? 0,
          lockRetentionPct: s.lockRetentionPct ?? null,
          truthProvided: s.truthProvided,
        },
        analyzer: null,
        server: { csv: `${base}${j.csv}`, report: `${base}${j.report}` },
      });
    } catch (e) {
      notify(`Video analysis failed: ${(e as Error).message}. Is the FastAPI server running?`);
    } finally {
      setBusy(false);
    }
  }

  const s = result?.summary;
  const report = (fmt: 'html' | 'md' | 'json') => {
    if (!s) return;
    const rep = buildReport({
      kind: 'video',
      source: result?.server ? 'FastAPI engine (camera bypass)' : 'Browser (camera bypass)',
      config: null,
      video: s,
    });
    saveReport(rep, fmt, 'netra-video-report');
  };

  return (
    <div className="modal-back" onClick={(e) => e.target === e.currentTarget && !busy && close()}>
      <div className="modal glass" role="dialog" aria-label="Video benchmark" style={{ maxWidth: 1080 }}>
        <div className="drawer-head">
          <div className="row" style={{ gap: 8, alignItems: 'center' }}>
            <h3>
              Video benchmark <span className="dim" style={{ letterSpacing: '0.06em', fontSize: 12 }}>· camera bypass (PS Benchmark-2)</span>
            </h3>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn sm ghost" onClick={handleReset} title="Reset and analyze another video" disabled={busy}>
              <Icon name="refresh" size={14} /> Refresh / Reset
            </button>
            <button className="btn icon ghost" onClick={close} aria-label="Close" disabled={busy}>
              <Icon name="close" />
            </button>
          </div>
        </div>

        <div className="modal-body">
          <div className="modal-left">
            <p className="note" style={{ marginTop: 0 }}>
              The simulated pan/tilt camera is bypassed: every frame of a recorded video goes straight into the detector, the learned verifier and the Kalman tracker. You get live target movement visualization, per-frame centroid logs and automated KPI verification.
            </p>

            <div className="eyebrow" style={{ margin: '10px 0 6px' }}>
              Analyse in
            </div>
            <Seg
              value={source}
              options={[
                { v: 'browser', label: 'This browser' },
                { v: 'server', label: 'FastAPI server' },
              ]}
              onChange={setSource}
            />

            <div className="eyebrow" style={{ margin: '12px 0 6px' }}>
              Quick Presets (ISRO 5-Tier Test Suite)
            </div>
            <div className="row wrap" style={{ gap: 6, marginBottom: 10 }}>
              <button
                className="btn xs ghost"
                disabled={busy}
                onClick={() => loadPresetVideo('/test_videos/tier1_clean_90pct.mp4', '/test_videos/tier1_clean_90pct_truth.csv', 'Tier 1 (90% Clean)')}
                title="Tier 1: 90% Clean, pristine sky, high SNR"
              >
                Tier 1 (90%)
              </button>
              <button
                className="btn xs ghost"
                disabled={busy}
                onClick={() => loadPresetVideo('/test_videos/tier2_mild_70pct.mp4', '/test_videos/tier2_mild_70pct_truth.csv', 'Tier 2 (70% Mild)')}
                title="Tier 2: 70% Mild haze, slight vibration"
              >
                Tier 2 (70%)
              </button>
              <button
                className="btn xs ghost"
                disabled={busy}
                onClick={() => loadPresetVideo('/test_videos/tier3_moderate_50pct.mp4', '/test_videos/tier3_moderate_50pct_truth.csv', 'Tier 3 (50% Fog)')}
                title="Tier 3: 50% Moderate fog & scintillation"
              >
                Tier 3 (50%)
              </button>
              <button
                className="btn xs ghost"
                disabled={busy}
                onClick={() => loadPresetVideo('/test_videos/tier4_degraded_30pct.mp4', '/test_videos/tier4_degraded_30pct_truth.csv', 'Tier 4 (30% Rain)')}
                title="Tier 4: 30% Rain streaks & platform drift"
              >
                Tier 4 (30%)
              </button>
              <button
                className="btn xs ghost"
                disabled={busy}
                onClick={() => loadPresetVideo('/test_videos/tier5_extreme_10pct.mp4', '/test_videos/tier5_extreme_10pct_truth.csv', 'Tier 5 (10% Extreme)')}
                title="Tier 5: 10% Heavy noise, jitter & dropouts"
              >
                Tier 5 (10%)
              </button>
              <button
                className="btn xs ghost"
                disabled={busy}
                onClick={() => loadPresetVideo('/fsoc_test_video_30s_60fps.mp4', '/fsoc_test_video_30s_60fps_truth.csv', '30s Benchmark Baseline')}
                title="Original 30s 60fps Benchmark Video"
              >
                30s Baseline
              </button>
            </div>

            <div className="row" style={{ marginTop: 6 }}>
              <button className="btn sm" onClick={() => vidIn.current?.click()} disabled={busy}>
                <Icon name="film" size={14} /> {file ? 'Change custom video' : 'Choose custom video (.mp4)'}
              </button>
              <button className="btn sm" onClick={() => truthIn.current?.click()} disabled={busy}>
                <Icon name="upload" size={14} /> {truthText ? 'Change truth CSV' : 'Ground truth CSV (optional)'}
              </button>
            </div>

            <p className="note">
              {file ? (
                <>
                  Video: <b>{file.name}</b> ({(file.size / 1e6).toFixed(1)} MB)
                </>
              ) : (
                'No video chosen.'
              )}
              {truthText && (
                <>
                  <br />
                  Truth: <b>{truthName}</b> (detected coordinates loaded)
                </>
              )}
            </p>

            <input
              ref={vidIn}
              type="file"
              accept="video/*,.mp4,.m4v,.webm,.mov,.avi"
              style={{ display: 'none' }}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                e.target.value = '';
              }}
            />
            <input
              ref={truthIn}
              type="file"
              accept=".csv,text/csv"
              style={{ display: 'none' }}
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (f) {
                  setTruthText(await f.text());
                  setTruthName(f.name);
                }
                e.target.value = '';
              }}
            />

            {source === 'browser' && <Slider label="Frame rate of the video" value={fps} min={10} max={60} step={1} digits={0} unit=" fps" onChange={setFps} />}
            <Slider label="Horizontal FOV of the video" value={params.hfovDeg} min={0.5} max={30} step={0.5} digits={1} unit="°" onChange={(v) => setParams({ ...params, hfovDeg: v })} />
            <Slider label="Beacon size (0 = auto-estimate)" value={params.spotSizePx} min={0} max={30} step={1} digits={0} unit=" px" onChange={(v) => setParams({ ...params, spotSizePx: v })} />
            <Slider label="Threshold (k·σ)" value={params.thresholdSigma} min={3} max={10} step={0.5} digits={1} onChange={(v) => setParams({ ...params, thresholdSigma: v })} />
            <Toggle label="Learned beacon verifier (AI)" on={params.verifier} onChange={(v) => setParams({ ...params, verifier: v })} />
            {source === 'browser' && (
              <Toggle
                label="Frame-exact decoding (slower)"
                on={exact}
                onChange={setExact}
                hint="Seek to every frame instead of playing the video: no frame is skipped, but long videos take much longer"
              />
            )}

            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn primary" disabled={busy || !file} onClick={() => (source === 'browser' ? runBrowser(false) : runServer())}>
                Analyse video
              </button>
              {source === 'browser' && (
                <button className="btn" disabled={busy} onClick={() => runBrowser(true)} title="No file needed: a generated 2000×2000 noisy video with exact ground truth">
                  Try built-in 2000×2000 stream
                </button>
              )}
              {busy && source === 'browser' && (
                <button className="btn ghost" onClick={() => (cancel.current = true)}>
                  Stop
                </button>
              )}
              <button className="btn ghost" disabled={busy} onClick={handleReset} title="Clear current inputs and start fresh">
                Reset
              </button>
            </div>

            {source === 'server' && (
              <p className="note" style={{ marginTop: 10 }}>
                Uploads to <b>{serverUrl}</b>/api/video/analyze (OpenCV decoding, all codecs supported).
              </p>
            )}
          </div>

          <div className="modal-right">
            {/* Live Movement & Canvas View */}
            <div className="vb-preview" style={{ position: 'relative', background: '#020617', borderRadius: 8, overflow: 'hidden' }}>
              <canvas ref={preview} style={{ display: 'block', width: '100%', maxHeight: 380 }} />
              {!prog && !result && !busy && trajectory.length === 0 && (
                <span className="dim">Preview and live movement trajectory appear here</span>
              )}
            </div>

            {/* Interactive Live Movement Playback Bar */}
            {trajectory.length > 0 && (
              <div className="row" style={{ background: 'rgba(15, 23, 42, 0.7)', padding: '8px 12px', borderRadius: 6, marginTop: 8, alignItems: 'center', gap: 10 }}>
                <button
                  className="btn sm icon primary"
                  onClick={() => setIsPlaying(!isPlaying)}
                  title={isPlaying ? 'Pause movement playback' : 'Play live movement animation'}
                >
                  <Icon name={isPlaying ? 'pause' : 'play'} size={14} />
                </button>
                <button
                  className="btn sm icon ghost"
                  onClick={() => {
                    setIsPlaying(false);
                    setPlaybackIndex(0);
                  }}
                  title="Rewind to start"
                >
                  <Icon name="backward" size={14} />
                </button>
                <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="range"
                    min={0}
                    max={Math.max(0, trajectory.length - 1)}
                    value={playbackIndex}
                    onChange={(e) => {
                      setIsPlaying(false);
                      setPlaybackIndex(Number(e.target.value));
                    }}
                    style={{ width: '100%', accentColor: '#38bdf8' }}
                  />
                  <span className="mono dim" style={{ fontSize: 11, minWidth: 65, textAlign: 'right' }}>
                    {playbackIndex + 1}/{trajectory.length}
                  </span>
                </div>
                <button
                  className="btn sm ghost"
                  onClick={() => setPlaybackSpeed((s) => (s === 1 ? 2 : s === 2 ? 4 : s === 4 ? 0.5 : 1))}
                  title="Playback speed"
                  style={{ fontSize: 11 }}
                >
                  {playbackSpeed}x
                </button>
              </div>
            )}

            {/* Processing Progress */}
            {busy && !prog && (
              <div className="vb-prog" style={{ marginTop: 8 }}>
                <div className="prog">
                  <i style={{ width: '100%', opacity: 0.8 }} />
                </div>
                <span className="mono dim">Running coarse-pointing pipeline & extracting metrics...</span>
              </div>
            )}
            {prog && (
              <div className="vb-prog" style={{ marginTop: 8 }}>
                <div className="prog">
                  <i style={{ width: `${(100 * prog.i) / prog.n}%` }} />
                </div>
                <span className="mono dim">
                  frame {prog.i}/{prog.n} · {prog.row?.state ?? ''} · {prog.fps.toFixed(1)} fps incl. decoding
                </span>
              </div>
            )}

            {/* KPI Summary Cards */}
            {s && (
              <>
                <div className="vb-cards" style={{ marginTop: 10 }}>
                  <Card label="Frames" value={`${s.frames} · ${s.width}×${s.height}`} />
                  <Card label="Detection rate" value={fmtVal(100 * s.detectionRate, 1, '%')} />
                  <Card label="Acquisition" value={fmtVal(s.acquisitionS, 2, 's')} ok={s.acquisitionS !== null && s.acquisitionS <= 2} />
                  <Card label="Lock retention" value={fmtVal(s.lockRetentionPct, 1, '%')} />
                  <Card label="Re-acquisition (worst)" value={fmtVal(s.reacqMaxS, 2, 's')} ok={s.reacqMaxS === null ? undefined : s.reacqMaxS <= 1} />
                  <Card label="Centroid RMSE" value={s.truthProvided ? fmtVal(s.centroidRmsePx, 3, 'px') : 'no truth'} />
                  <Card label="Processing speed" value={fmtVal(s.processingFps, 1, 'FPS')} ok={s.processingFps >= 20} />
                  <Card label="Time per frame" value={fmtVal(s.procMeanMs, 1, 'ms')} />
                </div>

                <div className="row" style={{ marginTop: 8 }}>
                  {result?.analyzer && (
                    <button className="btn sm" onClick={() => download('netra-video-centroid-log.csv', result.analyzer!.csv(), 'text/csv')}>
                      <Icon name="download" size={14} /> Centroid log (CSV)
                    </button>
                  )}
                  {result?.server && (
                    <a className="btn sm" href={result.server.csv} target="_blank" rel="noreferrer">
                      <Icon name="download" size={14} /> Centroid log (CSV)
                    </a>
                  )}
                  <button className="btn sm primary" onClick={() => report('html')}>
                    <Icon name="report" size={14} /> Performance report
                  </button>
                  <button className="btn sm" onClick={() => report('md')}>
                    Markdown
                  </button>
                  <button className="btn sm" onClick={() => report('json')}>
                    JSON
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Card({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className={`vb-card ${ok === undefined ? '' : ok ? 'ok' : 'bad'}`}>
      <div className="eyebrow">{label}</div>
      <div className="v">{value}</div>
    </div>
  );
}

