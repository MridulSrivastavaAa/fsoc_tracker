/**
 * Space environment: other traffic and natural objects around the link.
 *
 * Purely visual. None of these objects enter the simulated sensor image or the
 * tracking loop (the sensor frame is rendered by the simulation core), so they cannot
 * change any measured result. They make the scene read like real near-Earth space:
 *
 *  - SAT-3, a data-relay satellite with two reflectors and an optical ISL terminal (1,100 km)
 *  - meteors in the upper atmosphere, auroral ovals at both poles, and the Andromeda
 *    galaxy and Magellanic Clouds
 *
 * Orbital speeds are real (v = √(μ/r)); each spacecraft repeats a pass over the region
 * the link is looking at, so the traffic stays in view. Deep-sky positions are
 * approximate (no sidereal time) — the View drawer says so.
 */
import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { makeMaterials } from '../models/materials';
import { vis } from '../vis';
import { EARTH_CENTER, EARTH_R, azElVec, earthQuaternion, iconicScale } from '../world';
import { passIndex, passState, type Pass } from './orbits';
import { useApp } from '../../state/store';
import { NOISE_GLSL } from '../shaders/noise';
import { SUN_DIR as SUN } from '../models/Satellite';

type M = ReturnType<typeof makeMaterials>;
/** Orient a body: +y radial (zenith), +z along-track. */
const oy = new THREE.Vector3();
const oz = new THREE.Vector3();
const ox = new THREE.Vector3();
const om = new THREE.Matrix4();
function orient(q: THREE.Quaternion, pos: THREE.Vector3, vel: THREE.Vector3) {
  oy.copy(pos).sub(EARTH_CENTER).normalize();
  oz.copy(vel);
  ox.crossVectors(oy, oz).normalize();
  oz.crossVectors(ox, oy).normalize();
  q.setFromRotationMatrix(om.makeBasis(ox, oy, oz));
}

/** Shared per-frame driver for a pass-flying object. */
function usePassDriver(pass: Pass, realSizeKm: number, minAng: number, labelKey: string | null) {
  const root = useRef<THREE.Group>(null);
  const st = useMemo(() => ({ pos: new THREE.Vector3(), vel: new THREE.Vector3(), q: new THREE.Quaternion(), base: -1 }), []);
  useFrame((state) => {
    const g = root.current;
    if (!g) return;
    const { config, view, followKey } = useApp.getState();
    const followed = view === 'follow' && followKey === labelKey;
    const t = state.clock.elapsedTime;
    if (followed && st.base < 0) st.base = passIndex(pass, t, config.scene.losAzDeg, config.scene.losElDeg);
    if (!followed) st.base = -1;
    const fade = passState(pass, t, config.scene.losAzDeg, config.scene.losElDeg, st.pos, st.vel, !followed, Math.max(0, st.base));
    g.position.copy(st.pos);
    if (labelKey) {
      const b = (spaceBodies[labelKey] ??= { pos: new THREE.Vector3(), vel: new THREE.Vector3(), sizeKm: realSizeKm });
      b.pos.copy(st.pos);
      b.vel.copy(st.vel);
    }
    orient(st.q, st.pos, st.vel);
    g.quaternion.copy(st.q);
    const d = state.camera.position.distanceTo(st.pos);
    const sc = (followed ? 1 : iconicScale(realSizeKm, d, vis.pov ? minAng * 0.15 : minAng)) * 0.001 * fade;
    g.scale.setScalar(Math.max(sc, 1e-9));
    g.visible = fade > 0.01;
    if (labelKey) {
      const a = (spaceAnchors[labelKey] ??= new THREE.Vector3());
      a.copy(st.pos).sub(EARTH_CENTER).normalize().multiplyScalar(realSizeKm * 0.6 * (sc / 0.001)).add(st.pos);
      anchorOn[labelKey] = g.visible && fade > 0.3;
    }
  }, -3); // before the camera rig, so a following camera sees this frame's position
  return root;
}

