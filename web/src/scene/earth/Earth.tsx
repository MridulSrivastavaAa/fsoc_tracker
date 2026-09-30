/**
 * Basic 3D Earth Globe Model.
 *
 * Provides a clean, performant, accurate-scale Earth sphere with:
 *  - Real geographic continents from Natural Earth topology
 *  - Deep ocean basemap and clean coordinate graticules (Equator, Tropics, Meridians)
 *  - Ground station highlighted at Bengaluru, Karnataka (13.03° N, 77.51° E)
 *  - High-precision local ground terminal site at the origin (0, 0, 0)
 *  - Exact shape & size ratio: EARTH_R = 6,371 km sphere at (0, -EARTH_R, 0)
 */
import { useEffect, useMemo, useState } from 'react';
import * as THREE from 'three';
import { feature } from 'topojson-client';
import type { Topology, GeometryCollection } from 'topojson-specification';
import { EARTH_CENTER, EARTH_R, earthQuaternion } from '../world';
import { useApp } from '../../state/store';

type Ring = [number, number][];

/**
 * Builds a clean, crisp equirectangular Earth texture with real continents,
 * oceans, latitude/longitude graticules, and a prominent marker for Bengaluru, Karnataka.
 */
async function buildGlobeTexture(width = 2048): Promise<THREE.CanvasTexture> {
  const height = width / 2;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d')!;

  // 1. Deep blue oceans
  const oceanGrad = ctx.createLinearGradient(0, 0, 0, height);
  oceanGrad.addColorStop(0, '#102236');
  oceanGrad.addColorStop(0.2, '#142a44');
  oceanGrad.addColorStop(0.5, '#183352');
  oceanGrad.addColorStop(0.8, '#142a44');
  oceanGrad.addColorStop(1, '#102236');
  ctx.fillStyle = oceanGrad;
  ctx.fillRect(0, 0, width, height);

  // Subtle ocean bathymetric texture
  ctx.fillStyle = 'rgba(255, 255, 255, 0.015)';
  for (let y = 0; y < height; y += 4) {
    ctx.fillRect(0, y, width, 1.5);
  }

  // 2. Load and render real world landmasses
  const X = (lon: number) => ((lon + 180) / 360) * width;
  const Y = (lat: number) => ((90 - lat) / 180) * height;

  try {
    const topo = (await import('world-atlas/land-50m.json')).default as unknown as Topology<{ land: GeometryCollection }>;
    const land = feature(topo, topo.objects.land) as unknown as GeoJSON.FeatureCollection;

    const drawRing = (ring: Ring, offset: number) => {
      let prev = ring[0][0];
      let acc = prev;
      ctx.moveTo(X(acc + offset), Y(ring[0][1]));
      const pts: [number, number][] = [[acc, ring[0][1]]];
      for (let i = 1; i < ring.length; i++) {
        let d = ring[i][0] - prev;
        if (d > 180) d -= 360;
        if (d < -180) d += 360;
        acc += d;
        prev = ring[i][0];
        pts.push([acc, ring[i][1]]);
        ctx.lineTo(X(acc + offset), Y(ring[i][1]));
      }
      const span = acc - ring[0][0];
      if (Math.abs(span) > 300) {
        const poleLat = pts.reduce((a, p) => a + p[1], 0) < 0 ? -90 : 90;
        ctx.lineTo(X(acc + offset), Y(poleLat));
        ctx.lineTo(X(ring[0][0] + offset), Y(poleLat));
      }
      ctx.closePath();
    };

    // Draw continent base (lush terrain green)
    ctx.fillStyle = '#2f5a3a';
    for (const f of land.features) {
      const g = f.geometry;
      const polys: Ring[][] = g.type === 'Polygon' ? [g.coordinates as Ring[]] : g.type === 'MultiPolygon' ? (g.coordinates as Ring[][]) : [];
      for (const poly of polys) {
        for (const offset of [-360, 0, 360]) {
          ctx.beginPath();
          for (const ring of poly) drawRing(ring, offset);
          ctx.fill('evenodd');
        }
      }
    }

    // Coastal outline / highlight
    ctx.strokeStyle = '#4e855c';
    ctx.lineWidth = Math.max(1, width / 2048);
    for (const f of land.features) {
      const g = f.geometry;
      const polys: Ring[][] = g.type === 'Polygon' ? [g.coordinates as Ring[]] : g.type === 'MultiPolygon' ? (g.coordinates as Ring[][]) : [];
      for (const poly of polys) {
        for (const offset of [-360, 0, 360]) {
          ctx.beginPath();
          for (const ring of poly) drawRing(ring, offset);
          ctx.stroke();
        }
      }
    }
  } catch (err) {
    console.warn('Fallback continent rendering', err);
    // Procedural fallback continents
    ctx.fillStyle = '#2f5a3a';
    ctx.fillRect(X(60), Y(38), width * 0.15, height * 0.35); // Asia/India approximate
  }

  // 3. Coordinate Graticules & Reference Lines
  // 30° Latitudes / Longitudes
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
  ctx.lineWidth = 1;
  ctx.setLineDash([]);
  for (let lat = -60; lat <= 60; lat += 30) {
    if (lat === 0) continue;
    ctx.beginPath();
    ctx.moveTo(0, Y(lat));
    ctx.lineTo(width, Y(lat));
    ctx.stroke();
  }
  for (let lon = -150; lon <= 180; lon += 30) {
    ctx.beginPath();
    ctx.moveTo(X(lon), 0);
    ctx.lineTo(X(lon), height);
    ctx.stroke();
  }

  // Tropics (±23.44°) & Polar circles (±66.56°)
  ctx.strokeStyle = 'rgba(245, 185, 66, 0.35)'; // gold
  ctx.setLineDash([4, 4]);
  for (const tLat of [-66.56, -23.44, 23.44, 66.56]) {
    ctx.beginPath();
    ctx.moveTo(0, Y(tLat));
    ctx.lineTo(width, Y(tLat));
    ctx.stroke();
  }

  // Equator in solid Accent Gold
  ctx.strokeStyle = '#F5B942';
  ctx.lineWidth = 2;
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(0, Y(0));
  ctx.lineTo(width, Y(0));
  ctx.stroke();

  // Prime Meridian (0°)
  ctx.strokeStyle = 'rgba(255, 209, 102, 0.45)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(X(0), 0);
  ctx.lineTo(X(0), height);
  ctx.stroke();

  // 4. Ground Station Marker in Bengaluru, Karnataka (13.03° N, 77.51° E)
  const bLon = 77.51;
  const bLat = 13.03;
  const bx = X(bLon);
  const by = Y(bLat);

  for (const ox of [-width, 0, width]) {
    const cx = bx + ox;
    if (cx < -50 || cx > width + 50) continue;

    // Glowing target concentric rings
    ctx.strokeStyle = 'rgba(245, 185, 66, 0.4)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(cx, by, 16, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = 'rgba(255, 209, 102, 0.7)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(cx, by, 8, 0, Math.PI * 2);
    ctx.stroke();

    // Solid core dot
    ctx.fillStyle = '#FFD166';
    ctx.beginPath();
    ctx.arc(cx, by, 3.5, 0, Math.PI * 2);
    ctx.fill();

    // Crosshairs
    ctx.strokeStyle = '#F5B942';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(cx - 22, by);
    ctx.lineTo(cx - 10, by);
    ctx.moveTo(cx + 10, by);
    ctx.lineTo(cx + 22, by);
    ctx.moveTo(cx, by - 22);
    ctx.lineTo(cx, by - 10);
    ctx.moveTo(cx, by + 10);
    ctx.lineTo(cx, by + 22);
    ctx.stroke();

    // Marker label
    ctx.font = 'bold 12px "IBM Plex Sans", sans-serif';
    ctx.fillStyle = '#FFD166';
    ctx.fillText('BENGALURU, KA (ISRO)', cx + 18, by + 4);
    ctx.font = '10px "IBM Plex Mono", monospace';
    ctx.fillStyle = '#E6E9EC';
    ctx.fillText('13.03°N, 77.51°E', cx + 18, by + 16);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.anisotropy = 8;
  texture.needsUpdate = true;
  return texture;
}

/**
 * Basic 3D Earth Globe component.
 */
export function Earth({ sunDir: _sunDir }: { sunDir?: THREE.Vector3 }) {
  const cfg = useApp((s) => s.config.scene);
  const [texture, setTexture] = useState<THREE.Texture | null>(null);

  // Position Bengaluru, Karnataka directly at zenith (0, 0, 0)
  const q = useMemo(() => earthQuaternion(cfg.siteLatDeg, cfg.siteLonDeg), [cfg.siteLatDeg, cfg.siteLonDeg]);

  useEffect(() => {
    let active = true;
    buildGlobeTexture(2048).then((tex) => {
      if (active) setTexture(tex);
    });
    return () => {
      active = false;
    };
  }, []);

  const earthMat = useMemo(() => {
    return new THREE.MeshStandardMaterial({
      map: texture,
      roughness: 0.75,
      metalness: 0.05,
      bumpScale: 0.05,
    });
  }, [texture]);

  return (
    <group position={EARTH_CENTER} quaternion={q}>
      {/* Main Earth Globe Sphere */}
      <mesh material={earthMat} renderOrder={0}>
        <sphereGeometry args={[EARTH_R, 96, 48]} />
      </mesh>

      {/* Clean Atmosphere Rim Shell */}
      <mesh renderOrder={1} raycast={() => null}>
        <sphereGeometry args={[EARTH_R + 65, 64, 32]} />
        <meshBasicMaterial
          color="#38bdf8"
          transparent
          opacity={0.12}
          side={THREE.BackSide}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

/**
 * Clean ground site pad located directly at the origin in Bengaluru, Karnataka.
 */
export function GroundSite() {
  const quality = useApp((s) => s.quality);
  const { geo, mat, padMat } = useMemo(() => {
    const R = 3.0; // km radius ground apron
    const refined = new THREE.RingGeometry(0.0005, R, 120, 32);
    refined.rotateX(-Math.PI / 2);
    const rp = refined.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < rp.count; i++) {
      const x = rp.getX(i);
      const z = rp.getZ(i);
      rp.setY(i, -(x * x + z * z) / (2 * EARTH_R));
    }
    refined.computeVertexNormals();

    const grassTex = makeGrassTexture();
    grassTex.repeat.set(120, 120);

    const m = new THREE.MeshStandardMaterial({
      map: grassTex,
      color: new THREE.Color('#27442d'),
      roughness: 0.95,
      metalness: 0.02,
    });

    const pm = new THREE.MeshStandardMaterial({
      map: makeBengaluruPadTexture(),
      roughness: 0.85,
      metalness: 0.08,
      color: '#d4d8dc',
    });

    return { geo: refined, mat: m, padMat: pm };
  }, []);

  return (
    <group>
      <mesh geometry={geo} material={mat} receiveShadow={quality === 'high'} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.00002, 0]} material={padMat} receiveShadow={quality === 'high'}>
        <circleGeometry args={[0.016, 64]} />
      </mesh>
    </group>
  );
}

