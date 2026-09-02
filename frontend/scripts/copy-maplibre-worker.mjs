// MapLibre v6 ships ESM-only and resolves its worker's sibling
// (maplibre-gl-shared.mjs) by RELATIVE path. Turbopack — which Next 16 uses
// by default — rewrites `new URL(...)` into a hashed asset and does not emit
// that sibling alongside it, so the map mounts and then never requests a
// tile. Silent failure, no console error.
//
// The fix MapLibre documents for Next is to stop asking the bundler: copy
// both files into public/ ourselves and point setWorkerUrl at a static path.
// Needed in BOTH `next dev`/`next build` and `--webpack` mode.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const dist = dirname(require.resolve("maplibre-gl/package.json")) + "/dist";
const out = join(process.cwd(), "public", "maplibre");

mkdirSync(out, { recursive: true });
for (const f of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(join(dist, f), join(out, f));
}
console.log("maplibre worker + shared copied to public/maplibre/");