/** Label anchors for the space objects (read by the label projector). */
export const spaceAnchors: Record<string, THREE.Vector3> = {};
export const anchorOn: Record<string, boolean> = {};
/** Current position and velocity direction of each named body (read by the follow camera). */
export const spaceBodies: Record<string, { pos: THREE.Vector3; vel: THREE.Vector3; sizeKm: number }> = {};
export const SPACE_TAGS = [
  { key: 'sat3', title: 'SAT-3', sub: 'Data relay · 1,100 km' },
] as const;

/* ----------------------------------------------------------------- SAT-3 ---- */

function RelaySat({ m }: { m: M }) {
  const root = usePassDriver({ altKm: 1100, headingDeg: 292, offsetKm: 520, halfArcDeg: 16, phase: 0.72 }, 0.016, 0.032, 'sat3');
  const wings = [useRef<THREE.Group>(null), useRef<THREE.Group>(null)];
  useFrame(() => {
    if (!root.current) return;
    const s = SUN.clone().applyQuaternion(root.current.quaternion.clone().invert());
    const a = Math.atan2(s.z, s.y);
    wings.forEach((w) => w.current && (w.current.rotation.x = a));
  });

  const umbrellaDish = useMemo(() => {
    const pts: THREE.Vector2[] = [];
    for (let i = 0; i <= 20; i++) {
      const r = (i / 20) * 1.5;
      pts.push(new THREE.Vector2(r, (r * r) / 1.8));
    }
    return new THREE.LatheGeometry(pts, 32);
  }, []);

  return (
    <group ref={root} userData={{ measure: 'obj:sat3', measureName: 'SAT-3 (data relay)' }}>
      {/* Central composite truss bus */}
      <mesh material={m.frame} rotation={[Math.PI / 2, 0, 0]}>
        <boxGeometry args={[0.55, 0.55, 3.6]} />
      </mesh>
      <mesh material={m.darkMetal} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.2, 0.2, 3.8, 16]} />
      </mesh>

      {/* Forward payload module with optical ISL gimbal & laser terminal */}
      <group position={[0, 0, 1.9]}>
        <mesh material={m.gold}>
          <boxGeometry args={[1.2, 1.2, 1.0]} />
        </mesh>
        <mesh material={m.silverFoil} position={[0, 0, 0.52]}>
          <boxGeometry args={[1.1, 1.1, 0.06]} />
        </mesh>
        {/* Optical ISL terminal turret */}
        <group position={[0, 0.65, 0]}>
          <mesh material={m.blackAnod}>
            <cylinderGeometry args={[0.2, 0.22, 0.16, 20]} />
          </mesh>
          <mesh material={m.whitePaint} position={[0, 0.15, 0]} rotation={[0.4, 0, 0]}>
            <cylinderGeometry args={[0.12, 0.12, 0.32, 20]} />
          </mesh>
          <mesh material={m.lens} position={[0, 0.28, 0.08]} rotation={[0.4 - Math.PI / 2, 0, 0]}>
            <circleGeometry args={[0.1, 20]} />
          </mesh>
        </group>
      </group>

      {/* Aft propulsion & avionics module */}
      <group position={[0, 0, -1.9]}>
        <mesh material={m.darkMetal}>
          <cylinderGeometry args={[0.65, 0.75, 1.0, 24]} />
        </mesh>
        <mesh material={m.radiator} position={[0, 0, -0.52]} rotation={[Math.PI, 0, 0]}>
          <circleGeometry args={[0.7, 24]} />
        </mesh>
        {/* Dual biprop thruster nozzles */}
        {[-0.25, 0.25].map((x) => (
          <mesh key={x} material={m.silver} position={[x, 0, -0.6]} rotation={[-Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.1, 0.16, 0.2, 16, 1, true]} />
          </mesh>
        ))}
      </group>

      {/* Dual high-gain mesh umbrella reflectors on deployable boom arms */}
      <group position={[1.4, 0.8, 0.3]} rotation={[0.4, -0.6, 0.3]}>
        <mesh material={m.frame} position={[-0.7, -0.4, -0.1]} rotation={[0, 0, -0.6]}>
          <cylinderGeometry args={[0.04, 0.04, 1.6, 8]} />
        </mesh>
        <mesh geometry={umbrellaDish} material={m.gold} />
        <mesh material={m.frame} position={[0, 0, 0.8]}>
          <cylinderGeometry args={[0.02, 0.02, 1.2, 6]} />
        </mesh>
        <mesh material={m.whitePaint} position={[0, 0, 1.2]}>
          <sphereGeometry args={[0.1, 16, 16]} />
        </mesh>
      </group>

      <group position={[-1.4, 0.8, -0.3]} rotation={[0.4, 0.6, -0.3]}>
        <mesh material={m.frame} position={[0.7, -0.4, 0.1]} rotation={[0, 0, 0.6]}>
          <cylinderGeometry args={[0.04, 0.04, 1.6, 8]} />
        </mesh>
        <mesh geometry={umbrellaDish} material={m.gold} />
        <mesh material={m.frame} position={[0, 0, 0.8]}>
          <cylinderGeometry args={[0.02, 0.02, 1.2, 6]} />
        </mesh>
        <mesh material={m.whitePaint} position={[0, 0, 1.2]}>
          <sphereGeometry args={[0.1, 16, 16]} />
        </mesh>
      </group>

      {/* Dual canted V-wings with dark blue triple-junction solar panels */}
      {[1, -1].map((side, k) => (
        <group key={side} position={[side * 0.6, 0, -1.5]}>
          <mesh material={m.darkMetal} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.14, 0.14, 0.22, 16]} />
          </mesh>
          <group ref={wings[k]}>
            {[-0.45, 0.45].map((rotZ, wi) => (
              <group key={wi} rotation={[0, 0, rotZ * side]}>
                <mesh material={m.frame} position={[side * 0.6, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
                  <cylinderGeometry args={[0.03, 0.03, 1.2, 8]} />
                </mesh>
                <group position={[side * 2.0, 0, 0]}>
                  <mesh material={m.cells2} position={[0, 0.014, 0]}>
                    <boxGeometry args={[1.8, 0.014, 1.1]} />
                  </mesh>
                  <mesh material={m.panelBack2} position={[0, -0.008, 0]}>
                    <boxGeometry args={[1.8, 0.02, 1.1]} />
                  </mesh>
                  <mesh material={m.frame}>
                    <boxGeometry args={[1.84, 0.03, 1.14]} />
                  </mesh>
                </group>
              </group>
            ))}
          </group>
        </group>
      ))}
    </group>
  );
}

