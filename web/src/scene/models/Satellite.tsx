/**
 * Remote terminal: a LEO spacecraft carrying an optical communication terminal and
 * the acquisition beacon (modelled in metres, rendered in km with iconic scaling).
 *
 * Layout follows a typical small LEO bus: a box bus wrapped in crinkled gold MLI,
 * white radiators on the anti-sun sides, two deployable solar-array wings (yoke +
 * three hinged panels each) on sun-tracking drives, star trackers, GNSS, an RF dish
 * and, on the nadir deck, the optical head on a two-axis coarse-pointing mount with
 * its red beacon laser.
 *
 * Meaningful animation only: the body stays nadir-pointed, the array drives track the
 * Sun, and the optical head points at the ground terminal.
 */
import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { makeMaterials } from './materials';
import { vis } from '../vis';
import { EARTH_CENTER } from '../world';

type M = ReturnType<typeof makeMaterials>;

const PANEL_W = 1.35; // m along the wing
const PANEL_H = 1.18;
const PANELS = 4;

function Wing({ side, m, wingRef }: { side: 1 | -1; m: M; wingRef: React.RefObject<THREE.Group | null> }) {
  return (
    <group position={[side * 0.76, 0.05, 0]}>
      {/* Heavy-duty solar array drive mechanism (SADM) */}
      <mesh material={m.darkMetal} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.12, 0.14, 0.18, 24]} />
      </mesh>
      <mesh material={m.frame} position={[side * 0.1, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.05, 0.05, 0.1, 16]} />
      </mesh>
      <group ref={wingRef}>
        {/* Articulated dual-truss yoke */}
        <mesh material={m.blackAnod} position={[side * 0.38, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.035, 0.035, 0.65, 12]} />
        </mesh>
        {[-0.28, 0.28].map((sz) => (
          <mesh key={sz} material={m.frame} position={[side * 0.78, 0, sz]} rotation={[0, sz * side * 0.45, Math.PI / 2]}>
            <cylinderGeometry args={[0.018, 0.018, 0.75, 8]} />
          </mesh>
        ))}
        {/* Cross-brace spreader bar */}
        <mesh material={m.frame} position={[side * 1.05, 0, 0]}>
          <boxGeometry args={[0.035, 0.035, 0.72]} />
        </mesh>

        {/* ═══ 4 HIGH-EFFICIENCY RECTANGULAR SOLAR PANELS ═══ */}
        {Array.from({ length: PANELS }, (_, i) => {
          const cx = side * (1.15 + PANEL_W / 2 + i * (PANEL_W + 0.06));
          return (
            <group key={i} position={[cx, 0, 0]}>
              {/* Photovoltaic cell array with anti-reflective glass coat */}
              <mesh material={m.cells2} position={[0, 0.012, 0]}>
                <boxGeometry args={[PANEL_W, 0.012, PANEL_H]} />
              </mesh>
              {/* Lightweight carbon composite substrate backing */}
              <mesh material={m.panelBack2} position={[0, -0.006, 0]}>
                <boxGeometry args={[PANEL_W, 0.018, PANEL_H]} />
              </mesh>
              {/* Perimeter structural framing & beryllium stiffeners */}
              {[-1, 1].map((sz) => (
                <mesh key={sz} material={m.frame} position={[0, 0.005, sz * (PANEL_H / 2)]}>
                  <boxGeometry args={[PANEL_W + 0.02, 0.035, 0.028]} />
                </mesh>
              ))}
              {/* Deployment hinge actuators with rotary dampers between panels */}
              {i < PANELS - 1 &&
                [-0.38, 0.38].map((z) => (
                  <group key={z} position={[side * (PANEL_W / 2 + 0.03), 0, z]}>
                    <mesh material={m.darkMetal}>
                      <boxGeometry args={[0.07, 0.04, 0.1]} />
                    </mesh>
                    <mesh material={m.silver} rotation={[0, 0, Math.PI / 2]}>
                      <cylinderGeometry args={[0.018, 0.018, 0.08, 12]} />
                    </mesh>
                  </group>
                ))}
            </group>
          );
        })}
      </group>
    </group>
  );
}

