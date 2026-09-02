"use client";

import dynamic from "next/dynamic";

// Leaflet touches `window` at import time, so the map shell is client-only
// (plan §4 S5 Day 3-6: boundaries, PFZ pins, depth/bearing readout).
const MapView = dynamic(() => import("../components/MapView").then((m) => m.MapView), {
  ssr: false,
  loading: () => <p className="text-sm text-black/50">Loading map…</p>,
});

export default function MapPage() {
  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Map</h1>
      <MapView />
    </div>
  );
}