/* ---------------------------------------------------------------- meteors ---- */

const meteorVertex = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  #include <logdepthbuf_vertex>
}`;
const meteorFragment = /* glsl */ `
#include <logdepthbuf_pars_fragment>
varying vec2 vUv;
uniform float fade;
uniform float head;
void main() {
  #include <logdepthbuf_fragment>
  float along = vUv.x;
  float tail = smoothstep(head - 0.55, head, along) * step(along, head);
  float core = exp(-pow((vUv.y - 0.5) * 7.0, 2.0));
  vec3 col = mix(vec3(0.55, 1.0, 0.75), vec3(1.0, 0.95, 0.85), smoothstep(head - 0.1, head, along));
  gl_FragColor = vec4(col * 2.2, tail * core * fade);
}`;

function Meteors() {
  const mesh = useRef<THREE.Mesh>(null);
  const mat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: meteorVertex,
        fragmentShader: meteorFragment,
        uniforms: { fade: { value: 0 }, head: { value: 0 } },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      }),
    [],
  );
  const st = useMemo(() => ({ t0: -10, dur: 0.9, start: new THREE.Vector3(), dir: new THREE.Vector3(), len: 60, seed: 3, next: 2 }), []);
  useFrame((state) => {
    const m = mesh.current;
    if (!m) return;
    const t = state.clock.elapsedTime;
    if (t > st.next) {
      const r = () => ((st.seed = (st.seed * 16807) % 2147483647) / 2147483647);
      const { losAzDeg } = useApp.getState().config.scene;
      // a streak at 90–110 km altitude, 150–700 km from the site, roughly in the look direction
      const az = losAzDeg + (r() - 0.5) * 120;
      const ground = 150 + r() * 550;
      const h = 90 + r() * 20;
      const a = THREE.MathUtils.degToRad(az);
      st.start.set(Math.sin(a) * ground, h - (ground * ground) / (2 * EARTH_R), -Math.cos(a) * ground);
      st.dir.set(r() - 0.5, -0.35 - r() * 0.3, r() - 0.5).normalize();
      st.len = 40 + r() * 70;
      st.dur = 0.6 + r() * 0.7;
      st.t0 = t;
      st.next = t + 4 + r() * 7;
    }
    const k = (t - st.t0) / st.dur;
    if (k < 0 || k > 1.3) {
      m.visible = false;
      return;
    }
    m.visible = true;
    const mid = st.start.clone().addScaledVector(st.dir, st.len / 2);
    m.position.copy(mid);
    // billboard the quad along the streak direction
    const toCam = state.camera.position.clone().sub(mid).normalize();
    const side = new THREE.Vector3().crossVectors(st.dir, toCam).normalize();
    const n = new THREE.Vector3().crossVectors(side, st.dir).normalize();
    m.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(st.dir, side, n));
    const width = Math.max(0.3, state.camera.position.distanceTo(mid) * 0.0016);
    m.scale.set(st.len, width, 1);
    mat.uniforms.head.value = Math.min(1, k);
    mat.uniforms.fade.value = k < 1 ? 1 : 1 - (k - 1) / 0.3;
  });
  return (
    <mesh ref={mesh} material={mat} renderOrder={3} frustumCulled={false}>
      <planeGeometry args={[1, 1]} />
    </mesh>
  );
}

/* ----------------------------------------------------------------- aurora ---- */

const auroraVertex = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>
varying vec2 vUv;
varying vec3 vP;
void main() {
  vUv = uv; vP = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  #include <logdepthbuf_vertex>
}`;
const auroraFragment = /* glsl */ `
#include <logdepthbuf_pars_fragment>
varying vec2 vUv;
varying vec3 vP;
uniform float time;
${NOISE_GLSL}
void main() {
  #include <logdepthbuf_fragment>
  float ang = atan(vP.z, vP.x);
  float curtain = aq_fbm(vec3(ang * 6.0, time * 0.05, 1.0), 4);
  float rays = 0.6 + 0.4 * sin(ang * 180.0 + curtain * 12.0 + time * 0.3);
  float h = vUv.y;
  float vert = smoothstep(0.0, 0.08, h) * pow(1.0 - h, 1.6);
  float a = smoothstep(0.35, 0.75, curtain) * rays * vert;
  vec3 col = mix(vec3(0.15, 1.0, 0.45), vec3(0.75, 0.25, 0.9), smoothstep(0.35, 0.95, h));
  gl_FragColor = vec4(col * a * 1.6, a);
}`;

