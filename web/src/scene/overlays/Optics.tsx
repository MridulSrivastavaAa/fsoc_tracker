/**
 * Optical geometry drawn in the scene, all derived from telemetry:
 *   · FOV frustum of the terminal camera (true angles, true range)
 *   · optical axis
 *   · search field of regard and the recent scan path
 *   · beacon trajectory (history) and planned path
 *   · Kalman estimate marker
 *   · beacon illumination cone (divergence exaggerated — labelled in the legend)
 *   · optical link: a red laser (screen-space thick core + glow) with moving data pulses
 */
import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { vis } from '../vis';
import { live, trails, useApp } from '../../state/store';
import { basisFromAzEl, dirFromField } from '../../core/geometry';

const LOGV = /* glsl */ `#include <common>\n#include <logdepthbuf_pars_vertex>`;
const LOGF = /* glsl */ `#include <logdepthbuf_pars_fragment>`;

const beamVertex = /* glsl */ `
${LOGV}
attribute float lineDistance;
varying float vD;
void main() {
  vD = lineDistance;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  #include <logdepthbuf_vertex>
}`;
const beamFragment = /* glsl */ `
${LOGF}
uniform float time;
uniform float len;
uniform vec3 color;
uniform float pulses;
uniform float opacity;
varying float vD;
void main() {
  #include <logdepthbuf_fragment>
  float x = vD / len;
  float p = pulses * pow(0.5 + 0.5 * sin((x * 36.0 - time * 3.0) * 6.2831), 18.0);
  gl_FragColor = vec4(color * (1.0 + 3.0 * p), opacity * (0.55 + 0.45 * p));
}`;

const coneVertex = /* glsl */ `
${LOGV}
varying float vT;
void main() {
  vT = uv.y;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  #include <logdepthbuf_vertex>
}`;
const coneFragment = /* glsl */ `
${LOGF}
uniform vec3 color;
uniform float opacity;
varying float vT;
void main() {
  #include <logdepthbuf_fragment>
  gl_FragColor = vec4(color, opacity * pow(vT, 1.5));
}`;

function makeLine(n: number, color: string, opacity: number, dashed = false) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3));
  g.setDrawRange(0, 0);
  const m = dashed
    ? new THREE.LineDashedMaterial({ color, transparent: true, opacity, dashSize: 4, gapSize: 4, depthWrite: false })
    : new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false });
  const l = new THREE.Line(g, m);
  l.frustumCulled = false;
  return l;
}

