"use client";

import { useEffect, useRef } from "react";
import type * as maplibregl from "maplibre-gl";

export interface VectorPoint {
  lat: number;
  lon: number;
  speed_ms: number;
  direction_deg: number;
  u?: number;
  v?: number;
}

interface FlowFieldCanvasProps {
  /** The map lives in a ref on the parent; reading `.current` during the parent's
   *  render is the hazard `react-hooks/refs` catches, so the ref is handed over
   *  whole and read inside the effect below. `mapReady` is what re-runs it. */
  mapRef: React.RefObject<maplibregl.Map | null>;
  mapReady: boolean;
  showCurrents: boolean;
  showWind: boolean;
  currentVectors: VectorPoint[] | null;
  windVectors: VectorPoint[] | null;
  currentBounds?: [number, number, number, number] | null;
  windBounds?: [number, number, number, number] | null;
  /** Drawn grey when the time slider is on an hour this field was not sampled at (P4.15). */
  greyCurrents?: boolean;
  greyWind?: boolean;
}

// Neutral grey, fainter: "this is not the hour you are looking at".
const GREY_RGB = "rgba(120, 120, 120, ALPHA)";

interface Particle {
  lon: number;
  lat: number;
  age: number;
  maxAge: number;
}

/** Auto-detect the grid spacing from point coordinates instead of hardcoding.
 *  Finds the median of all consecutive unique lat/lon differences — robust
 *  against irregular coastline gaps and single-point outliers. */
function detectResolution(points: VectorPoint[]): number {
  const lats = [...new Set(points.map((p) => p.lat))].sort((a, b) => a - b);
  const lons = [...new Set(points.map((p) => p.lon))].sort((a, b) => a - b);
  const diffs: number[] = [];
  for (let i = 1; i < lats.length; i++) {
    const d = lats[i] - lats[i - 1];
    if (d > 0.001) diffs.push(d);
  }
  for (let i = 1; i < lons.length; i++) {
    const d = lons[i] - lons[i - 1];
    if (d > 0.001) diffs.push(d);
  }
  if (diffs.length === 0) return 0.25; // fallback
  diffs.sort((a, b) => a - b);
  return diffs[Math.floor(diffs.length / 2)];
}

class VectorGrid {
  private grid: ({ u: number; v: number; speed: number } | null)[][];
  private west: number;
  private south: number;
  private east: number;
  private north: number;
  private resolution: number;
  private cols: number;
  private rows: number;

  constructor(points: VectorPoint[], bounds: [number, number, number, number] = [65.0, 4.0, 95.0, 26.0], res?: number) {
    const effectiveRes = res ?? detectResolution(points);
    this.west = bounds[0];
    this.south = bounds[1];
    this.east = bounds[2];
    this.north = bounds[3];
    this.resolution = effectiveRes;
    this.cols = Math.ceil((this.east - this.west) / effectiveRes) + 1;
    this.rows = Math.ceil((this.north - this.south) / effectiveRes) + 1;
    this.grid = Array.from({ length: this.rows }, () => Array.from({ length: this.cols }, () => null));

    for (const p of points) {
      const c = Math.round((p.lon - this.west) / effectiveRes);
      const r = Math.round((p.lat - this.south) / effectiveRes);
      if (r >= 0 && r < this.rows && c >= 0 && c < this.cols) {
        let u = p.u;
        let v = p.v;
        if (u === undefined || v === undefined) {
          const rad = (p.direction_deg * Math.PI) / 180;
          u = p.speed_ms * Math.sin(rad);
          v = p.speed_ms * Math.cos(rad);
        }
        this.grid[r][c] = { u, v, speed: p.speed_ms };
      }
    }
  }