export function Satellite() {
  const m = useMemo(makeMaterials, []);
  const root = useRef<THREE.Group>(null);
  const body = useRef<THREE.Group>(null);
  const wingL = useRef<THREE.Group>(null);
  const wingR = useRef<THREE.Group>(null);
  const head = useRef<THREE.Group>(null);
  const beacon = useRef<THREE.Sprite>(null);
  const halo = useRef<THREE.Sprite>(null);
  const beaconAnchor = useRef<THREE.Object3D>(null);
  const tmp = useMemo(
    () => ({ x: new THREE.Vector3(), y: new THREE.Vector3(), z: new THREE.Vector3(), mat: new THREE.Matrix4(), q: new THREE.Quaternion(), d: new THREE.Vector3() }),
    [],
  );
  const glow = useMemo(() => {
    const c = document.createElement('canvas');
    c.width = c.height = 128;
    const x = c.getContext('2d')!;
    const g = x.createRadialGradient(64, 64, 0, 64, 64, 64);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(0.12, 'rgba(255,190,190,0.95)');
    g.addColorStop(0.35, 'rgba(255,40,40,0.35)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    x.fillStyle = g;
    x.fillRect(0, 0, 128, 128);
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, []);

  const flag = useMemo(() => {
    const c = document.createElement('canvas');
    c.width = 180;
    c.height = 120;
    const x = c.getContext('2d')!;
    x.fillStyle = '#ff9933';
    x.fillRect(0, 0, 180, 40);
    x.fillStyle = '#ffffff';
    x.fillRect(0, 40, 180, 40);
    x.fillStyle = '#138808';
    x.fillRect(0, 80, 180, 40);
    x.strokeStyle = '#000080';
    x.lineWidth = 2;
    x.beginPath();
    x.arc(90, 60, 15, 0, Math.PI * 2);
    x.stroke();
    for (let i = 0; i < 24; i++) {
      const a = (i / 24) * Math.PI * 2;
      x.beginPath();
      x.moveTo(90, 60);
      x.lineTo(90 + Math.cos(a) * 15, 60 + Math.sin(a) * 15);
      x.lineWidth = 0.8;
      x.stroke();
    }
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, []);

  const dish = useMemo(() => {
    const pts: THREE.Vector2[] = [];
    for (let i = 0; i <= 16; i++) {
      const r = (i / 16) * 0.48;
      pts.push(new THREE.Vector2(r, (r * r) / 0.55));
    }
    return new THREE.LatheGeometry(pts, 40);
  }, []);

  useFrame(() => {
    if (!root.current || !body.current) return;
    root.current.position.copy(vis.sat);
    root.current.scale.setScalar(0.001 * vis.satScale);
    // Nadir pointing: body +y = radial (zenith), body +z roughly along-track.
    tmp.y.copy(vis.sat).sub(EARTH_CENTER).normalize();
    tmp.z.set(0, 0, -1);
    if (vis.satVel.lengthSq() > 1e-8) tmp.z.copy(vis.satVel).normalize();
    tmp.x.crossVectors(tmp.y, tmp.z);
    if (tmp.x.lengthSq() < 1e-6) tmp.x.set(1, 0, 0);
    tmp.x.normalize();
    tmp.z.crossVectors(tmp.x, tmp.y).normalize();
    tmp.mat.makeBasis(tmp.x, tmp.y, tmp.z);
    body.current.quaternion.setFromRotationMatrix(tmp.mat);
    // Solar array drives: rotate each circular wing about body x so the cells face the Sun.
    const sunLocal = SUN_DIR.clone().applyQuaternion(body.current.quaternion.clone().invert());
    const ang = Math.atan2(sunLocal.z, sunLocal.y);
    if (wingL.current) wingL.current.rotation.x = ang;
    if (wingR.current) wingR.current.rotation.x = ang;
    // Optical head: point the telescope (local −z) at the ground terminal.
    if (head.current) {
      tmp.d.copy(vis.lens).sub(vis.sat).normalize().applyQuaternion(body.current.quaternion.clone().invert());
      tmp.q.setFromUnitVectors(new THREE.Vector3(0, 0, -1), tmp.d);
      head.current.quaternion.slerp(tmp.q, 0.2);
    }
    if (beacon.current && beaconAnchor.current) {
      beaconAnchor.current.getWorldPosition(beacon.current.position);
      vis.beacon.copy(beacon.current.position);
      const locked = vis.state === 'LOCKED';
      const s = (locked ? 0.05 : 0.036 + 0.012 * Math.sin(vis.time * 6)) * (vis.pov ? 0.08 : 1) * (vis.view === 'link' ? 0.5 : vis.view === 'orbit' ? 0.45 : 1);
      beacon.current.scale.set(s, s, 1);
      if (halo.current) {
        halo.current.position.copy(beacon.current.position);
        const h = s * (locked ? 1.7 : 1.4);
        halo.current.scale.set(h, h, 1);
        (halo.current.material as THREE.SpriteMaterial).opacity = locked ? 0.3 : 0.2;
      }
    }
  });

  return (
    <>
      <group ref={root} userData={{ measure: 'satellite' }}>
        <group ref={body}>
          {/* ═══ DISTINCT CENTRAL CYLINDRICAL FUSELAGE WITH GOLD MLI CORE ═══ */}
          <mesh material={m.paint} position={[0, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.72, 0.72, 2.2, 32]} />
          </mesh>
          {/* Mid-fuselage Gold MLI Thermal Blanket Segment */}
          <mesh material={m.gold} position={[0, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.735, 0.735, 1.1, 32]} />
          </mesh>
          {/* Titanium structural reinforcement rings */}
          {[-0.6, 0.6].map((z) => (
            <mesh key={z} material={m.darkMetal} position={[0, 0, z]} rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[0.74, 0.035, 12, 36]} />
            </mesh>
          ))}

          {/* Forward Aft Conical Nose Cap */}
          <mesh material={m.silverFoil} position={[0, 0, 1.25]} rotation={[-Math.PI / 2, 0, 0]}>
            <coneGeometry args={[0.72, 0.4, 32]} />
          </mesh>

          {/* Rear Propulsion Bulkhead with Main Ion Thruster Cluster */}
          <group position={[0, 0, -1.15]}>
            <mesh material={m.darkMetal} rotation={[Math.PI / 2, 0, 0]}>
              <cylinderGeometry args={[0.7, 0.65, 0.15, 32]} />
            </mesh>
            {/* 4 Ion Thruster Engine bells */}
            {[
              [-0.25, -0.25],
              [0.25, -0.25],
              [-0.25, 0.25],
              [0.25, 0.25],
            ].map(([x, y]) => (
              <mesh key={`${x}${y}`} material={m.silver} position={[x, y, -0.1]} rotation={[-Math.PI / 2, 0, 0]}>
                <cylinderGeometry args={[0.08, 0.14, 0.18, 16, 1, true]} />
              </mesh>
            ))}
          </group>

          {/* Dual Outrigger Propellant Tanks nestled on sides */}
          {[-1, 1].map((side) => (
            <group key={side} position={[side * 0.75, 0.25, -0.1]}>
              <mesh material={m.silver} rotation={[Math.PI / 2, 0, 0]}>
                <cylinderGeometry args={[0.18, 0.18, 1.2, 24]} />
              </mesh>
              <mesh material={m.silver} position={[0, 0, 0.6]}>
                <sphereGeometry args={[0.18, 24, 16]} />
              </mesh>
              <mesh material={m.silver} position={[0, 0, -0.6]}>
                <sphereGeometry args={[0.18, 24, 16]} />
              </mesh>
              {/* Tank carbon support brackets */}
              {[-0.35, 0.35].map((z) => (
                <mesh key={z} material={m.darkMetal} position={[-side * 0.1, 0, z]}>
                  <boxGeometry args={[0.16, 0.05, 0.08]} />
                </mesh>
              ))}
            </group>
          ))}

          {/* Circular Solar Arrays on ±x */}
          <Wing side={1} m={m} wingRef={wingR} />
          <Wing side={-1} m={m} wingRef={wingL} />

          {/* Forward-facing High-Gain Communications Dish on carbon tripod */}
          <group position={[0, 0.45, 1.4]} rotation={[0.3, 0, 0]}>
            <mesh material={m.frame} position={[0, 0, 0.2]} rotation={[Math.PI / 2, 0, 0]}>
              <cylinderGeometry args={[0.025, 0.025, 0.4, 8]} />
            </mesh>
            <mesh geometry={dish} material={m.whitePaint} position={[0, 0, 0.45]} rotation={[-Math.PI / 2, 0, 0]} />
            <mesh material={m.silver} position={[0, 0, 0.65]}>
              <sphereGeometry args={[0.05, 16, 16]} />
            </mesh>
          </group>

          {/* ═══════════════════════════════════════════════════════════════ */}
          {/* OPTICAL COMMUNICATION TERMINAL (Nadir Deck)                    */}
          {/* 2-Axis Precision Gimbal Turret + Telescope + Laser Beacon      */}
          {/* ═══════════════════════════════════════════════════════════════ */}
          <group position={[0, -0.85, 0.2]}>
            {/* Azimuth swivel base plate */}
            <mesh material={m.darkMetal}>
              <cylinderGeometry args={[0.26, 0.28, 0.16, 32]} />
            </mesh>
            <mesh material={m.frame} position={[0, -0.09, 0]}>
              <cylinderGeometry args={[0.22, 0.22, 0.04, 32]} />
            </mesh>

            {/* Elevation yoke & optical head */}
            <group ref={head} position={[0, -0.24, 0]}>
              {/* Dual-sided gimbal support fork arms */}
              {[-1, 1].map((sx) => (
                <group key={sx} position={[sx * 0.22, 0.05, 0]}>
                  <mesh material={m.blackAnod}>
                    <boxGeometry args={[0.055, 0.28, 0.14]} />
                  </mesh>
                  <mesh material={m.darkMetal} position={[0, -0.06, 0]} rotation={[0, 0, Math.PI / 2]}>
                    <cylinderGeometry args={[0.045, 0.045, 0.07, 16]} />
                  </mesh>
                </group>
              ))}

              {/* Main Telescope Optical Barrel */}
              <mesh material={m.whitePaint} position={[0, 0, -0.06]} rotation={[Math.PI / 2, 0, 0]}>
                <cylinderGeometry args={[0.16, 0.16, 0.54, 32]} />
              </mesh>
              {/* Carbon-fiber sunshield & internal baffle rings */}
              <mesh material={m.blackAnod} position={[0, 0, -0.38]} rotation={[Math.PI / 2, 0, 0]}>
                <cylinderGeometry args={[0.175, 0.165, 0.18, 32, 1, true]} />
              </mesh>
              {/* Multicoated precision objective lens with iridescence reflection */}
              <mesh material={m.lens} position={[0, 0, -0.32]}>
                <circleGeometry args={[0.145, 36]} />
              </mesh>
              {/* Secondary mirror spider support vane */}
              <mesh material={m.frame} position={[0, 0, -0.36]}>
                <boxGeometry args={[0.3, 0.008, 0.008]} />
              </mesh>
              <mesh material={m.frame} position={[0, 0, -0.36]}>
                <boxGeometry args={[0.008, 0.3, 0.008]} />
              </mesh>
              <mesh material={m.silver} position={[0, 0, -0.36]}>
                <cylinderGeometry args={[0.035, 0.035, 0.02, 16]} />
              </mesh>

              {/* Red Beacon Laser Emitter (co-aligned with optical axis) */}
              <group position={[0.12, 0.14, -0.22]}>
                <mesh material={m.darkMetal} rotation={[Math.PI / 2, 0, 0]}>
                  <cylinderGeometry args={[0.04, 0.04, 0.22, 16]} />
                </mesh>
                <mesh material={m.silver} position={[0, 0, -0.12]} rotation={[Math.PI / 2, 0, 0]}>
                  <cylinderGeometry args={[0.045, 0.04, 0.04, 16]} />
                </mesh>
                <mesh material={m.redLaser} position={[0, 0, -0.14]}>
                  <sphereGeometry args={[0.03, 16, 16]} />
                </mesh>
              </group>

              {/* Beacon anchor positioned precisely at laser emitter output */}
              <object3D ref={beaconAnchor} position={[0.12, 0.14, -0.38]} />
            </group>
          </group>

          {/* Star tracker optical heads (dual baffled miniature telescopes looking zenithward) */}
          {[-0.25, 0.25].map((x) => (
            <group key={x} position={[x, 0.82, -0.4]} rotation={[0.4, 0, x * 0.7]}>
              <mesh material={m.blackAnod}>
                <cylinderGeometry args={[0.065, 0.085, 0.26, 16, 1, true]} />
              </mesh>
              <mesh material={m.silver} position={[0, -0.14, 0]}>
                <boxGeometry args={[0.14, 0.06, 0.14]} />
              </mesh>
              <mesh material={m.lens} position={[0, 0.1, 0]} rotation={[Math.PI / 2, 0, 0]}>
                <circleGeometry args={[0.06, 16]} />
              </mesh>
            </group>
          ))}

          {/* National Agency Insignia Decal */}
          <mesh position={[0, 0.73, 0.3]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[0.42, 0.28]} />
            <meshStandardMaterial map={flag} roughness={0.5} metalness={0} />
          </mesh>
        </group>
      </group>
      {/* Precision Beacon Glow and Ray halo outside scaled model */}
      <sprite ref={halo} renderOrder={4}>
        <spriteMaterial map={glow} color={[3, 0.25, 0.2]} sizeAttenuation={false} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} transparent opacity={0.3} />
      </sprite>
      <sprite ref={beacon} renderOrder={5}>
        <spriteMaterial map={glow} color={[5, 1.1, 0.9]} sizeAttenuation={false} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
      </sprite>
    </>
  );
}

/** Sun direction shared with the satellite (set by the stage). */
export const SUN_DIR = new THREE.Vector3(0, 1, 0);
