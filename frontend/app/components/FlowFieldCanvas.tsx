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
  map: maplibregl.Map | null;
  showCurrents: boolean;
  showWind: boolean;
  currentVectors: VectorPoint[] | null;
  windVectors: VectorPoint[] | null;
}

interface Particle {
  lon: number;
  lat: number;
  age: number;
  maxAge: number;
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

  constructor(points: VectorPoint[], bounds: [number, number, number, number] = [65.0, 5.0, 95.0, 25.0], res = 0.5) {
    this.west = bounds[0];
    this.south = bounds[1];
    this.east = bounds[2];
    this.north = bounds[3];
    this.resolution = res;
    this.cols = Math.ceil((this.east - this.west) / res) + 1;
    this.rows = Math.ceil((this.north - this.south) / res) + 1;
    this.grid = Array.from({ length: this.rows }, () => Array.from({ length: this.cols }, () => null));

    for (const p of points) {
      const c = Math.round((p.lon - this.west) / res);
      const r = Math.round((p.lat - this.south) / res);
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

    if (!p00 && !p10 && !p01 && !p11) return null;

    const fx = c - c0;
    const fy = r - r0;

    const u0 = (p00?.u ?? 0) * (1 - fx) + (p10?.u ?? 0) * fx;
    const u1 = (p01?.u ?? 0) * (1 - fx) + (p11?.u ?? 0) * fx;
    const u = u0 * (1 - fy) + u1 * fy;

    const v0 = (p00?.v ?? 0) * (1 - fx) + (p10?.v ?? 0) * fx;
    const v1 = (p01?.v ?? 0) * (1 - fx) + (p11?.v ?? 0) * fx;
    const v = v0 * (1 - fy) + v1 * fy;

    const speed = Math.hypot(u, v);
    if (speed < 0.02) return null;

    return { u, v, speed };
  }
}

export function FlowFieldCanvas({
  map,
  showCurrents,
  showWind,
  currentVectors,
  windVectors,
}: FlowFieldCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
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

    // Build vector grids
    const currentGrid =
      showCurrents && currentVectors?.length
        ? new VectorGrid(currentVectors)
        : null;

    const windGrid =
      showWind && windVectors?.length
        ? new VectorGrid(windVectors)
        : null;

    // Particle pools. Density tuned for "a flow field", not "a starfield" —
    // the earlier 1800 read as noise once the field covered a whole ocean
    // basin at typical zoom.
    const NUM_PARTICLES = 480;
    const currentParticles: Particle[] = [];
    const windParticles: Particle[] = [];

    // Web Mercator meters-per-pixel at a latitude/zoom — the standard
    // formula MapLibre itself uses internally. Converting each particle's
    // step to a fixed PIXEL distance (via this) rather than a fixed DEGREE
    // delta is what actually fixes the "frozen dust" look: a hardcoded
    // degree step is imperceptible pixels at an ocean-basin zoom and wildly
    // oversized at a harbour zoom, so the old version never looked like
    // flow at any zoom except the one it was tuned against.
    const metersPerPixel = (lat: number) => (156543.03392 * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, map.getZoom());

    const getBounds = () => {
      const b = map.getBounds();
      return {
        west: Math.max(65.0, b.getWest()),
        south: Math.max(5.0, b.getSouth()),
        east: Math.min(95.0, b.getEast()),
        north: Math.min(25.0, b.getNorth()),
      };
    };

    const spawnParticle = (grid: VectorGrid | null): Particle => {
      const b = getBounds();
      let attempts = 0;
      let lon = b.west + Math.random() * (b.east - b.west);
      let lat = b.south + Math.random() * (b.north - b.south);
      while (grid && !grid.lookup(lon, lat) && attempts < 10) {
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
        // Subtle trail fade: dark tint over previous frame
        ctx.globalCompositeOperation = "destination-out";
        ctx.fillStyle = "rgba(0, 0, 0, 0.1)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.globalCompositeOperation = "source-over";

        const container = map.getContainer();
        const width = container.clientWidth;
        const height = container.clientHeight;
        const b = getBounds();

        // Shared stepper for both fields: moves each particle a fixed PIXEL
        // distance per frame (scaled to local Mercator scale) rather than a
        // fixed degree delta, so the field reads as flowing streamlines at
        // any zoom instead of a near-static dust cloud at ocean-basin zooms
        // and a wild streak at harbour zooms. Particles are bucketed into
        // three speed tiers so faster water/wind draws visibly bolder and
        // brighter than slack water — "meaningful intensity variation" —
        // for the cost of 3 stroke() calls instead of 1, not per-particle.
        const drawField = (
          grid: VectorGrid,
          particles: Particle[],
          opts: { maxSpeed: number; haloRgb: string; colorRgb: string; widths: [number, number, number]; pxPerFrame: [number, number, number] },
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

            p.lon += dLon;
            p.lat += dLat;
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
            // A thin, faint halo pass first — just enough edge definition to
            // stay legible over both the pale shelf and the dark abyssal end
            // of the depth ramp — then a thin colour pass. Both stay narrow:
            // a wide dark outline under every particle was what actually
            // read as "harsh scratches" rather than water.
            ctx.strokeStyle = opts.haloRgb;
            ctx.lineWidth = opts.widths[t] + 0.5;
            ctx.stroke();
            const alpha = [0.32, 0.5, 0.72][t];
            ctx.strokeStyle = opts.colorRgb.replace("ALPHA", String(alpha));
            ctx.lineWidth = opts.widths[t];
            ctx.stroke();
          }
        };

        // 1. Currents — a clean water-blue, thin enough to read as threads
        // of flow rather than a bold overlay competing with the depth ramp.
        if (currentGrid) {
          drawField(currentGrid, currentParticles, {
            maxSpeed: 1.2,
            haloRgb: "rgba(4, 20, 28, 0.28)",
            colorRgb: "rgba(8, 145, 178, ALPHA)",
            widths: [0.55, 0.8, 1.15],
            pxPerFrame: [0.7, 1.4, 2.2],
          });
        }

        // 2. Wind — archived ScatSat, kept visually distinct (amber) from
        // live currents so the two are never mistaken for one field.
        if (windGrid) {
          drawField(windGrid, windParticles, {
            maxSpeed: 12,
            haloRgb: "rgba(4, 20, 28, 0.24)",
            colorRgb: "rgba(202, 138, 4, ALPHA)",
            widths: [0.5, 0.7, 1.0],
            pxPerFrame: [0.6, 1.2, 1.9],
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
  }, [map, showCurrents, showWind, currentVectors, windVectors]);

  if (!showCurrents && !showWind) return null;

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-10"
      style={{ width: "100%", height: "100%" }}
    />
  );
}
