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

    // Particle pools
    const NUM_PARTICLES = 1800;
    const currentParticles: Particle[] = [];
    const windParticles: Particle[] = [];

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
        ctx.fillStyle = "rgba(0, 0, 0, 0.08)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.globalCompositeOperation = "source-over";

        const container = map.getContainer();
        const width = container.clientWidth;
        const height = container.clientHeight;
        const b = getBounds();

        // 1. Draw Currents (Electric Cyan / Aquatic Azure). A dark halo is
        // stroked first so the line reads against BOTH the pale shelf colours
        // and the near-black abyssal fill of the depth ramp underneath —
        // without it, cyan-on-pale-shelf was nearly invisible (the two are
        // close in lightness) even though cyan-on-abyss looked fine alone.
        if (currentGrid) {
          ctx.lineCap = "round";

          ctx.beginPath();
          for (let i = 0; i < currentParticles.length; i++) {
            const p = currentParticles[i];
            const vec = currentGrid.lookup(p.lon, p.lat);

            if (!vec || p.age >= p.maxAge || p.lon < b.west || p.lon > b.east || p.lat < b.south || p.lat > b.north) {
              currentParticles[i] = spawnParticle(currentGrid);
              continue;
            }

            const p1 = map.project([p.lon, p.lat]);
            if (p1.x < 0 || p1.x > width || p1.y < 0 || p1.y > height) {
              currentParticles[i] = spawnParticle(currentGrid);
              continue;
            }

            // Current speed factor
            const speedFactor = 0.0035;
            const cosLat = Math.cos((p.lat * Math.PI) / 180);
            const dLon = (vec.u * speedFactor) / (cosLat > 0.01 ? cosLat : 1);
            const dLat = vec.v * speedFactor;

            p.lon += dLon;
            p.lat += dLat;
            p.age++;

            const p2 = map.project([p.lon, p.lat]);
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
          }
          // Halo pass (wider, dark) then the colour pass on the same path —
          // stroke() doesn't clear the path, so this re-draws it twice.
          ctx.strokeStyle = "rgba(3, 14, 20, 0.55)";
          ctx.lineWidth = 3;
          ctx.stroke();
          ctx.strokeStyle = "rgba(14, 165, 233, 0.95)";
          ctx.lineWidth = 1.7;
          ctx.stroke();
        }

        // 2. Draw Wind (Golden Amber / Solar Yellow) — same halo treatment.
        if (windGrid) {
          ctx.lineCap = "round";

          ctx.beginPath();
          for (let i = 0; i < windParticles.length; i++) {
            const p = windParticles[i];
            const vec = windGrid.lookup(p.lon, p.lat);

            if (!vec || p.age >= p.maxAge || p.lon < b.west || p.lon > b.east || p.lat < b.south || p.lat > b.north) {
              windParticles[i] = spawnParticle(windGrid);
              continue;
            }

            const p1 = map.project([p.lon, p.lat]);
            if (p1.x < 0 || p1.x > width || p1.y < 0 || p1.y > height) {
              windParticles[i] = spawnParticle(windGrid);
              continue;
            }

            // Wind speed factor (winds are higher m/s than currents)
            const speedFactor = 0.0018;
            const cosLat = Math.cos((p.lat * Math.PI) / 180);
            const dLon = (vec.u * speedFactor) / (cosLat > 0.01 ? cosLat : 1);
            const dLat = vec.v * speedFactor;

            p.lon += dLon;
            p.lat += dLat;
            p.age++;

            const p2 = map.project([p.lon, p.lat]);
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
          }
          ctx.strokeStyle = "rgba(3, 14, 20, 0.5)";
          ctx.lineWidth = 2.6;
          ctx.stroke();
          ctx.strokeStyle = "rgba(251, 191, 36, 0.95)";
          ctx.lineWidth = 1.4;
          ctx.stroke();
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
