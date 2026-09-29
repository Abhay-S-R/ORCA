# ORCA — Deployment

> Living document. It records where each part of ORCA is deployed, how to redo it, and what state
> it is in. Update the status table whenever a step is done.

## Status

| Part | Host | Status |
|---|---|---|
| Frontend (Next.js, `frontend/`) | Vercel, Hobby plan (free) | **In progress.** The repo is ready (§1.1). The Vercel project has not been created yet (§1.2). |
| Backend (FastAPI, `backend/`) | Not decided yet. The candidates are in §2. | Not started |
| Postgres + PostGIS, Redis | Goes wherever the backend goes | Not started |

**Until the backend is deployed, the Vercel site loads but every API call fails.** Every page is
built statically and gets all of its data from the backend.

---

## 1. Frontend on Vercel

### 1.1 What the repo already does for Vercel

- **`frontend/next.config.ts` fails the build on Vercel if `NEXT_PUBLIC_API_BASE_URL` is missing
  or is not `https://`.** Next.js bakes this value into the JavaScript at build time. If it were
  missing, every call would silently fall back to `http://localhost:8000` (`app/lib/apiBase.ts`),
  and the site would look deployed while nothing on it worked. An `http://` backend is also
  blocked by the browser, because a page served over https may not call http (mixed content). The
  check only runs when Vercel's `VERCEL` variable is set, so local builds are unaffected.
- `npm run build` runs `prebuild`, which copies the MapLibre worker into `public/maplibre/`.
  Vercel runs this automatically, so the map works without any extra step.
- Every route is static (`○` in the build output). There are no server functions, so the Hobby
  function limits do not apply to the frontend.
- Sign-in uses bearer tokens stored in `localStorage`, not cookies. Hosting the frontend and the
  backend on different domains therefore needs no cookie or SameSite setup. The backend already
  allows every origin (`CORSMiddleware(allow_origins=["*"])` in `backend/orca/api/main.py`).

Checked on 2026-09-30:

- `VERCEL=1 NEXT_PUBLIC_API_BASE_URL=https://api.example.test npm run build` built all 20 routes,
  and the URL appears in `.next/static/chunks`.
- With the variable unset, the build fails with the error message above.
- With the variable set to `http://…`, the build also fails with that message.
- No file the build needs is gitignored (`git ls-files -o -i --exclude-standard frontend` lists
  only `next-env.d.ts`, which Next regenerates, and an editor cache).

### 1.2 Steps in the Vercel dashboard

1. **Push `main` to GitHub** (`Abhay-S-R/ORCA`). Vercel builds whatever is on GitHub, not your
   local working tree.
2. **Create the account.** Sign up at <https://vercel.com/signup> with **Continue with GitHub**,
   using the account that owns the repo, and choose the **Hobby** plan.
3. **Import the repo.** Click **Add New… → Project**. Under *Import Git Repository*, click
   **Adjust GitHub App Permissions** if `ORCA` is not listed, grant access to that repo, then click
   **Import**.
4. **Configure the project** before clicking Deploy:
   - **Project Name:** `orca`. This gives the URL `https://orca-<something>.vercel.app`.
   - **Framework Preset:** Next.js. It is detected automatically.
   - **Root Directory:** click **Edit** and choose **`frontend`**. **This is the setting most
     likely to be missed.** The repo root has no `package.json`, so the build fails without it.
   - **Build and Output Settings:** leave everything on default (`npm install`, `npm run build`,
     output `.next`).
   - **Environment Variables:**

     | Name | Value | Required |
     |---|---|---|
     | `NEXT_PUBLIC_API_BASE_URL` | The backend's public **https** URL, with no trailing slash, e.g. `https://orca-api.example.com` | **Yes.** Without it the build fails on purpose. |
     | `NEXT_PUBLIC_CARTO_KEY` | A CARTO basemap key | No. Without it the keyless CARTO light style is used. |
     | `NEXT_PUBLIC_BASEMAP_STYLE` | A full MapLibre style URL | No. It overrides the basemap. |

     Anything starting with `NEXT_PUBLIC_` is visible to every visitor. Never put a secret there.
     The LLM, Bhashini, database and JWT values belong to the backend and never go into Vercel.