function Aurora() {
  const lat = useApp((s) => s.config.scene.siteLatDeg);
  const lon = useApp((s) => s.config.scene.siteLonDeg);
  const q = useMemo(() => earthQuaternion(lat, lon), [lat, lon]);
  const mat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: auroraVertex,
        fragmentShader: auroraFragment,
        uniforms: { time: { value: 0 } },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      }),
    [],
  );
  useFrame((s) => (mat.uniforms.time.value = s.clock.elapsedTime));
  const ovals = [
    { lat: 70, sign: 1 },
    { lat: 70, sign: -1 },
  ];
  return (
    <group position={EARTH_CENTER} quaternion={q}>
      {ovals.map((o) => {
        const phi = THREE.MathUtils.degToRad(o.lat);
        const rr = (EARTH_R + 180) * Math.cos(phi);
        const y = o.sign * (EARTH_R + 180) * Math.sin(phi);
        return (
          <mesh key={o.sign} material={mat} position={[0, y, 0]} rotation={[o.sign > 0 ? 0 : Math.PI, 0, 0]} renderOrder={2}>
            <cylinderGeometry args={[rr, rr * 1.01, 260, 256, 1, true]} />
          </mesh>
        );
      })}
    </group>
  );
}

/* ---------------------------------------------------------------- deep sky ---- */