function makeGrassTexture(): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const ctx = c.getContext('2d')!;
  ctx.fillStyle = '#233d28';
  ctx.fillRect(0, 0, 256, 256);
  let s = 42;
  const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 3000; i++) {
    const g = 40 + r() * 50;
    ctx.fillStyle = `rgba(${g - 10},${g + 20},${g - 15},0.3)`;
    ctx.fillRect(r() * 256, r() * 256, 2, 2);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeBengaluruPadTexture(): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = c.height = 1024;
  const ctx = c.getContext('2d')!;

  // Concrete foundation
  ctx.fillStyle = '#1e262f';
  ctx.fillRect(0, 0, 1024, 1024);

  // Concentric radar & azimuth calibration rings
  ctx.strokeStyle = 'rgba(245, 185, 66, 0.6)';
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(512, 512, 450, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = 'rgba(53, 64, 74, 0.8)';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(512, 512, 300, 0, Math.PI * 2);
  ctx.stroke();

  // Crosshairs & Compass Cardinal Marks
  ctx.strokeStyle = 'rgba(245, 185, 66, 0.4)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(512, 60);
  ctx.lineTo(512, 964);
  ctx.moveTo(60, 512);
  ctx.lineTo(964, 512);
  ctx.stroke();

  // North Arrow
  ctx.fillStyle = '#F5B942';
  ctx.beginPath();
  ctx.moveTo(512, 100);
  ctx.lineTo(480, 170);
  ctx.lineTo(544, 170);
  ctx.fill();

  ctx.font = 'bold 44px "IBM Plex Sans", sans-serif';
  ctx.fillStyle = '#FFD166';
  ctx.textAlign = 'center';
  ctx.fillText('N', 512, 85);

  // Station Label
  ctx.font = 'bold 30px "IBM Plex Sans", sans-serif';
  ctx.fillStyle = '#E6E9EC';
  ctx.fillText('ISRO GROUND STATION · BENGALURU', 512, 500);

  ctx.font = '22px "IBM Plex Mono", monospace';
  ctx.fillStyle = '#89939D';
  ctx.fillText('13.03° N · 77.51° E · KARNATAKA', 512, 540);

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}
