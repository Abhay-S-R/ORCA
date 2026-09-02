"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "../components/States";

// MapLibre touches `window` at module load, so the chart is client-only —
// same constraint Leaflet had, same fix.
const MapView = dynamic(() => import("../components/MapView").then((m) => m.MapView), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

// The chart explorer goes edge to edge. No page header, no padding: this
// surface IS the map, and framing it in a card would make it a widget.
export default function MapPage() {
  return (
    <div className="h-full">
      <h1 className="sr-only">Chart</h1>
      <MapView className="h-full w-full rounded-none border-0" />
    </div>
  );
}
