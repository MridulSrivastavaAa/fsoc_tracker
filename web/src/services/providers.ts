/**
 * TelemetryProvider: the only thing the UI knows about "where the simulation runs".
 *
 *   LocalEngineProvider   Web Worker running the TypeScript engine (default, no backend)
 *   RemoteEngineProvider  FastAPI server over WebSocket (Python engine)
 *   ReplayProvider        plays back a recorded run
 *
 * Swapping providers never requires UI changes.
 */
import type { EngineCommand, EngineMessage } from '../engine/protocol';
import type { Recording } from '../core/telemetry/recorder';

export type ProviderKind = 'local' | 'remote' | 'replay';
export type Listener = (msg: EngineMessage) => void;

export interface TelemetryProvider {
  readonly kind: ProviderKind;
  readonly label: string;
  connect(listener: Listener): Promise<void>;
  send(cmd: EngineCommand): void;
  disconnect(): void;
}

export class LocalEngineProvider implements TelemetryProvider {
  readonly kind = 'local' as const;
  readonly label = 'Local engine (browser worker)';
  private worker: Worker | null = null;

  async connect(listener: Listener) {
    this.worker = new Worker(new URL('../engine/worker.ts', import.meta.url), { type: 'module' });
    this.worker.onmessage = (e: MessageEvent<EngineMessage>) => listener(e.data);
    this.worker.onerror = (e) => listener({ type: 'error', message: `Engine worker error: ${e.message}` });
  }

  send(cmd: EngineCommand) {
    this.worker?.postMessage(cmd);
  }

  disconnect() {
    this.worker?.terminate();
    this.worker = null;
  }
}

/** Binary frame header: 'AQF1' magic, uint16 width, uint16 height, uint32 frame. */
function decodeBinaryFrame(buf: ArrayBuffer): EngineMessage | null {
  const dv = new DataView(buf);
  if (buf.byteLength < 12 || dv.getUint32(0) !== 0x41514631) return null;
  const width = dv.getUint16(4, true);
  const height = dv.getUint16(6, true);
  const frame = dv.getUint32(8, true);
  const data = new Uint8ClampedArray(buf, 12, width * height);
  return { type: 'frame', width, height, frame, data };
}

export class RemoteEngineProvider implements TelemetryProvider {
  readonly kind = 'remote' as const;
  public label: string;
  private ws: WebSocket | null = null;
  private shouldReconnect = false;
  private listener: Listener | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private baseUrl: string) {
    this.label = `Remote engine (${baseUrl})`;
  }

  private tryConnectUrl(targetUrl: string, listener: Listener): Promise<WebSocket> {
    const wsUrl = targetUrl.replace(/^http/, 'ws').replace(/\/$/, '') + '/ws/telemetry';
    return new Promise((resolve, reject) => {
      let settled = false;
      const ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';
      const timeout = setTimeout(() => {
        if (!settled) {
          settled = true;
          try { ws.close(); } catch {}
          reject(new Error(`Timeout connecting to ${wsUrl}`));
        }
      }, 2000);

      ws.onopen = () => {
        if (!settled) {
          settled = true;
          clearTimeout(timeout);
          resolve(ws);
        }
      };

      ws.onerror = () => {
        if (!settled) {
          settled = true;
          clearTimeout(timeout);
          reject(new Error(`WebSocket connection failed: ${wsUrl}`));
        } else {
          listener({ type: 'error', message: 'WebSocket communication error' });
        }
      };

      ws.onclose = (ev) => {
        if (!settled) {
          settled = true;
          clearTimeout(timeout);
          reject(new Error(`WebSocket closed before connecting: ${wsUrl} (code ${ev.code})`));
        } else if (this.shouldReconnect) {
          listener({ type: 'error', message: 'Remote engine disconnected — auto-reconnecting…' });
          this.scheduleReconnect();
        }
      };

      ws.onmessage = (e) => {
        if (typeof e.data === 'string') {
          try {
            listener(JSON.parse(e.data) as EngineMessage);
          } catch {
            /* ignore malformed */
          }
        } else {
          const m = decodeBinaryFrame(e.data as ArrayBuffer);
          if (m) listener(m);
        }
      };
    });
  }

  async connect(listener: Listener): Promise<void> {
    this.listener = listener;
    this.shouldReconnect = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);

    // Robust candidates: primary + IP alternate + port alternate (8000 <-> 8001)
    const candidates: string[] = [];
    const addCandidate = (url: string) => {
      const clean = url.trim().replace(/\/$/, '');
      if (clean && !candidates.includes(clean)) candidates.push(clean);
    };

    addCandidate(this.baseUrl);
    if (this.baseUrl.includes('localhost')) {
      addCandidate(this.baseUrl.replace('localhost', '127.0.0.1'));
    } else if (this.baseUrl.includes('127.0.0.1')) {
      addCandidate(this.baseUrl.replace('127.0.0.1', 'localhost'));
    }

    const currentLen = candidates.length;
    for (let i = 0; i < currentLen; i++) {
      const c = candidates[i];
      if (c.includes(':8000')) addCandidate(c.replace(':8000', ':8001'));
      else if (c.includes(':8001')) addCandidate(c.replace(':8001', ':8000'));
    }

    let lastErr: Error | null = null;
    for (const url of candidates) {
      try {
        const ws = await this.tryConnectUrl(url, listener);
        this.ws = ws;
        this.baseUrl = url;
        this.label = `Remote engine (${url})`;
        return;
      } catch (e) {
        lastErr = e as Error;
      }
    }

    // Schedule auto-reconnect attempt if initial connection fails
    this.scheduleReconnect();
    throw lastErr ?? new Error(`Could not connect to FastAPI server at ${this.baseUrl} or alternate ports`);
  }

  private scheduleReconnect() {
    if (!this.shouldReconnect || this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(async () => {
      this.reconnectTimer = null;
      if (!this.shouldReconnect || !this.listener) return;
      try {
        await this.connect(this.listener);
        this.listener({ type: 'status', running: true, demo: false, fps: 30, timeScale: 1 });
        this.send({ type: 'start' });
      } catch {
        this.scheduleReconnect();
      }
    }, 1500);
  }

  send(cmd: EngineCommand) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(cmd));
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    const ws = this.ws;
    this.ws = null;
    this.listener = null;
    if (ws) {
      ws.onclose = null;
      ws.close();
    }
  }
}

