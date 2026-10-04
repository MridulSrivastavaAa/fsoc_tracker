/**
 * High-Precision Optical Ground Station (OGS) Tracking Antenna Terminal.
 * Modelled in metres, rendered in km.
 *
 * Gimbal hierarchy (driven by the real-time simulation engine):
 *   BASE (heading 150°, anchor pedestal on reinforced pad)
 *     └─ MOUNT (north-referenced with platform disturbance)
 *          └─ PAN AXIS (rotation about local up = −azimuth)
 *               └─ TILT AXIS (rotation about local east = +elevation)
 *                    └─ PARABOLIC DISH & OPTICAL PAYLOAD:
 *                         - Deep-dish parabolic reflector & sub-reflector
 *                         - High-power FSOC optical laser collimator & beam anchor
 *                         - Co-aligned wide-field acquisition camera pod
 *                         - Pulsed uplink red beacon emitter
 */
import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { RoundedBox } from '@react-three/drei';
import { makeMaterials } from './materials';
import { TERMINAL_HEADING_DEG, vis } from '../vis';
import { useApp } from '../../state/store';

const PEDESTAL_TOP = 3.6; // m above ground
const TILT_AXIS_UP = 1.1; // m above the pan turntable



export function GroundTerminal() {
  const m = useMemo(makeMaterials, []);
  const quality = useApp((s) => s.quality);
  const root = useRef<THREE.Group>(null);
  const mount = useRef<THREE.Group>(null);
  const pan = useRef<THREE.Group>(null);
  const tilt = useRef<THREE.Group>(null);
  const lensAnchor = useRef<THREE.Object3D>(null);
  const lensFwd = useRef<THREE.Object3D>(null); // 1 unit along local beam-forward (-Z) from lensAnchor
  const status = useRef<THREE.MeshStandardMaterial>(null);
  const beaconLamp = useRef<THREE.MeshStandardMaterial>(null);
  const tmp = useMemo(() => new THREE.Vector3(), []);
  const tmp2 = useMemo(() => new THREE.Vector3(), []);

  // Structural conduit routing
  const powerConduit = useMemo(() => {
    const pts = [
      new THREE.Vector3(-2.2, 0.6, 1.4),
      new THREE.Vector3(-1.8, 0.1, 1.2),
      new THREE.Vector3(-1.0, 0.08, 0.6),
      new THREE.Vector3(-0.45, 0.25, 0.2),
      new THREE.Vector3(-0.35, 1.2, 0.0),
    ];
    return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 30, 0.032, 8, false);
  }, []);

  const towerCable = useMemo(() => {
    const pts = [
      new THREE.Vector3(-0.35, 1.2, 0.0),
      new THREE.Vector3(-0.32, 2.4, 0.0),
      new THREE.Vector3(-0.28, 3.4, 0.0),
      new THREE.Vector3(-0.15, 3.8, 0.0),
    ];
    return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 24, 0.024, 8, false);
  }, []);

  useFrame(() => {
    if (!root.current || !pan.current || !tilt.current || !mount.current) return;
    root.current.scale.setScalar(0.001 * vis.terminalScale);
    pan.current.rotation.y = -THREE.MathUtils.degToRad(vis.pan);
    tilt.current.rotation.x = THREE.MathUtils.degToRad(vis.tilt);
    // Platform disturbance tilt
    mount.current.rotation.set(
      THREE.MathUtils.degToRad(vis.dTilt),
      THREE.MathUtils.degToRad(TERMINAL_HEADING_DEG) - THREE.MathUtils.degToRad(vis.dPan),
      0,
    );
    // Force world matrices to propagate the new pan/tilt rotations before reading positions.
    root.current.updateWorldMatrix(true, true);
    if (lensAnchor.current) {
      lensAnchor.current.getWorldPosition(tmp);
      vis.lens.copy(tmp);
    }
    if (lensAnchor.current && lensFwd.current) {
      lensFwd.current.getWorldPosition(tmp2);
      vis.lensDir.copy(tmp2).sub(vis.lens).normalize();
    }
    const isLocked = vis.state === 'LOCKED';
    const col = isLocked ? '#22c55e' : '#facc15';
    if (status.current) {
      status.current.emissive.set(col);
      const blink = !isLocked ? 0.4 + 0.6 * Math.abs(Math.sin(vis.time * 4)) : 1;
      status.current.emissiveIntensity = 3.5 * blink;
    }
    if (beaconLamp.current) {
      beaconLamp.current.emissiveIntensity =
        vis.state === 'LOCKED' ? 6 + 2 * Math.sin(vis.time * 10) : 1.5;
    }
  });

  const heading = -THREE.MathUtils.degToRad(TERMINAL_HEADING_DEG);
  const shadows = quality === 'high';
  const lights = quality !== 'low';

  return (
    <group ref={root}>
      <group rotation={[0, heading, 0]}>
        {/* ── 1. Reinforced Concrete Foundation Pad ───────────────── */}
        {/* Octagonal Foundation Base */}
        <mesh position={[0, 0.12, 0]} receiveShadow>
          <cylinderGeometry args={[3.6, 3.9, 0.24, 8]} />
          <meshStandardMaterial color="#2c333e" roughness={0.88} metalness={0.12} />
        </mesh>
        {/* Inner Pedestal Foundation Ring */}
        <mesh position={[0, 0.28, 0]} receiveShadow castShadow={shadows}>
          <cylinderGeometry args={[1.8, 2.0, 0.16, 24]} />
          <meshStandardMaterial color="#3a4452" roughness={0.8} metalness={0.2} />
        </mesh>
        {/* Grounding & Anchor Flange */}
        <mesh material={m.darkMetal} position={[0, 0.38, 0]}>
          <cylinderGeometry args={[1.35, 1.4, 0.08, 32]} />
        </mesh>
        {/* Foundation Anchor Studs */}
        {Array.from({ length: 12 }, (_, i) => {
          const a = (i / 12) * Math.PI * 2;
          return (
            <mesh
              key={`bolt${i}`}
              material={m.silver}
              position={[Math.cos(a) * 1.25, 0.44, Math.sin(a) * 1.25]}
            >
              <cylinderGeometry args={[0.03, 0.03, 0.08, 8]} />
            </mesh>
          );
        })}

        {/* ── 2. Structural Steel Tower Pedestal ───────────────────── */}
        {/* Main Tapered Pedestal Column */}
        <mesh material={m.whitePaint} position={[0, 1.8, 0]} castShadow={shadows} receiveShadow={shadows}>
          <cylinderGeometry args={[0.65, 1.1, 2.8, 32]} />
        </mesh>
        {/* Pedestal Base Gusset Stiffeners */}
        {Array.from({ length: 8 }, (_, i) => {
          const a = (i / 8) * Math.PI * 2;
          return (
            <mesh
              key={`gusset${i}`}
              material={m.chassis}
              position={[Math.cos(a) * 0.95, 0.85, Math.sin(a) * 0.95]}
              rotation={[0, -a, 0]}
            >
              <boxGeometry args={[0.04, 0.9, 0.45]} />
            </mesh>
          );
        })}
        {/* Pedestal Mid Collar & Service Door */}
        <mesh material={m.frame} position={[0, 1.9, 0]}>
          <cylinderGeometry args={[0.78, 0.8, 0.12, 32]} />
        </mesh>
        <mesh material={m.trim} position={[0.74, 1.3, 0]} rotation={[0, Math.PI / 2, 0]}>
          <boxGeometry args={[0.45, 0.9, 0.04]} />
        </mesh>
        <mesh material={m.orange} position={[0.76, 1.6, 0.14]}>
          <boxGeometry args={[0.02, 0.08, 0.08]} />
        </mesh>

        {/* Access Ladder along Pedestal */}
        <group position={[-0.82, 0.4, 0]} rotation={[0, Math.PI / 2, 0]}>
          {[-0.18, 0.18].map((lx) => (
            <mesh key={`lad_r${lx}`} material={m.frame} position={[lx, 1.4, 0]}>
              <boxGeometry args={[0.03, 2.8, 0.03]} />
            </mesh>
          ))}
          {Array.from({ length: 9 }, (_, i) => (
            <mesh key={`rung${i}`} material={m.frame} position={[0, 0.3 + i * 0.3, 0]} rotation={[0, 0, Math.PI / 2]}>
              <cylinderGeometry args={[0.015, 0.015, 0.36, 8]} />
            </mesh>
          ))}
        </group>

        {/* Top Maintenance Catwalk / Circular Platform */}
        <group position={[0, 3.25, 0]}>
          {/* Grate Platform Ring */}
          <mesh material={m.darkMetal} position={[0, 0, 0]}>
            <cylinderGeometry args={[1.45, 1.45, 0.06, 32]} />
          </mesh>
          <mesh material={m.chassis} position={[0, -0.04, 0]}>
            <cylinderGeometry args={[0.8, 1.45, 0.04, 32]} />
          </mesh>
          {/* Safety Handrail Posts & Rings */}
          {Array.from({ length: 8 }, (_, i) => {
            const a = (i / 8) * Math.PI * 2;
            return (
              <mesh
                key={`post${i}`}
                material={m.frame}
                position={[Math.cos(a) * 1.38, 0.48, Math.sin(a) * 1.38]}
              >
                <cylinderGeometry args={[0.02, 0.02, 0.95, 8]} />
              </mesh>
            );
          })}
          <mesh material={m.frame} position={[0, 0.94, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[1.38, 0.022, 8, 48]} />
          </mesh>
          <mesh material={m.frame} position={[0, 0.5, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[1.38, 0.016, 8, 48]} />
          </mesh>
          {/* Toe kick plate */}
          <mesh material={m.chassis} position={[0, 0.08, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[1.42, 1.42, 0.12, 32, 1, true]} />
          </mesh>
        </group>

        {/* Cable conduits */}
        <mesh geometry={powerConduit} material={m.cable} />
        <mesh geometry={towerCable} material={m.cable} />

        {/* ── 3. Gimbal Assembly: Pier Top Mount & Azimuth Turntable ─ */}
        <group position={[0, PEDESTAL_TOP, 0]}>
          <group ref={mount}>
            {/* Base Bearing Collar */}
            <mesh material={m.darkMetal} position={[0, 0.06, 0]}>
              <cylinderGeometry args={[0.55, 0.62, 0.12, 36]} />
            </mesh>

            {/* ── PAN / AZIMUTH TURNTABLE (Rotates about local Y = -Azimuth) ─ */}
            <group ref={pan}>
              {/* Azimuth Slew Bearing Ring */}
              <mesh material={m.chassis} position={[0, 0.2, 0]} castShadow={shadows}>
                <cylinderGeometry args={[0.68, 0.68, 0.18, 48]} />
              </mesh>
              <mesh material={m.silver} position={[0, 0.2, 0]} rotation={[Math.PI / 2, 0, 0]}>
                <torusGeometry args={[0.685, 0.018, 12, 64]} />
              </mesh>
              {/* Dual Azimuth Drive Motor Pods */}
              {[-0.58, 0.58].map((dx) => (
                <group key={`az_mot_${dx}`} position={[dx, 0.18, 0.42]}>
                  <mesh material={m.darkMetal}>
                    <cylinderGeometry args={[0.11, 0.11, 0.28, 20]} />
                  </mesh>
                  <mesh material={m.trim} position={[0, 0.16, 0]}>
                    <boxGeometry args={[0.16, 0.08, 0.16]} />
                  </mesh>
                </group>
              ))}

              {/* Dynamic 360° Tracking State Indicator Ring */}
              <mesh position={[0, 0.31, 0]} rotation={[Math.PI / 2, 0, 0]}>
                <torusGeometry args={[0.62, 0.024, 12, 64]} />
                <meshStandardMaterial
                  ref={status}
                  color="#111"
                  emissive="#ffb547"
                  emissiveIntensity={3.5}
                  toneMapped={false}
                />
              </mesh>

              {/* Yoke Platform Baseplate */}
              <mesh material={m.whitePaint} position={[0, 0.38, 0]}>
                <boxGeometry args={[1.7, 0.14, 0.8]} />
              </mesh>
              <mesh material={m.frame} position={[0, 0.46, 0]}>
                <boxGeometry args={[1.5, 0.04, 0.65]} />
              </mesh>

              {/* Dual Heavy Elevation Fork Arms (Left & Right) */}
              {[-1, 1].map((sx) => (
                <group key={`fork_${sx}`} position={[sx * 0.72, 0.45, 0]}>
                  {/* Vertical Arm Upright */}
                  <mesh material={m.whitePaint} position={[0, 0.62, 0]} castShadow={shadows}>
                    <boxGeometry args={[0.18, 1.1, 0.48]} />
                  </mesh>
                  {/* Outer Arm Stiffener Taper */}
                  <mesh material={m.frame} position={[sx * 0.095, 0.58, 0]}>
                    <boxGeometry args={[0.02, 0.95, 0.38]} />
                  </mesh>
                  {/* Diagonal Strut to Base */}
                  <mesh
                    material={m.frame}
                    position={[-sx * 0.18, 0.15, 0]}
                    rotation={[0, 0, sx * 0.45]}
                  >
                    <boxGeometry args={[0.08, 0.5, 0.36]} />
                  </mesh>
                </group>
              ))}

              {/* ── TILT / ELEVATION AXIS + PARABOLIC DISH ASSEMBLY ── */}
              <group ref={tilt} position={[0, TILT_AXIS_UP + 0.52, 0]}>
                {/* Heavy Elevation Trunnion Cross-Shaft */}
                <mesh material={m.silver} rotation={[0, 0, Math.PI / 2]}>
                  <cylinderGeometry args={[0.07, 0.07, 1.5, 24]} />
                </mesh>

                {/* Elevation Gearbox / Actuator Hubs on both fork sides */}
                {[-1, 1].map((sx) => (
                  <group key={`el_hub_${sx}`} position={[sx * 0.76, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
                    <mesh material={m.darkMetal}>
                      <cylinderGeometry args={[0.22, 0.22, 0.16, 32]} />
                    </mesh>
                    <mesh material={m.silver} position={[0, sx * 0.09, 0]}>
                      <cylinderGeometry args={[0.14, 0.14, 0.04, 24]} />
                    </mesh>
                    <mesh position={[0, sx * 0.115, 0]}>
                      <cylinderGeometry args={[0.09, 0.09, 0.02, 24]} />
                      <meshStandardMaterial
                        color="#38bdf8"
                        emissive="#0284c7"
                        emissiveIntensity={0.8}
                        metalness={0.6}
                        roughness={0.2}
                      />
                    </mesh>
                  </group>
                ))}

                {/* ── PARABOLIC TRACKING ANTENNA DISH ──────────────── */}
                {/* Main Dish Reflector Bowl (facing along −Z) */}
                <group position={[0, 0, 0]}>
                  {/* Deep parabolic dish curved shell */}
                  <mesh rotation={[Math.PI / 2, 0, 0]} castShadow={shadows}>
                    <sphereGeometry args={[2.0, 48, 24, 0, Math.PI * 2, 0, Math.PI * 0.42]} />
                    <meshStandardMaterial
                      color="#f8fafc"
                      roughness={0.18}
                      metalness={0.25}
                      side={THREE.DoubleSide}
                    />
                  </mesh>

                  {/* High-Reflectivity Inner Optical / RF Focal Surface */}
                  <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, 0, -0.01]}>
                    <sphereGeometry args={[1.96, 40, 20, 0, Math.PI * 2, 0, Math.PI * 0.4]} />
                    <meshStandardMaterial
                      color="#ffffff"
                      roughness={0.08}
                      metalness={0.85}
                      side={THREE.FrontSide}
                    />
                  </mesh>

                  {/* Dish Perimeter Rim Ring */}
                  <mesh position={[0, 0, -0.92]} rotation={[Math.PI / 2, 0, 0]}>
                    <torusGeometry args={[1.98, 0.038, 16, 64]} />
                    <meshStandardMaterial color="#0284c7" metalness={0.7} roughness={0.3} />
                  </mesh>
                  <mesh position={[0, 0, -0.92]} rotation={[Math.PI / 2, 0, 0]}>
                    <torusGeometry args={[1.93, 0.02, 12, 64]} />
                    <meshStandardMaterial color="#23272c" metalness={0.5} roughness={0.5} />
                  </mesh>

                  {/* Rear Radial Backing Truss Ribs */}
                  {Array.from({ length: 12 }, (_, i) => {
                    const a = (i / 12) * Math.PI * 2;
                    return (
                      <group key={`rib_${i}`} rotation={[0, 0, a]}>
                        <mesh
                          material={m.frame}
                          position={[0.95, 0, 0.42]}
                          rotation={[0, 0.45, 0]}
                        >
                          <boxGeometry args={[1.3, 0.035, 0.12]} />
                        </mesh>
                        <mesh
                          material={m.darkMetal}
                          position={[1.5, 0, 0.15]}
                          rotation={[0, 0.95, 0]}
                        >
                          <boxGeometry args={[0.7, 0.025, 0.06]} />
                        </mesh>
                      </group>
                    );
                  })}

                  {/* Rear Structural Support Ring */}
                  <mesh position={[0, 0, 0.45]} rotation={[Math.PI / 2, 0, 0]}>
                    <torusGeometry args={[0.92, 0.045, 12, 48]} />
                    <meshStandardMaterial color="#1e293b" metalness={0.8} roughness={0.3} />
                  </mesh>

                  {/* Rear Electronics & Counterweight Pod */}
                  <mesh material={m.darkMetal} position={[0, 0, 0.68]} rotation={[Math.PI / 2, 0, 0]} castShadow={shadows}>
                    <cylinderGeometry args={[0.55, 0.62, 0.38, 32]} />
                  </mesh>
                  <RoundedBox
                    args={[0.85, 0.55, 0.4]}
                    radius={0.05}
                    smoothness={2}
                    position={[0, -0.22, 0.85]}
                    material={m.trim}
                    castShadow={shadows}
                  />
                  {/* Status LEDs on Electronics Bay */}
                  {[-0.14, 0, 0.14].map((x, i) => (
                    <mesh key={`el_led_${x}`} position={[x, -0.1, 1.06]}>
                      <sphereGeometry args={[0.016, 8, 8]} />
                      <meshStandardMaterial
                        color="#111"
                        emissive={['#9cf5c8', '#8fdcff', '#ffb547'][i]}
                        emissiveIntensity={3}
                        toneMapped={false}
                      />
                    </mesh>
                  ))}
                </group>

                {/* ── Sub-Reflector Quadripod Support Struts ────────── */}
                {[0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2].map((angle, i) => {
                  const r = 1.9;
                  const x = Math.cos(angle) * r;
                  const y = Math.sin(angle) * r;
                  return (
                    <group key={`strut_${i}`}>
                      <mesh
                        material={m.blackAnod}
                        position={[x * 0.5, y * 0.5, -1.35]}
                        rotation={[
                          (y / r) * 0.52,
                          -(x / r) * 0.52,
                          angle,
                        ]}
                      >
                        <cylinderGeometry args={[0.024, 0.032, 2.2, 12]} />
                      </mesh>
                    </group>
                  );
                })}

                {/* Secondary Cassegrain Sub-Reflector Cone (at focus) */}
                <group position={[0, 0, -2.15]}>
                  {/* Sub-reflector apex cone */}
                  <mesh rotation={[-Math.PI / 2, 0, 0]}>
                    <cylinderGeometry args={[0.04, 0.28, 0.18, 24]} />
                    <meshStandardMaterial color="#0f172a" metalness={0.9} roughness={0.15} />
                  </mesh>
                  {/* Secondary Reflector Surface */}
                  <mesh position={[0, 0, 0.08]} rotation={[Math.PI / 2, 0, 0]}>
                    <cylinderGeometry args={[0.26, 0.26, 0.02, 32]} />
                    <meshStandardMaterial color="#38bdf8" metalness={0.95} roughness={0.1} />
                  </mesh>
                </group>

                {/* ── Central FSOC Optical Collimator & Laser Feed Horn ─ */}
                <group position={[0, 0, -0.45]}>
                  {/* Central Feed Horn Housing */}
                  <mesh material={m.darkMetal} rotation={[Math.PI / 2, 0, 0]}>
                    <cylinderGeometry args={[0.28, 0.35, 0.7, 32]} />
                  </mesh>
                  <mesh material={m.blackAnod} position={[0, 0, -0.4]} rotation={[Math.PI / 2, 0, 0]}>
                    <cylinderGeometry args={[0.18, 0.26, 0.24, 32]} />
                  </mesh>

                  {/* Optical Laser Collimation Lens */}
                  <mesh material={m.lens} position={[0, 0, -0.53]} rotation={[Math.PI / 2, 0, 0]}>
                    <circleGeometry args={[0.16, 32]} />
                  </mesh>
                  {/* Anti-reflective Lens Bezel Ring */}
                  <mesh position={[0, 0, -0.535]} rotation={[Math.PI / 2, 0, 0]}>
                    <torusGeometry args={[0.165, 0.015, 12, 32]} />
                    <meshStandardMaterial color="#0284c7" metalness={0.8} roughness={0.2} />
                  </mesh>

                  {/* LASER BEAM ANCHOR (Points directly along −Z where the FSOC beam fires) */}
                  <object3D ref={lensAnchor} position={[0, 0, -1.75]} />
                  {/* 1 unit further along local beam axis (−Z) — used to derive vis.lensDir */}
                  <object3D ref={lensFwd} position={[0, 0, -2.75]} />
                </group>

                {/* ── Co-Aligned Sensor Pods on Antenna Dish ───────── */}
                {/* 1. Wide-Field Acquisition Camera Pod (Top Rim) */}
                <group position={[0, 1.45, -0.65]}>
                  <mesh material={m.blackAnod}>
                    <boxGeometry args={[0.18, 0.16, 0.42]} />
                  </mesh>
                  <mesh material={m.blackAnod} position={[0, 0, -0.25]} rotation={[Math.PI / 2, 0, 0]}>
                    <cylinderGeometry args={[0.07, 0.065, 0.14, 20]} />
                  </mesh>
                  <mesh material={m.lens} position={[0, 0, -0.322]}>
                    <circleGeometry args={[0.06, 24]} />
                  </mesh>
                  <mesh material={m.darkMetal} position={[0, -0.12, 0]}>
                    <boxGeometry args={[0.08, 0.08, 0.16]} />
                  </mesh>
                </group>

                {/* 2. Uplink Beacon Laser Collimator (Right Rim) */}
                <group position={[1.45, 0, -0.65]} rotation={[0, 0, -Math.PI / 2]}>
                  <mesh material={m.silver} rotation={[Math.PI / 2, 0, 0]}>
                    <cylinderGeometry args={[0.06, 0.06, 0.45, 16]} />
                  </mesh>
                  <mesh position={[0, 0, -0.23]}>
                    <circleGeometry args={[0.05, 16]} />
                    <meshStandardMaterial
                      ref={beaconLamp}
                      color="#ff2a2a"
                      emissive="#ff1a1a"
                      emissiveIntensity={1.5}
                      toneMapped={false}
                      side={THREE.DoubleSide}
                    />
                  </mesh>
                </group>

                {/* 3. Atmospheric Turbulence / Met Sensor (Left Rim) */}
                <group position={[-1.45, 0, -0.65]}>
                  <mesh material={m.darkMetal}>
                    <boxGeometry args={[0.14, 0.14, 0.32]} />
                  </mesh>
                  <mesh material={m.silver} position={[0, 0, -0.2]} rotation={[Math.PI / 2, 0, 0]}>
                    <cylinderGeometry args={[0.03, 0.03, 0.12, 12]} />
                  </mesh>
                </group>
              </group>
            </group>
          </group>
        </group>



        {/* Perimeter Floodlight Mast */}
        <group position={[3.2, 0, -1.8]}>
          <mesh material={m.chassis} position={[0, 0.15, 0]}>
            <cylinderGeometry args={[0.3, 0.35, 0.3, 12]} />
          </mesh>
          <mesh material={m.silver} position={[0, 2.5, 0]}>
            <cylinderGeometry args={[0.04, 0.05, 4.8, 12]} />
          </mesh>
          {/* Dual LED Floodlight Fixtures */}
          <group position={[0, 4.8, 0]} rotation={[0.4, -0.85, 0]}>
            <mesh material={m.trim}>
              <boxGeometry args={[0.6, 0.38, 0.18]} />
            </mesh>
            <mesh material={m.headlight} position={[0, 0, -0.095]}>
              <planeGeometry args={[0.54, 0.32]} />
            </mesh>
          </group>
          {lights && (
            <pointLight
              position={[-0.6, 4.5, 0.6]}
              color="#ffe0b0"
              intensity={7e-5}
              distance={0.05}
              decay={2}
            />
          )}
        </group>


      </group>
    </group>
  );
}
