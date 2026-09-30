/**
 * Scenario presets. Each is a patch on top of DEFAULT_CONFIG; selecting one restarts
 * the run. The same list is served by the FastAPI engine at GET /api/presets.
 */
import { DEFAULT_CONFIG, DeepPartial, SimConfig, cloneConfig, mergeConfig } from './config';

export interface ScenarioPreset {
  id: string;
  name: string;
  summary: string;
  patch: DeepPartial<SimConfig>;
}

export const SCENARIO_PRESETS: ScenarioPreset[] = [
  {
    id: 'open-sky',
    name: 'Clear Link',
    summary: 'Optimal conditions: clear atmospheric window with smooth circular LEO motion (Nominal Reference).',
    patch: {},
  },
  {
    id: 'ps-baseline',
    name: 'PS-169 Std',
    summary: 'Standard mission benchmark: 4°×3° narrow acquisition FOV, 10 px beacon spot, 5 °/s gimbal.',
    patch: { camera: { wideAcquisition: false }, target: { trajectory: 'linear', speedDegS: 0.5 } },
  },
  {
    id: 'moving-platform',
    name: 'Mobile Base',
    summary: 'Vehicular optical terminal: 8 Hz platform vibration, kinematic roll, and aerodynamic wind torque.',
    patch: {
      target: { trajectory: 'figure8', amplitudeDeg: 1.5, periodS: 14 },
      disturbance: { platformMotion: 'circular', platformMotionPx: 12, vibrationPx: 4, vibrationHz: 8, windDegS: 0.25, jitterPx: 3 },
    },
  },
  {
    id: 'high-jitter',
    name: 'High Jitter',
    summary: 'Severe sensor vibration (±20 px/frame) testing the physical stabilization floor of the coarse stage.',
    patch: { disturbance: { jitterPx: 20, vibrationPx: 6, vibrationHz: 12 } },
  },
  {
    id: 'weak-beacon',
    name: 'Haze & Dim',
    summary: 'Low-SNR transmission: heavy haze, 6 px attenuated beacon, strong turbulence, and Gaussian noise.',
    patch: {
      target: { spotSizePx: 6, beaconIntensity: 120, trajectory: 'sinusoidal' },
      disturbance: { atmosphere: 'haze', atmosphereStrength: 0.7, turbulence: 0.6, gaussianNoise: 18, saltPepper: 0.03 },
    },
  },
  {
    id: 'fast-target',
    name: 'Fast Transit',
    summary: 'High-speed angular motion at 1.5 °/s with 10 °/s gimbal dynamics — stresses Kalman rate feed-forward.',
    patch: { target: { trajectory: 'random', speedDegS: 1.5 }, gimbal: { maxRateDegS: 10, maxAccelDegS2: 60 } },
  },
  {
    id: 'acquisition-challenge',
    name: 'Corner Lock',
    summary: 'Offset corner target start with 30 % sensor dropouts, precipitation, and decoy optical reflection.',
    patch: {
      target: { startMode: 'fixed', startUDeg: 5.6, startVDeg: -5.4, trajectory: 'stationary' },
      disturbance: { atmosphere: 'rain', atmosphereStrength: 0.6, dropoutProb: 0.3, decoy: true },
    },
  },
  {
    id: 'occlusion',
    name: 'Cloud Break',
    summary: 'Cloud occlusion masking beacon for 1 s every 6 s, evaluating sub-second reacquisition recovery.',
    patch: { target: { trajectory: 'circular', amplitudeDeg: 1.4, periodS: 14 }, disturbance: { occlusionPeriodS: 6, occlusionDurS: 1 } },
  },
  {
    id: 'leo-pass',
    name: 'LEO Orbit',
    summary: 'True Keplerian orbital overpass at 550 km (62° max elevation) with ephemeris timing bias.',
    patch: { target: { trajectory: 'orbital' } },
  },
];

export function presetConfig(id: string, seed?: number): SimConfig {
  const p = SCENARIO_PRESETS.find((x) => x.id === id) ?? SCENARIO_PRESETS[0];
  const cfg = mergeConfig(cloneConfig(DEFAULT_CONFIG), p.patch);
  cfg.scenarioId = p.id;
  if (seed !== undefined) cfg.seed = seed;
  return cfg;
}