/** Plays a recording back at its original timing (images are not recorded). */
export class ReplayProvider implements TelemetryProvider {
  readonly kind = 'replay' as const;
  readonly label: string;
  private listener: Listener | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private index = 0;
  private playing = true;
  private speed = 1;
  private clock = 0;
  constructor(public readonly recording: Recording) {
    this.label = `Replay · ${recording.name}`;
  }

  get length() {
    return this.recording.frames.length;
  }
  get position() {
    return this.index;
  }
  get isPlaying() {
    return this.playing;
  }

  async connect(listener: Listener) {
    this.listener = listener;
    if (this.recording.config) listener({ type: 'config', config: this.recording.config, version: 1 });
    this.clock = this.recording.frames[0]?.t ?? 0;
    let last = performance.now();
    this.timer = setInterval(() => {
      const now = performance.now();
      const dt = ((now - last) / 1000) * this.speed;
      last = now;
      if (!this.playing) return;
      this.clock += dt;
      const frames = this.recording.frames;
      while (this.index < frames.length - 1 && frames[this.index + 1].t <= this.clock) {
        this.index++;
        this.emit(this.index);
      }
      if (this.index >= frames.length - 1) this.playing = false;
      listener({ type: 'status', running: this.playing, demo: false, fps: this.playing ? 30 : 0, timeScale: this.speed });
    }, 16);
    this.emit(0);
  }

  private emit(i: number) {
    const s = this.recording.frames[i];
    if (s && this.listener) this.listener({ type: 'snapshot', snapshot: { ...s, source: 'replay' } });
  }

  seek(i: number) {
    const frames = this.recording.frames;
    this.index = Math.max(0, Math.min(frames.length - 1, Math.round(i)));
    this.clock = frames[this.index]?.t ?? 0;
    this.emit(this.index);
  }

  send(cmd: EngineCommand) {
    if (cmd.type === 'start') {
      if (this.index >= this.recording.frames.length - 1) this.seek(0);
      this.playing = true;
    } else if (cmd.type === 'pause') this.playing = false;
    else if (cmd.type === 'reset') this.seek(0);
    else if (cmd.type === 'timeScale') this.speed = cmd.value;
  }

  disconnect() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.listener = null;
  }
}

export const DEFAULT_SERVER_URL: string =
  (import.meta.env.VITE_NETRA_SERVER as string | undefined) ?? 'http://localhost:8000';