  lookup(lon: number, lat: number): { u: number; v: number; speed: number } | null {
    if (lon < this.west || lon > this.east || lat < this.south || lat > this.north) {
      return null;
    }
    const c = (lon - this.west) / this.resolution;
    const r = (lat - this.south) / this.resolution;
    const c0 = Math.floor(c);
    const c1 = Math.min(c0 + 1, this.cols - 1);
    const r0 = Math.floor(r);
    const r1 = Math.min(r0 + 1, this.rows - 1);

    if (r0 < 0 || r0 >= this.rows || c0 < 0 || c0 >= this.cols) return null;

    const p00 = this.grid[r0][c0];
    const p10 = this.grid[r0][c1];
    const p01 = this.grid[r1][c0];
    const p11 = this.grid[r1][c1];

    const fx = c - c0;
    const fy = r - r0;

    // Nearest grid vertex among the 4 corners
    const nearestCell = (fy < 0.5)
      ? (fx < 0.5 ? p00 : p10)
      : (fx < 0.5 ? p01 : p11);

    // If the closest cell is land/null, strictly do not show on land
    if (!nearestCell) return null;

    // Bilinear weighting over available ocean cells
    const w00 = p00 ? (1 - fx) * (1 - fy) : 0;
    const w10 = p10 ? fx * (1 - fy) : 0;
    const w01 = p01 ? (1 - fx) * fy : 0;
    const w11 = p11 ? fx * fy : 0;
    const totalW = w00 + w10 + w01 + w11;
    if (totalW < 0.0001) return null;

    const u = (w00 * (p00?.u ?? 0) + w10 * (p10?.u ?? 0) + w01 * (p01?.u ?? 0) + w11 * (p11?.u ?? 0)) / totalW;
    const v = (w00 * (p00?.v ?? 0) + w10 * (p10?.v ?? 0) + w01 * (p01?.v ?? 0) + w11 * (p11?.v ?? 0)) / totalW;

    const speed = Math.hypot(u, v);
    if (speed < 0.01) return null;

    return { u, v, speed };
  }
}

