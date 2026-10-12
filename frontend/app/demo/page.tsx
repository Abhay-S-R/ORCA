"use client";

// /demo — IMBL Border Bypass Cinematic Demo
// Full-viewport layout: map fills the entire available height, with HUD overlays on top.
import { IMBLCrossing } from "./IMBLCrossing";

export default function DemoPage() {
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <IMBLCrossing />
    </div>
  );
}
