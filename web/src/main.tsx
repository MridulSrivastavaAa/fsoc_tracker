import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/space-grotesk/400.css';
import '@fontsource/space-grotesk/500.css';
import '@fontsource/space-grotesk/600.css';
import '@fontsource/space-grotesk/700.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import '@fontsource/jetbrains-mono/600.css';
import '@fontsource/jetbrains-mono/700.css';
import './styles/netra.css';
import App from './app/App';

function webglAvailable(): boolean {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch {
    return false;
  }
}

const root = createRoot(document.getElementById('root')!);
if (!webglAvailable()) {
  root.render(
    <div style={{ padding: 40, fontFamily: '"Space Grotesk", sans-serif', color: '#e8f0f7', maxWidth: 640 }}>
      <h2 style={{ letterSpacing: '0.3em' }}>NETRA</h2>
      <p>WebGL is not available in this browser, so the 3D view cannot start.</p>
      <p>Enable hardware acceleration (Chrome: Settings ▸ System ▸ "Use graphics acceleration when available"), update your graphics driver, or try another browser. See README → Troubleshooting.</p>
    </div>,
  );
} else {
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