export function FlowFieldCanvas({
  mapRef,
  mapReady,
  showCurrents,
  showWind,
  currentVectors,
  windVectors,
  currentBounds,
  windBounds,
  greyCurrents = false,
  greyWind = false,
}: FlowFieldCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (!showCurrents && !showWind) {
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Resize canvas to match map container
    const resize = () => {
      const container = map.getContainer();
      const dpr = window.devicePixelRatio || 1;
      const width = container.clientWidth;
      const height = container.clientHeight;
      if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        ctx.scale(dpr, dpr);
      }
    };
    resize();

    // Build vector grids covering the maritime region
    const currentGrid =
      showCurrents && currentVectors?.length
        ? new VectorGrid(currentVectors, currentBounds || [65.0, 4.0, 95.0, 26.0])
        : null;

    const windGrid =
      showWind && windVectors?.length
        ? new VectorGrid(windVectors, windBounds || [65.0, 4.0, 95.0, 26.0])
        : null;

    // Particle pools covering the active Pan-India domain.
    const NUM_PARTICLES = 2000;
    const currentParticles: Particle[] = [];
    const windParticles: Particle[] = [];

    // Web Mercator meters-per-pixel at a latitude/zoom
    const metersPerPixel = (lat: number) => (156543.03392 * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, map.getZoom());

    const getBounds = () => {
      const b = map.getBounds();
      return {
        west: Math.max(65.0, b.getWest()),
        south: Math.max(4.0, b.getSouth()),
        east: Math.min(95.0, b.getEast()),
        north: Math.min(26.0, b.getNorth()),
      };
    };

    const spawnParticle = (grid: VectorGrid | null): Particle => {
      const b = getBounds();
      let attempts = 0;
      let lon = b.west + Math.random() * (b.east - b.west);
      let lat = b.south + Math.random() * (b.north - b.south);
      while (grid && !grid.lookup(lon, lat) && attempts < 40) {
        lon = b.west + Math.random() * (b.east - b.west);
        lat = b.south + Math.random() * (b.north - b.south);
        attempts++;
      }
      return {
        lon,
        lat,
        age: Math.floor(Math.random() * 80),
        maxAge: 80 + Math.floor(Math.random() * 60),
      };
    };

    if (currentGrid) {
      for (let i = 0; i < NUM_PARTICLES; i++) {
        currentParticles.push(spawnParticle(currentGrid));
      }
    }

    if (windGrid) {
      for (let i = 0; i < NUM_PARTICLES; i++) {
        windParticles.push(spawnParticle(windGrid));
      }
    }

    let animationFrameId: number;
    let isMoving = false;

    const onMoveStart = () => {
      isMoving = true;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    };

    const onMoveEnd = () => {
      isMoving = false;
      resize();
    };

    map.on("movestart", onMoveStart);
    map.on("moveend", onMoveEnd);
    map.on("resize", resize);

    const step = () => {
      if (!isMoving) {
        // Subtle trail fade: dark tint over previous frame.
        ctx.globalCompositeOperation = "destination-out";
        ctx.fillStyle = "rgba(0, 0, 0, 0.06)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.globalCompositeOperation = "source-over";

        const container = map.getContainer();
        const width = container.clientWidth;
        const height = container.clientHeight;
        const b = getBounds();

        const drawField = (
          grid: VectorGrid,
          particles: Particle[],
          opts: {
            maxSpeed: number;
            haloRgb: string;
            lightHaloRgb: string;
            colorRgb: string;
            widths: [number, number, number];
            pxPerFrame: [number, number, number];
          },
        ) => {
          const tiers: { lon: number; lat: number; lon2: number; lat2: number }[][] = [[], [], []];

          for (let i = 0; i < particles.length; i++) {
            const p = particles[i];
            const vec = grid.lookup(p.lon, p.lat);

            if (!vec || p.age >= p.maxAge || p.lon < b.west || p.lon > b.east || p.lat < b.south || p.lat > b.north) {
              particles[i] = spawnParticle(grid);
              continue;
            }

            const p1 = map.project([p.lon, p.lat]);
            if (p1.x < 0 || p1.x > width || p1.y < 0 || p1.y > height) {
              particles[i] = spawnParticle(grid);
              continue;
            }

            const speedFrac = Math.min(vec.speed / opts.maxSpeed, 1);
            const tier = speedFrac < 0.33 ? 0 : speedFrac < 0.7 ? 1 : 2;
            const pxPerFrame = opts.pxPerFrame[tier];

            const mpp = metersPerPixel(p.lat);
            const ux = vec.u / vec.speed;
            const uy = vec.v / vec.speed;
            const dLon = (ux * pxPerFrame * mpp) / (111320 * Math.max(Math.cos((p.lat * Math.PI) / 180), 0.01));
            const dLat = (uy * pxPerFrame * mpp) / 111320;

            const nextLon = p.lon + dLon;
            const nextLat = p.lat + dLat;

            // Strict boundary check: ensure destination point is still in ocean and not over land
            const nextVec = grid.lookup(nextLon, nextLat);
            if (!nextVec) {
              particles[i] = spawnParticle(grid);
              continue;
            }

            p.lon = nextLon;
            p.lat = nextLat;
            p.age++;

            const p2 = map.project([p.lon, p.lat]);
            tiers[tier].push({ lon: p1.x, lat: p1.y, lon2: p2.x, lat2: p2.y });
          }

          ctx.lineCap = "round";
          for (let t = 0; t < 3; t++) {
            if (!tiers[t].length) continue;
            ctx.beginPath();
            for (const seg of tiers[t]) {
              ctx.moveTo(seg.lon, seg.lat);
              ctx.lineTo(seg.lon2, seg.lat2);
            }
            ctx.strokeStyle = opts.lightHaloRgb;
            ctx.lineWidth = opts.widths[t] + 0.9;
            ctx.stroke();
            ctx.strokeStyle = opts.haloRgb;
            ctx.lineWidth = opts.widths[t] + 0.5;
            ctx.stroke();
            const alpha = [0.32, 0.5, 0.72][t] * (opts.colorRgb === GREY_RGB ? 0.5 : 1);
            ctx.strokeStyle = opts.colorRgb.replace("ALPHA", String(alpha));
            ctx.lineWidth = opts.widths[t];
            ctx.stroke();
          }
        };

        // 1. Currents — water-blue streamlines filling all Indian ocean domain
        if (currentGrid) {
          drawField(currentGrid, currentParticles, {
            maxSpeed: 1.2,
            haloRgb: "rgba(4, 20, 28, 0.28)",
            lightHaloRgb: "rgba(255, 255, 255, 0.4)",
            colorRgb: greyCurrents ? GREY_RGB : "rgba(8, 145, 178, ALPHA)",
            widths: [0.55, 0.8, 1.15],
            pxPerFrame: [0.28, 0.55, 0.85],
          });
        }

        // 2. Wind — archived ScatSat, visually distinct amber
        if (windGrid) {
          drawField(windGrid, windParticles, {
            maxSpeed: 12,
            haloRgb: "rgba(4, 20, 28, 0.24)",
            lightHaloRgb: "rgba(255, 255, 255, 0.35)",
            colorRgb: greyWind ? GREY_RGB : "rgba(202, 138, 4, ALPHA)",
            widths: [0.5, 0.7, 1.0],
            pxPerFrame: [0.25, 0.48, 0.75],
          });
        }
      }

      animationFrameId = requestAnimationFrame(step);
    };

    animationFrameId = requestAnimationFrame(step);

    return () => {
      cancelAnimationFrame(animationFrameId);
      map.off("movestart", onMoveStart);
      map.off("moveend", onMoveEnd);
      map.off("resize", resize);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [mapRef, mapReady, showCurrents, showWind, currentVectors, windVectors, currentBounds, windBounds, greyCurrents, greyWind]);

  if (!showCurrents && !showWind) return null;

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-[1]"
      style={{ width: "100%", height: "100%" }}
    />
  );
}
