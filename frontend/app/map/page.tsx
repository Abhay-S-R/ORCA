"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "../components/States";
import { PERSONA_MAP_PROFILE } from "../persona/config";
import { usePersona } from "../persona/context";
import { useT } from "../i18n/useT";

// MapLibre touches `window` at module load, so the chart is client-only —
// same constraint Leaflet had, same fix.
const MapView = dynamic(() => import("../components/MapView").then((m) => m.MapView), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

// The chart explorer goes edge to edge. No page header, no padding: this
// surface IS the map, and framing it in a card would make it a widget.
export default function MapPage() {
  const t = useT();
  // P4.4 — "per-persona map defaults... come from one extension of the
  // existing config table". Fisherman drops the layer console entirely
  // (one pin, no stack); researcher opens with every layer, including the
  // two heavy ones, already on.
  const { persona } = usePersona();
  const profile = PERSONA_MAP_PROFILE[persona];
  return (
    <div className="h-full">
      <h1 className="sr-only">{t("nav.map")}</h1>
      <MapView
        className="h-full w-full rounded-none border-0"
        showLayerPanel={profile.showLayerPanel}
        initialLayers={profile.initialLayers}
      />
    </div>
  );
}