export function Optics() {
  const overlays = useApp((s) => s.overlays);
  const cfg = useApp((s) => s.config);

  const frustum = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(5 * 3), 3));
    g.setIndex([
      0, 1, 2,
      0, 2, 3,
      0, 3, 4,
      0, 4, 1,
      1, 2, 3,
      1, 3, 4,
    ]);
    const faces = new THREE.Mesh(
      g,
      new THREE.MeshBasicMaterial({
        color: '#38bdf8',
        transparent: true,
        opacity: 0.05,
        side: THREE.DoubleSide,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    const eg = new THREE.BufferGeometry();
    eg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(32 * 3), 3));
    const edges = new THREE.LineSegments(
      eg,
      new THREE.LineBasicMaterial({
        color: '#38bdf8',
        transparent: true,
        opacity: 0.85,
        depthWrite: false,
      }),
    );
    faces.frustumCulled = edges.frustumCulled = false;
    faces.renderOrder = 1;
    edges.renderOrder = 2;
    return { faces, edges };
  }, []);

  const axis = useMemo(() => makeLine(2, '#e8f6ff', 0.55, true), []);
  const field = useMemo(() => makeLine(5, '#ffb547', 0.35, true), []);
  const scan = useMemo(() => makeLine(30 * 8, '#ffb547', 0.6), []);
  const trail = useMemo(() => makeLine(30 * 25, '#8fdcff', 0.7), []);
  const plan = useMemo(() => makeLine(97, '#8fdcff', 0.25, true), []);

  const beam = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const n = 64;
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    g.setAttribute('lineDistance', new THREE.BufferAttribute(new Float32Array(n), 1));
    const m = new THREE.ShaderMaterial({
      vertexShader: beamVertex,
      fragmentShader: beamFragment,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      toneMapped: false,
      uniforms: { time: { value: 0 }, len: { value: 1 }, color: { value: new THREE.Color('#ff6a5a') }, pulses: { value: 1 }, opacity: { value: 1 } },
    });
    const l = new THREE.Line(g, m);
    l.frustumCulled = false;
    return l;
  }, []);

  // Volumetric 3D Laser Beam Mesh: 100% visible at all distances and zoom levels
  const laserBeam = useMemo(() => {
    const coreGeo = new THREE.CylinderGeometry(0.02, 0.02, 1, 16, 1, true);
    coreGeo.translate(0, 0.5, 0);
    coreGeo.rotateX(Math.PI / 2);
    const coreMat = new THREE.MeshBasicMaterial({
      color: '#ff2222',
      transparent: true,
      opacity: 0.95,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const core = new THREE.Mesh(coreGeo, coreMat);

    const glowGeo = new THREE.CylinderGeometry(0.12, 0.12, 1, 16, 1, true);
    glowGeo.translate(0, 0.5, 0);
    glowGeo.rotateX(Math.PI / 2);
    const glowMat = new THREE.MeshBasicMaterial({
      color: '#ff4433',
      transparent: true,
      opacity: 0.38,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const glow = new THREE.Mesh(glowGeo, glowMat);

    const group = new THREE.Group();
    group.add(core);
    group.add(glow);
    group.frustumCulled = false;
    core.frustumCulled = false;
    glow.frustumCulled = false;
    group.renderOrder = 3;
    return { group, core, glow, coreMat, glowMat };
  }, []);

  const cone = useMemo(() => {
    const g = new THREE.CylinderGeometry(0, 1, 1, 48, 1, true);
    g.translate(0, -0.5, 0); // apex at origin, opening toward −y
    const m = new THREE.ShaderMaterial({
      vertexShader: coneVertex,
      fragmentShader: coneFragment,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      uniforms: { color: { value: new THREE.Color('#ff4a3a') }, opacity: { value: 0.07 } },
    });
    // CylinderGeometry uv.y is 1 at the apex (satellite) and 0 at the base → fades toward the ground.
    const mesh = new THREE.Mesh(g, m);
    mesh.frustumCulled = false;
    return mesh;
  }, []);

  const aperture = useMemo(() => {
    const g = new THREE.RingGeometry(0.005, 0.025, 32);
    const m = new THREE.MeshBasicMaterial({
      color: '#38bdf8',
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.95,
      blending: THREE.AdditiveBlending,
    });
    const mesh = new THREE.Mesh(g, m);
    mesh.frustumCulled = false;
    mesh.renderOrder = 4;
    return mesh;
  }, []);

  const est = useRef<THREE.Mesh>(null);
  const tmp = useMemo(() => ({ f: new THREE.Vector3(), r: new THREE.Vector3(), u: new THREE.Vector3(), p: new THREE.Vector3(), q: new THREE.Quaternion(), m: new THREE.Matrix4() }), []);

  useFrame((state) => {
    const L = vis.range;
    const apex = vis.lens;
    const isLocked = vis.state === 'LOCKED';

    // ── FOV frustum (3D focal vision box) ──────────────────────────
    // LOCKED → derive forward from lens→sat (world-space), guaranteed pixel-perfect.
    // Scanning / Acquiring → use vis.lensDir (read from physical 3D model each frame)
    //   so the frustum dynamically sweeps with the gimbal during search.
    if (isLocked) {
      tmp.f.copy(vis.sat).sub(apex).normalize();
    } else {
      tmp.f.copy(vis.lensDir);
    }
    // Build stable right/up basis orthogonal to the forward direction.
    // Fall back to world-east when beam is near-vertical.
    const worldUp = new THREE.Vector3(0, 1, 0);
    const upDot = Math.abs(tmp.f.dot(worldUp));
    const worldRef = upDot > 0.99 ? new THREE.Vector3(1, 0, 0) : worldUp;
    tmp.r.copy(tmp.f).cross(worldRef).negate().normalize();
    tmp.u.copy(tmp.r).cross(tmp.f).normalize();

    const th = Math.tan(THREE.MathUtils.degToRad(vis.hfov / 2));
    const tv = Math.tan(THREE.MathUtils.degToRad(vis.vfov / 2));
    const corner = (dist: number, sx: number, sy: number) =>
      tmp.p.copy(apex).addScaledVector(tmp.f, dist).addScaledVector(tmp.r, sx * th * dist).addScaledVector(tmp.u, sy * tv * dist).clone();
    
    // Far camera FOV rectangle at satellite range
    const c1 = corner(L, -1, -1);
    const c2 = corner(L, 1, -1);
    const c3 = corner(L, 1, 1);
    const c4 = corner(L, -1, 1);

    // Mid camera FOV rectangle at 20% range or 5 km
    const Lmid = Math.max(5, L * 0.2);
    const m1 = corner(Lmid, -1, -1);
    const m2 = corner(Lmid, 1, -1);
    const m3 = corner(Lmid, 1, 1);
    const m4 = corner(Lmid, -1, 1);

    // Near camera FOV aperture rectangle (50m = 0.05 km) so frustum is prominent at the terminal
    const Lnear = Math.min(0.06, L * 0.01);
    const n1 = corner(Lnear, -1, -1);
    const n2 = corner(Lnear, 1, -1);
    const n3 = corner(Lnear, 1, 1);
    const n4 = corner(Lnear, -1, 1);

    const fp = frustum.faces.geometry.attributes.position as THREE.BufferAttribute;
    [apex, c1, c2, c3, c4].forEach((v, i) => fp.setXYZ(i, v.x, v.y, v.z));
    fp.needsUpdate = true;
    const ep = frustum.edges.geometry.attributes.position as THREE.BufferAttribute;
    const segs = [
      apex, c1, apex, c2, apex, c3, apex, c4, // 4 corner sightlines
      n1, n2, n2, n3, n3, n4, n4, n1,         // Near aperture box (50m)
      m1, m2, m2, m3, m3, m4, m4, m1,         // Mid reference box (5km)
      c1, c2, c2, c3, c3, c4, c4, c1,         // Far camera FOV rectangle (780km)
    ];
    segs.forEach((v, i) => ep.setXYZ(i, v.x, v.y, v.z));
    ep.needsUpdate = true;

    // Sleek cyan during search/tracking; Vibrant green ONLY when fully LOCKED.
    const focalCol = isLocked ? '#00ff66' : '#00e5ff';
    (frustum.edges.material as THREE.LineBasicMaterial).color.set(focalCol);
    (frustum.faces.material as THREE.MeshBasicMaterial).color.set(focalCol);
    (frustum.edges.material as THREE.LineBasicMaterial).opacity = isLocked ? 0.98 : 0.85;
    (frustum.faces.material as THREE.MeshBasicMaterial).opacity = isLocked ? 0.22 : 0.15;
    frustum.faces.visible = frustum.edges.visible = overlays.fov && !vis.pov && vis.view !== 'link';

    // Camera aperture ring
    aperture.position.copy(apex);
    aperture.lookAt(tmp.p.copy(apex).add(tmp.f));
    (aperture.material as THREE.MeshBasicMaterial).color.set(focalCol);
    aperture.visible = overlays.fov && !vis.pov && vis.view !== 'link';

    // ── Optical axis (aligned to actual beam direction) ────────────
    const ap = axis.geometry.attributes.position as THREE.BufferAttribute;
    ap.setXYZ(0, apex.x, apex.y, apex.z);
    tmp.p.copy(apex).addScaledVector(tmp.f, L * 1.08);
    ap.setXYZ(1, tmp.p.x, tmp.p.y, tmp.p.z);
    ap.needsUpdate = true;
    axis.geometry.setDrawRange(0, 2);
    axis.computeLineDistances();
    (axis.material as THREE.LineDashedMaterial).dashSize = L * 0.012;
    (axis.material as THREE.LineDashedMaterial).gapSize = L * 0.008;
    axis.visible = overlays.fov && !vis.pov && vis.view !== 'link';

    // ── Search field of regard ────────────────────────────────────
    const ref = basisFromAzEl(vis.refAz, vis.refEl);
    const hu = cfg.logic.searchHalfUDeg;
    const hv = cfg.logic.searchHalfVDeg;
    const fpos = field.geometry.attributes.position as THREE.BufferAttribute;
    [
      [-hu, -hv],
      [hu, -hv],
      [hu, hv],
      [-hu, hv],
      [-hu, -hv],
    ].forEach(([u, v], i) => {
      const d = dirFromField(ref, u, v);
      fpos.setXYZ(i, d[0] * L, d[1] * L, d[2] * L);
    });
    fpos.needsUpdate = true;
    field.geometry.setDrawRange(0, 5);
    field.computeLineDistances();
    (field.material as THREE.LineDashedMaterial).dashSize = L * 0.01;
    (field.material as THREE.LineDashedMaterial).gapSize = L * 0.008;
    const searching = vis.state === 'SEARCHING' || vis.state === 'REACQUIRING' || vis.state === 'DETECTED';
    const close = vis.view === 'link';
    field.visible = overlays.trails && !close;
    (field.material as THREE.LineDashedMaterial).opacity = searching ? 0.55 : 0.18;

    // ── Scan path (recent optical-axis directions at target range) ─
    const sp = scan.geometry.attributes.position as THREE.BufferAttribute;
    const ax = trails.axis;
    const nScan = Math.min(ax.length, sp.count);
    for (let i = 0; i < nScan; i++) {
      const a = ax[ax.length - nScan + i];
      const d = basisFromAzEl(a.az, a.el).f;
      sp.setXYZ(i, d[0] * L, d[1] * L, d[2] * L);
    }
    sp.needsUpdate = true;
    scan.geometry.setDrawRange(0, nScan);
    scan.visible = overlays.trails && !close;
    (scan.material as THREE.LineBasicMaterial).color.set(searching ? '#ffb547' : '#8fdcff');
    (scan.material as THREE.LineBasicMaterial).opacity = searching ? 0.7 : 0.25;

    // ── Target trail + planned path ───────────────────────────────
    const tp = trail.geometry.attributes.position as THREE.BufferAttribute;
    const tt = trails.target;
    const nT = Math.min(tt.length, tp.count);
    for (let i = 0; i < nT; i++) {
      const p = tt[tt.length - nT + i];
      tp.setXYZ(i, p[0], p[1], p[2]);
    }
    tp.needsUpdate = true;
    trail.geometry.setDrawRange(0, nT);
    trail.visible = overlays.trails && !close;
    const pl = live.plan?.path ?? [];
    const pp = plan.geometry.attributes.position as THREE.BufferAttribute;
    const nP = Math.min(pl.length, pp.count);
    for (let i = 0; i < nP; i++) {
      const d = dirFromField(ref, pl[i][0], pl[i][1]);
      pp.setXYZ(i, d[0] * L, d[1] * L, d[2] * L);
    }
    pp.needsUpdate = true;
    plan.geometry.setDrawRange(0, nP);
    plan.computeLineDistances();
    (plan.material as THREE.LineDashedMaterial).dashSize = L * 0.006;
    (plan.material as THREE.LineDashedMaterial).gapSize = L * 0.006;
    plan.visible = overlays.trails && nP > 1 && !close;

    // ── Kalman estimate marker ────────────────────────────────────
    if (est.current) {
      est.current.visible = !!vis.est && overlays.trails && vis.view !== 'link';
      if (vis.est) {
        est.current.position.copy(vis.est).multiplyScalar(L);
        est.current.scale.setScalar(vis.satScale * 0.0012);
        est.current.rotation.y = state.clock.elapsedTime * 1.5;
      }
    }

    // ── Beacon illumination cone (sat → ground) ───────────────────
    const targetPos = (vis.beacon && vis.beacon.lengthSq() > 10) ? vis.beacon : vis.sat;
    tmp.p.copy(vis.lens).sub(targetPos);
    const dist = tmp.p.length();
    cone.position.copy(targetPos);
    tmp.q.setFromUnitVectors(new THREE.Vector3(0, -1, 0), tmp.p.normalize());
    cone.quaternion.copy(tmp.q);
    const halfAngle = 0.012; // rad — exaggerated ×80 vs a 150 µrad beacon for visibility
    cone.scale.set(dist * halfAngle, dist, dist * halfAngle);
    cone.visible = !vis.pov && vis.view !== 'link';
    (cone.material as THREE.ShaderMaterial).uniforms.opacity.value = vis.state === 'LOCKED' ? 0.035 : 0.07;

    // ── 3D Volumetric Laser Beam ──────────────────────────────────
    const hasLaser = vis.state === 'LOCKED' || vis.state === 'TRACKING' || vis.state === 'DETECTED';
    laserBeam.group.visible = !vis.pov && hasLaser && dist > 0.05;
    if (laserBeam.group.visible) {
      laserBeam.group.position.copy(apex);
      laserBeam.group.lookAt(targetPos);
      const radScale = Math.max(0.08, Math.min(2.5, dist * 0.0014));
      laserBeam.core.scale.set(radScale * 0.45, radScale * 0.45, dist);
      laserBeam.glow.scale.set(radScale * 1.6, radScale * 1.6, dist);
      laserBeam.coreMat.color.set(isLocked ? '#ff2222' : '#ff7a30');
      laserBeam.glowMat.color.set(isLocked ? '#ff1100' : '#ff5500');
      laserBeam.coreMat.opacity = isLocked ? 0.98 : 0.70;
      laserBeam.glowMat.opacity = isLocked ? (0.45 + 0.15 * Math.sin(state.clock.elapsedTime * 8)) : 0.25;
    }

    // ── Secondary data pulse beam ─────────────────────────────────
    const tracking = vis.state === 'LOCKED' || vis.state === 'TRACKING';
    beam.visible = tracking && !vis.pov && dist > 0.05;
    if (beam.visible) {
      const bp = beam.geometry.attributes.position as THREE.BufferAttribute;
      const bd = beam.geometry.attributes.lineDistance as THREE.BufferAttribute;
      const n = bp.count;
      for (let i = 0; i < n; i++) {
        const t = i / (n - 1);
        tmp.p.copy(vis.lens).lerp(targetPos, t);
        bp.setXYZ(i, tmp.p.x, tmp.p.y, tmp.p.z);
        bd.setX(i, t * dist);
      }
      bp.needsUpdate = true;
      bd.needsUpdate = true;
      const u = (beam.material as THREE.ShaderMaterial).uniforms;
      u.time.value = state.clock.elapsedTime;
      u.len.value = dist;
      u.pulses.value = isLocked ? 1 : 0;
      u.opacity.value = isLocked ? 0.9 : 0.3;
      u.color.value.set(isLocked ? '#ffd0c8' : '#ff6a5a');
    }
  });

  return (
    <>
      {/* 3D camera FOV frame pyramid extending from telescope into space */}
      <primitive object={frustum.faces} />
      <primitive object={frustum.edges} />
      {/* Precision camera optical aperture ring at terminal telescope */}
      <primitive object={aperture} />
      {/* Clean blue satellite trajectory path */}
      <primitive object={trail} />
      {/* 3D Volumetric Laser Beam (always visible at all ranges and angles) */}
      <primitive object={laserBeam.group} />
      {/* Secondary glowing link pulse beam */}
      <primitive object={beam} />
    </>
  );
}
