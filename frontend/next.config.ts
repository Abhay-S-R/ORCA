import type { NextConfig } from "next";

// NEXT_PUBLIC_API_BASE_URL is baked into the bundle at build time. Unset on a
// Vercel build, every call would silently fall back to http://localhost:8000
// (app/lib/apiBase.ts); an http:// value is blocked as mixed content on
// Vercel's https origin. VERCEL is set by Vercel on every build and never
// locally, so local builds are untouched.
//
// Unset on Vercel, it defaults to the deployed Render backend
// (docs/deployment/ORCA_Deployment.md §2.5). A value set in the Vercel dashboard always
// wins. Render added the -render suffix because orca-backend.onrender.com
// belongs to someone else: a default left at that name would send every
// sign-in to a stranger's service.
// Backend host on AWS EC2
const BACKEND_URL = process.env.BACKEND_URL || "http://52.62.164.128:8000";

// When deployed on Vercel, if NEXT_PUBLIC_API_BASE_URL is not explicitly set to an external URL,
// default to "" (empty string) so all fetches use relative paths (e.g., /api/...)
// and are proxied server-side via rewrites below. This prevents browser Mixed Content blocking.
const apiBase = process.env.VERCEL
  ? (process.env.NEXT_PUBLIC_API_BASE_URL ?? "")
  : undefined;

const nextConfig: NextConfig = {
  devIndicators: false,
  ...(apiBase !== undefined && { env: { NEXT_PUBLIC_API_BASE_URL: apiBase } }),
  async redirects() {
    return [
      {
        source: "/sea-route",
        destination: "/voyage?tab=sea-route",
        permanent: false,
      },
      {
        source: "/sea-routes",
        destination: "/voyage?tab=sea-route",
        permanent: false,
      },
      {
        source: "/searoute",
        destination: "/voyage?tab=sea-route",
        permanent: false,
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
      {
        source: "/query",
        destination: `${BACKEND_URL}/query`,
      },
      {
        source: "/trace/:path*",
        destination: `${BACKEND_URL}/trace/:path*`,
      },
      {
        source: "/render",
        destination: `${BACKEND_URL}/render`,
      },
      {
        source: "/voice/:path*",
        destination: `${BACKEND_URL}/voice/:path*`,
      },
      {
        source: "/health",
        destination: `${BACKEND_URL}/health`,
      },
    ];
  },
};

export default nextConfig;