function galaxyTexture(kind: 'spiral' | 'cloud') {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const x = c.getContext('2d')!;
  let s = kind === 'spiral' ? 5 : 9;
  const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const g = x.createRadialGradient(128, 128, 0, 128, 128, 128);
  if (kind === 'spiral') {
    g.addColorStop(0, 'rgba(255,240,215,0.95)');
    g.addColorStop(0.12, 'rgba(230,215,200,0.45)');
    g.addColorStop(0.45, 'rgba(150,165,210,0.12)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
  } else {
    g.addColorStop(0, 'rgba(210,215,235,0.35)');
    g.addColorStop(0.5, 'rgba(170,180,220,0.14)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
  }
  x.fillStyle = g;
  x.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 900; i++) {
    const a = r() * Math.PI * 2;
    const d = Math.pow(r(), 0.7) * 110;
    x.fillStyle = `rgba(230,230,255,${0.08 * r()})`;
    x.fillRect(128 + Math.cos(a) * d, 128 + Math.sin(a) * d, 1.5, 1.5);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function DeepSky() {
  const tex = useMemo(() => ({ spiral: galaxyTexture('spiral'), cloud: galaxyTexture('cloud') }), []);
  const group = useRef<THREE.Group>(null);
  useFrame((s) => group.current?.position.copy(s.camera.position));
  const R = 90000;
  // Approximate directions for a site at 13° N (no sidereal time in the scene).
  const objs = [
    { name: 'Andromeda galaxy (M31)', az: 18, el: 42, w: 3.2, h: 1.0, rot: 0.6, t: tex.spiral, o: 0.55 },
    { name: 'Large Magellanic Cloud', az: 182, el: 7, w: 9, h: 7, rot: 0.3, t: tex.cloud, o: 0.2 },
    { name: 'Small Magellanic Cloud', az: 166, el: 5, w: 4, h: 3, rot: 0.1, t: tex.cloud, o: 0.16 },
  ];
  return (
    <group ref={group}>
      {objs.map((o) => {
        const p = azElVec(o.az, o.el, R);
        const size = (o.w * Math.PI) / 180 * R;
        return (
          <mesh
            key={o.name}
            position={p}
            renderOrder={-9}
            frustumCulled={false}
            onUpdate={(mm) => {
              mm.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), p.clone().negate().normalize());
              mm.rotateZ(o.rot);
            }}
          >
            <planeGeometry args={[size, (size * o.h) / o.w]} />
            <meshBasicMaterial map={o.t} transparent opacity={o.o} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
          </mesh>
        );
      })}
    </group>
  );
}

/* ---------------------------------------------------------------- root ---- */

export function SpaceEnvironment() {
  const on = useApp((s) => s.overlays.space);
  const m = useMemo(makeMaterials, []);
  if (!on) {
    for (const k of Object.keys(anchorOn)) anchorOn[k] = false;
    return null;
  }
  return (
    <group>
      <RelaySat m={m} />
      <Meteors />
      <Aurora />
      <DeepSky />
    </group>
  );
}
