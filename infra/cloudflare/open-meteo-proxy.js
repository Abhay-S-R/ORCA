// ORCA's Open-Meteo relay, deployed as a Cloudflare Worker (docs/deployment/ORCA_Deployment.md §2.9).
//
// Why it exists: Open-Meteo's free API counts requests per IP address, and Render free sends
// from IPs it shares with other customers, so api.open-meteo.com answered ORCA with
// 429 Too Many Requests although ORCA itself had made few calls. Open-Meteo counts Worker
// traffic by the CF-Worker header Cloudflare adds, not by IP (open-meteo/open-meteo#1727), so
// requests through this Worker spend this Worker's own free quota.
//
// It forwards only the two Open-Meteo endpoints ORCA's backend reads, and only for callers
// holding ORCA_PROXY_KEY (a Worker secret), so nobody else can spend the quota or use it as
// an open proxy. Responses are passed through unchanged and never cached here: ORCA labels
// this data as fetched now, so a cached copy would misreport its age.

const UPSTREAM = {
  "/v1/forecast": "https://api.open-meteo.com",
  "/v1/marine": "https://marine-api.open-meteo.com",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const upstream = UPSTREAM[url.pathname];
    if (request.method !== "GET" || !upstream) {
      return new Response("not found", { status: 404 });
    }
    if (!env.ORCA_PROXY_KEY || request.headers.get("X-Orca-Key") !== env.ORCA_PROXY_KEY) {
      return new Response("forbidden", { status: 403 });
    }
    return fetch(upstream + url.pathname + url.search);
  },
};