5. **Click Deploy.** The build takes about 1–2 minutes. When it finishes, open the `.vercel.app`
   URL.
6. **Node version:** Settings → General → Node.js Version should be **22.x** or newer. Next 16
   needs at least 20.9, and the project is developed on 22.
7. **After the backend's URL is known or changes:** go to Settings → Environment Variables and
   edit `NEXT_PUBLIC_API_BASE_URL`. Then open **Deployments → ⋯ → Redeploy** on the latest
   deployment. **Editing the variable alone does nothing**, because the value is baked in at build
   time.

**If you need to deploy before the backend exists:** Vercel will not build without an https
backend URL. You can temporarily expose your local backend with a Cloudflare quick tunnel
(`cloudflared tunnel --url http://localhost:8000` prints an `https://…trycloudflare.com` URL),
set that as the value, and redeploy. The tunnel URL changes every time `cloudflared` restarts,
and it works only while your laptop is on.

### 1.3 After it is live

- **Automatic deploys:** every push to `main` redeploys production, and pushes to other branches
  get preview URLs. On Hobby, Vercel may refuse to build a commit to a private repo whose author
  is not the Vercel account owner. If a teammate's push does not deploy, check this first.
- **HTTPS is automatic** on `*.vercel.app`. Browser live location (`app/lib/useGeolocation.ts`)
  and Web Push both require https, so they work there. They will not work on a plain-http host.
- **Custom domain (optional):** Settings → Domains → add the domain, then create the DNS record
  Vercel shows you.
- **Hobby plan terms:** Hobby is for non-commercial use, which covers an SIH submission. Usage
  limits are listed at <https://vercel.com/docs/limits>.

### 1.4 How to check the deployed frontend

1. Open the `.vercel.app` URL. The home page and the nav should render.
2. Open `/map`. The basemap tiles should appear. This confirms the MapLibre worker copy ran.
3. Open DevTools → Network, then open `/ask`. The requests should go to the
   `NEXT_PUBLIC_API_BASE_URL` host and **never to `localhost:8000`**. If you see localhost, the
   variable was not set when that deployment was built, so redeploy.
4. Once the backend is up, sign in and ask a question on `/ask`. **Do not register the shared
   agent account (`agent@orca.test`) on a deployed backend.** It exists only for local
   development, as the project's `CLAUDE.md` explains.

---

## 2. Backend

Not decided yet. The requirements and candidates as researched on 2026-09-29/30 are below.

- **Needs:** about 2.8 GB of `data/` (gitignored, so it must be copied up separately), Postgres
  with PostGIS, Redis, and roughly 3–5 GB of RAM with torch, IndicTrans2, faster-whisper and
  MMS-TTS loaded. The RAM figure is estimated from model sizes, not measured. Plan for 8 GB. The
  backend must be reachable over **https**, per §1.2.
- **Ruled out:**
  - Vercel: 500 MB Python bundle limit and 2 GB RAM.
  - Render and Koyeb free tiers: about 512 MB RAM.
  - New Docker Spaces on a free Hugging Face account: now a paid feature.
- **Candidates, cheapest and easiest first:**
  1. Azure for Students VM (B2ms, 8 GB): no card needed, paid from the $100 credit.
  2. Your own laptop behind a Cloudflare Tunnel.
  3. Hugging Face PRO for one month ($9), with Neon for Postgres and Upstash for Redis.
  4. A Google Cloud or AWS VM paid from their new-account credits (card needed).

To be filled in when the backend host is chosen: the host, the compose and HTTPS setup, copying
`data/` up, the production `.env` (a new `ORCA_JWT_SECRET` and a non-default Postgres password),
running `infra/db/*.sql`, and then setting `NEXT_PUBLIC_API_BASE_URL` in Vercel and redeploying
(§1.2, step 7).
