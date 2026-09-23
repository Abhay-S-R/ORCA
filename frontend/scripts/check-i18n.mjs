#!/usr/bin/env node
// P3.12 Done-when — "zero untranslated keys reported by a script that diffs
// each dictionary against en.json". Run: node scripts/check-i18n.mjs
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const i18nDir = join(here, "..", "app", "i18n");

const en = JSON.parse(readFileSync(join(i18nDir, "en.json"), "utf8"));
const enKeys = new Set(Object.keys(en));

const files = readdirSync(i18nDir).filter((f) => f.endsWith(".json") && f !== "en.json");

let failed = false;
for (const file of files) {
  const dict = JSON.parse(readFileSync(join(i18nDir, file), "utf8"));
  const dictKeys = new Set(Object.keys(dict));
  const missing = [...enKeys].filter((k) => !dictKeys.has(k));
  const extra = [...dictKeys].filter((k) => !enKeys.has(k));
  if (missing.length || extra.length) {
    failed = true;
    console.error(`\n${file}:`);
    if (missing.length) console.error(`  missing: ${missing.join(", ")}`);
    if (extra.length) console.error(`  extra (not in en.json): ${extra.join(", ")}`);
  }
}

if (failed) {
  console.error("\ni18n check FAILED — see gaps above.");
  process.exit(1);
}
console.log(`i18n check OK — ${files.length} dictionaries, ${enKeys.size} keys each, all match en.json.`);
