import type { NextConfig } from "next";

// NEXT_PUBLIC_API_BASE_URL is baked into the bundle at build time. Unset on a
// Vercel build, every call silently falls back to http://localhost:8000
// (app/lib/apiBase.ts) and the deployed site 404s everything; an http:// value
// is blocked as mixed content on Vercel's https origin. Fail the build instead.
// VERCEL is set by Vercel on every build and never locally.
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
if (process.env.VERCEL && !apiBase?.startsWith("https://")) {
  throw new Error(
    `NEXT_PUBLIC_API_BASE_URL must be set to the backend's https:// URL in the Vercel project settings (got ${JSON.stringify(apiBase)}). See docs/ORCA_Deployment.md.`,
  );
}

const nextConfig: NextConfig = {
  /* config options here */
};

export default nextConfig;
