import type { NextConfig } from "next";

// NEXT_PUBLIC_API_BASE_URL is baked into the bundle at build time. Unset on a
// Vercel build, every call would silently fall back to http://localhost:8000
// (app/lib/apiBase.ts); an http:// value is blocked as mixed content on
// Vercel's https origin. VERCEL is set by Vercel on every build and never
// locally, so local builds are untouched.
//
// Unset on Vercel, it defaults to the planned Render backend URL
// (docs/ORCA_Deployment.md §2.5), so the frontend can be deployed before the
// backend exists. A value set in the Vercel dashboard always wins.
const RENDER_BACKEND_URL = "https://orca-backend.onrender.com";

const apiBase = process.env.VERCEL
  ? process.env.NEXT_PUBLIC_API_BASE_URL || RENDER_BACKEND_URL
  : undefined;
if (apiBase && !apiBase.startsWith("https://")) {
  throw new Error(
    `NEXT_PUBLIC_API_BASE_URL must be the backend's https:// URL in the Vercel project settings (got ${JSON.stringify(apiBase)}). See docs/ORCA_Deployment.md.`,
  );
}

const nextConfig: NextConfig = {
  ...(apiBase && { env: { NEXT_PUBLIC_API_BASE_URL: apiBase } }),
};

export default nextConfig;
