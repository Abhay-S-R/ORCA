# ORCA — Deployment

> Living document. It records where each part of ORCA is deployed, how to redo it, and what state
> it is in. Update the status table whenever a step is done.

## Status

| Part | Host | Status |
|---|---|---|
| Frontend (Next.js, `frontend/`) | Vercel, Hobby plan (free) | **Deployed** at <https://sagarsarathi.vercel.app>. Points at the backend once `NEXT_PUBLIC_API_BASE_URL` is set and it is redeployed (§1.2, step 7). |
| Backend (FastAPI, `backend/`) + `data/` | Render free, Singapore (§2) | **Deployed** at <https://orca-backend-render.onrender.com> on 2026-10-01, image `asrsyshash/orca-backend:render`. `/health` and `/query?q=hi` answered. Stress test pending (`docs/deployment/ORCA_Render_Stress_Test.md`). |
| Postgres + PostGIS | Supabase, free plan, Singapore (§2.3) | **Done.** All 10 migrations applied, PostGIS 3.3 checked. |
| Redis | Upstash, free plan, Singapore (§2.4) | **Done.** `PING` and set/get checked. |

**Until the backend is deployed, the Vercel site loads but every API call fails.** Every page is
built statically and gets all of its data from the backend.

## 0. The whole picture

ORCA is **four things to deploy**. `data/` is not a fifth: it always travels with the backend.

| # | Part | Where | Depends on the backend host? |
|---|---|---|---|
| 1 | Frontend | Vercel | **No.** It is already live. Once the backend exists, it only needs `NEXT_PUBLIC_API_BASE_URL` set and a redeploy. |
| 2 | Postgres + PostGIS (users, chats, watches, alerts) | Supabase (§2.3) | **No.** It is reachable from any host over the internet. Pick the region closest to the backend. |
| 3 | Redis (a cache only) | Upstash (§2.4) | **No.** It is reachable from any host. If Redis is down, the backend runs uncached. |
| 4 | Backend + `data/` | **Not decided** (§3) | This is the only part that changes with the host. |

**Where `data/` goes.** The backend reads `data/` (about 2.9 GB of forecasts, grids, tiles and
gazetteers) from its own filesystem, so `data/` must be **next to the backend, wherever the
backend runs**. It never goes to Vercel, Supabase or Upstash. How it gets there depends on the
kind of host:

| Kind of host | How `data/` gets there | Examples |
|---|---|---|
| **Container platform with no persistent disk** | **Baked into the image** by `infra/render/Dockerfile`: `orca-backend:render`, about 8.9 GB uncompressed. This is the current setup. | Render, Railway, Koyeb, Cloud Run, Azure Container Apps, Heroku, DigitalOcean App Platform |
| **Container platform with a volume** | Either baked into the image as above, or copied once onto a mounted volume. A volume needs the `ORCA_DATA_DIR` fix below first. | Render paid + Disk, Railway + Volume, Fly.io + Volume, Azure Container Apps + Azure Files, AWS ECS + EFS |
| **A virtual machine (VPS)** | **A plain folder on the VM's disk.** Copy it once with `scp`/`rsync`, or run the baked image. This is the only kind of host where the refresh jobs in `scripts/cron/` can also run next to the backend, so the data stays current without rebuilding. | Oracle Cloud, AWS EC2 or Lightsail, Google Compute Engine, Azure VM, DigitalOcean Droplet, Hetzner, Vultr, Linode |

**On any host other than a VM, the deployed `data/` is frozen at the moment the image was
built.** To update it, re-run the refresh scripts locally, then rebuild and push the image
(§2.2).

**Known before any host is chosen:**
- **CORS allows every origin** (`backend/orca/api/main.py`, marked local-dev only). It works as it
  is, but it should be restricted to `https://sagarsarathi.vercel.app` before the demo.
- **`ORCA_DATA_DIR` is only partly honoured.** `orca/data/loaders.py` reads it, but
  `orca/agents/discovery.py` and `orca/agents/geospatial.py` always use `<repo>/data`, which is
  `/data` in the image. Baking works. Mounting `data/` anywhere else than `/data` needs those two
  fixed first.

---

## 1. Frontend on Vercel

### 1.1 What the repo already does for Vercel

- **On Vercel, `frontend/next.config.ts` defaults `NEXT_PUBLIC_API_BASE_URL` to the planned Render
  backend, `https://orca-backend-render.onrender.com`,** so the frontend deploys before the backend
  exists. A value set in the Vercel dashboard always wins. Next.js bakes the value into the
  JavaScript at build time. Without the default, every call would silently fall back to
  `http://localhost:8000` (`app/lib/apiBase.ts`). **An `http://` value fails the build**, because a
  page served over https may not call http (mixed content). All of this only applies when
  Vercel's `VERCEL` variable is set, so local builds still use `localhost:8000`.
- `npm run build` runs `prebuild`, which copies the MapLibre worker into `public/maplibre/`.
  Vercel runs this automatically, so the map works without any extra step.
- Every route is static (`○` in the build output). There are no server functions, so the Hobby
  function limits do not apply to the frontend.
- Sign-in uses bearer tokens stored in `localStorage`, not cookies. Hosting the frontend and the
  backend on different domains therefore needs no cookie or SameSite setup. The backend already
  allows every origin (`CORSMiddleware(allow_origins=["*"])` in `backend/orca/api/main.py`).

Checked on 2026-09-30:

- `VERCEL=1 npm run build` with the variable unset: the build passes, and
  `orca-backend-render.onrender.com` is in `.next/static/chunks` with no `localhost:8000`.
- `VERCEL=1 NEXT_PUBLIC_API_BASE_URL=https://api.example.test npm run build`: that URL is baked
  in, not the Render default.
- With the variable set to `http://…`: the build fails with the guard's message.
- A local `npm run build` still bakes in `localhost:8000`.
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
     | `NEXT_PUBLIC_API_BASE_URL` | The backend's public **https** URL, with no trailing slash | **Yes, once the backend exists.** Until then it defaults to `https://orca-backend-render.onrender.com`, which is only right if the backend lands on Render under that exact name. On any other host, set it to that host's URL and redeploy (step 7). |
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

**Deploying before the backend exists:** leave the variable unset. The site deploys pointing at
`https://orca-backend-render.onrender.com`. Pages load, but anything that needs the API shows an error
until the Render service with that name is live (§2.5). Nothing needs redeploying then, unless
Render assigns a different URL.

### 1.3 After it is live

The production URL is **<https://sagarsarathi.vercel.app>**. This is the origin the backend's
CORS setting should allow.

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

## 2. Backend on Render (free)

**The backend host is not decided yet.** This section is the worked plan for one candidate: a
**Render free web service** running a **prebuilt Docker image** that already contains `data/`.
§3 lists every other candidate. Parts of this section are the same for every host:
- §2.1: what the image does.
- §2.2: building and pushing it. Most hosts can pull from Docker Hub.
- §2.3 and §2.4: Postgres and Redis.
- §2.5, step 4: the list of environment variables.

Only §2.5 steps 1–3 and §2.6 are specific to Render.

### 2.1 What the repo already does for Render

- **`ORCA_LOCAL_MODELS=0` is the one switch for every local model.** It covers IndicTrans2,
  faster-whisper, MMS-TTS, the e5 intent model and the Ollama rung
  (`backend/orca/local_models.py`). At `0` none of them is ever loaded, either at startup or on
  first use. Each falls through to the rung that already exists:
  - Bhashini for translation and speech.
  - Word overlap for intent routing.
  - Groq and Gemini for answers.

  **The Render image defaults it to `0`** (`infra/render/Dockerfile`). To turn the models on, set
  `ORCA_LOCAL_MODELS=1` in the Render dashboard. That needs a plan with at least 2 GB, since the
  models take about 1.3 GB once warmed.
- **Memory on the query path was cut to fit 512 MB.** Measured 2026-09-30 on the real image with
  `--memory=512m`, the switch at `0`, and uncached queries (`fresh=true`) in a row:

  | Query | Memory after | Result |
  |---|---|---|
  | (startup) | 174 MB | up |
  | `is it safe to fish near rameswaram today` | 279 MB | GO answer |
  | Tamil, Rameswaram safety | 310 MB | GO answer, Bhashini ta→en→ta |
  | `kal kochi ke paas samundar kaisa rahega` | 326 MB | Hinglish answer |
  | `pfzs near ktaka` | 337 MB | refused (see §2.8) |
  | `hi` | 337 MB | LLM greeting |

  Before the fixes, the first safety query peaked at 889 MB and was OOM-killed. The three fixes:
  - **The bathymetry heatmap** strides the grid before reading it. It used to read the whole
    national GEBCO grid, about 190 MB, to keep one cell in every 200 × 200 block.
  - **The INSAT SST grid** is now cached in float32, for the newest granule only, cropped to India
    plus 5°. It was cached in float64 for up to four granules of the full disc, about 190 MB.
  - **`MALLOC_ARENA_MAX=2`** in `backend/Dockerfile` limits native-heap fragmentation across the
    agent threads.

  The outputs of the first two fixes were checked to be value-identical before and after, and the
  loader self-check passes after the crop.
- **Import and install fixes that were breaking the image:**
  - The e5 `ImportError: is_torch_npu_available` was a race between parallel warm-ups. All model
    loads now take one process-wide lock.
  - IndicTransToolkit was missing from `requirements.txt`. It is now listed for non-Windows.
  - `libexpat1` was missing from the slim image, so the rasterio engine failed. It is now
    installed.
- **The container listens on `$PORT`**, which Render sets. Elsewhere it falls back to 8000.
- **`data/` is baked into the image** by `infra/render/Dockerfile`. Render builds from git, which
  has no `data/` because it is gitignored, and free services have no disk. The accompanying
  `Dockerfile.dockerignore` lets in only `data/` and the one script the ban-order lookup reads,
  so **`.env` never enters the image.**

### 2.2 Build and push the image (your machine, once per backend change)

This needs Docker Desktop and a Docker Hub account. Render runs only `linux/amd64` images, which
is what an x86 Windows machine builds.

1. On <https://hub.docker.com>, **create a private repository** named `orca-backend`. It must be
   private because the image contains `data/`. Then go to Account settings → Personal access
   tokens → **Generate new token** with **Read-only** scope, which Render will use to pull. Copy
   the token.
2. From the repo root:
   ```bash
   docker login -u <dockerhub-user>
   docker build -t orca-backend backend
   docker build -f infra/render/Dockerfile -t <dockerhub-user>/orca-backend:render -t <dockerhub-user>/orca-backend:data-base .
   docker push <dockerhub-user>/orca-backend:data-base
   docker push <dockerhub-user>/orca-backend:render
   ```
   The first push uploads several GB: the code image plus about 2.8 GB of `data/`. Later pushes
   upload only the changed layers. Render's limit is 10 GB compressed.

   **Automated deployments:**
   - **Code-only updates:** Handled automatically on `git push main` by GitHub Actions
     (`.github/workflows/deploy-render.yml`), pulling the immutable `<dockerhub-user>/orca-backend:data-base`
     tag, patching code onto it, pushing to `render`, and hitting Render's deploy hook (preventing Docker layer accumulation).
   - **Data updates:** `scripts/deploy_data.cmd` (or `scripts/deploy_data.sh`) automates the build, push, and Render hook
     trigger. Both `scripts/cron/refresh_daily.cmd` and `scripts/cron/refresh_weekly.cmd`
     automatically call `scripts/deploy_data.cmd` after their freshness gate passes.


### 2.3 Postgres + PostGIS on Supabase (free), for every host

**This step is the same whichever backend host is chosen.** The local database is 79 MB
(measured 2026-09-30), so it fits every free plan below.

**Why Supabase and not Neon.** Sentinel (`orca/sentinel_runtime.py`) touches Postgres every
120 s (`ORCA_SENTINEL_INTERVAL_S`) and holds a session-level advisory lock on an open connection.
On an **always-on** backend this keeps the database awake all month:

- **Neon Free** meters compute, at 100 CU-hours per project per month, and scales to zero after
  5 idle minutes. Awake all month at the minimum 0.25 CU is about 182 CU-hours, so the project
  would be suspended around day 16.
- **Supabase Free** does not meter compute hours. It only pauses a project after a week with no
  activity, which Sentinel prevents.

Neon is still fine if the backend sleeps when idle (Render free), because Sentinel sleeps with
it.

Render's own free Postgres expires 30 days after creation, so it is not an option.

| | Supabase Free (recommended) | Neon Free (only with a sleeping backend) |
|---|---|---|
| Storage | 500 MB database | 0.5 GB per project |
| Compute | Shared CPU, 500 MB RAM, no hour limit | 100 CU-hours per project per month; scales to zero after 5 min idle |
| Pausing | After 1 week with no activity; resume by hand in the dashboard | Wakes itself on the next query (a few hundred ms) |
| Asia regions | Mumbai (`ap-south-1`), Singapore, and others | Singapore, Sydney |
| PostGIS | Yes, `CREATE EXTENSION` | Yes, `CREATE EXTENSION` |
| Which connection string | **Session pooler, port 5432.** The direct string is IPv6-only on Free, and most hosts only have IPv4. The transaction pooler (6543) breaks Sentinel's advisory lock. | **The direct string** (no `-pooler` in the host). Neon's pooler is transaction-mode, which breaks the advisory lock. |

Steps:

1. Sign up at <https://supabase.com> and click **New project**. For **Region**, pick the one
   closest to the backend: **Singapore** for Render, Railway, Fly.io or DigitalOcean, and
   **Mumbai** for a host in India such as Cloud Run `asia-south1`, Azure Central India or
   AWS `ap-south-1`. If the backend host is still undecided, pick Singapore. Save the database
   password it asks for.
2. Click **Connect**, choose **Session pooler**, and copy the string. It looks like
   `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`.
   Copy it exactly: the user name is `postgres.<ref>`, not `postgres`. This string becomes
   `DATABASE_URL` on the backend.
3. Run the migrations against it from the repo root. `psql` comes from the PostGIS image, so
   nothing needs to be installed:
   ```bash
   MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD/infra/db:/db" -e DATABASE_URL="<session-pooler-url>" \
     postgis/postgis:16-3.4-alpine bash /db/migrate.sh
   ```
   It prints `apply 001_init.sql` … `migrations up to date`. `001_init.sql` runs
   `CREATE EXTENSION postgis`. Running it again is safe, because files that were already applied
   are skipped.

Sources, checked 2026-09-30: [Supabase pricing](https://supabase.com/pricing),
[Supabase regions](https://supabase.com/docs/guides/platform/regions),
[Supabase connection strings](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Supavisor FAQ (session vs transaction mode)](https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI),
[Neon Free plan limits](https://neon.com/faqs/free-plan-limits-and-quotas),
[Neon plans](https://neon.com/docs/introduction/plans).

### 2.4 Redis on Upstash (free), for every host

**This step is the same whichever backend host is chosen.** Redis is only a cache here. If it is
unreachable, the backend runs uncached after a 1 s timeout instead of failing.

**Upstash, not Render Key Value.** Render Key Value is only reachable from Render services unless
an IP allowlist is set up, and its free plan has only 25 MB. Upstash is reachable from any host
and its free plan has 256 MB.

| Upstash Free | |
|---|---|
| Data | 256 MB |
| Commands | 500,000 per month. A cache lookup is 2 reads and a miss adds 2 writes, so this covers thousands of questions a month. |
| At the limit | Rate-limited, not billed. The backend then runs uncached. |
| Asia regions | Singapore (`ap-southeast-1`), Mumbai (`ap-south-1`) |

1. Sign up at <https://upstash.com>, then **Create Database** → Redis, in the **same region as
   Postgres**. Keep it single-region: a replica spends the free command quota.
2. Copy the **TCP** connection string (`rediss://default:<password>@<name>.upstash.io:6379`),
   not the REST URL. This becomes `REDIS_URL` on the backend.

**If the backend ends up on Render**, Render Key Value also works: **New → Key Value**, Free
plan, the same region as the web service, and use its **Internal Key Value URL**. It is in-memory
and wiped on restart.

Sources, checked 2026-09-30: [Upstash Redis pricing](https://upstash.com/pricing/redis),
[Upstash limits](https://upstash.com/docs/redis/overall/pricing),
[Render Key Value](https://render.com/docs/key-value),
[Render inbound IP rules](https://render.com/docs/inbound-ip-rules).

### 2.5 Create the web service

1. Render dashboard → **Settings → Container Registry Credentials → Add credential**:
   - Registry: Docker Hub.
   - Username: your Docker Hub username.
   - Token: the read-only token from §2.2.
2. **New → Web Service → Existing Image**:
   - Image URL: `docker.io/<dockerhub-user>/orca-backend:render`.
   - Credential: the one you just added.
   - Click **Connect**.
3. Configure:
   - **Name:** `orca-backend`. That name was already taken on Render, so it added a suffix and
     gave `https://orca-backend-render.onrender.com`. Use whatever URL Render shows.
   - **Region:** Singapore. It is the closest to India, and it should match Supabase and Upstash (§2.3, §2.4).
   - **Instance type:** Free.
   - **Health check path** (under Advanced): `/health`.
4. **Environment variables.** Copy the values from your local `.env`, **except** these, which must
   be new or different:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the Supabase session-pooler string (§2.3) |
   | `REDIS_URL` | the Upstash TCP string (§2.4) |
   | `ORCA_JWT_SECRET` | **a new random value**, e.g. from `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Never reuse the local one. |
   | `ORCA_LOCAL_MODELS` | `0`. The image already defaults to it; setting it explicitly makes it visible and switchable in the dashboard. |

   What to copy and what to leave out:
   - **Copy** the LLM keys (`GROQ_API_KEY`, `GEMINI_API_KEY`, and so on) and the `ORCA_LLM_*`
     provider and model variables.
   - **Leave out** `ORCA_LLM_LOCAL_MODEL`, `OLLAMA_BASE_URL` and `ORCA_OLLAMA_*`, because there is
     no Ollama on Render.
   - **The `BHASHINI_*` keys are required.** With local models off, Bhashini is the only
     translation and speech rung.
   - The data-source keys (`STORMGLASS_API_KEY`, `COPERNICUS_*`, `GFW_API_KEY`,
     `EARTHDATA_TOKEN`, `MOSDAC_*`) and `VAPID_*` are optional, but copy them for the full
     experience.
   - `NEXT_PUBLIC_*` values belong to Vercel, not here.

   To list every name in your file: `grep -E '^[A-Z_0-9]+=' .env | cut -d= -f1`.
5. Click **Deploy**. The first deploy pulls the multi-GB image, so allow several minutes. The
   service is up when the log shows `Uvicorn running on http://0.0.0.0:10000` and the health
   check passes.
6. **Point the frontend at it:** in Vercel, set `NEXT_PUBLIC_API_BASE_URL` to the Render URL with
   no trailing slash, then **Redeploy** (§1.2, step 7).

**After any backend change:** rebuild and push (§2.2), then in Render click **Manual Deploy →
Deploy latest reference**. Pushing the same tag does not redeploy on its own.

### 2.6 Free-plan behaviour to know for the judges

- **The service sleeps after 15 minutes without traffic, and the next request takes a minute or
  more to wake it.** Expect the longer end, because the image is large. To keep it awake, a free
  uptime monitor such as <https://uptimerobot.com> can hit `https://<render-url>/health` every 5
  minutes. An always-on service uses about 744 of the 750 free instance-hours in a month, so this
  only fits if it is the workspace's only free web service.
- Render may restart a free service at any time, and the local filesystem resets on every
  restart. That is fine for ORCA: users and chats live in Supabase, and the cache in Upstash.
- **Do not register the agent account (`agent@orca.test`) on this backend.** It exists only for
  local development. Register a normal account through the deployed site.

### 2.7 How to check the deployed backend

1. Open `https://<render-url>/health`. It should return JSON, not an error page.
2. Open `https://<render-url>/query?q=hi`. It should stream `data:` lines ending in a
   `final_response` that contains an LLM-written greeting.
3. On the Vercel site, sign in and ask on `/ask`: `is it safe to fish near rameswaram today`.
   Expect a verdict (GO, CAUTION or NO-GO) with a written answer. Then ask the same question in
   Tamil. The answer should come back in Tamil, and the trace's language step should say Bhashini.
4. In Render → **Metrics**, memory should stay under 512 MB. If the service's events show `Out of
   memory`, note which query caused it.

### 2.8 Known, not fixed

- **`pfzs near ktaka` is refused as out of scope.** It is a chatbot read defect covered by
  `docs/plans/ORCA_Prompt_Routing_Revamp.md`, not a deployment issue. With `ORCA_LOCAL_MODELS=0` the e5
  routing tier is off, so routing relies on the LLM read and on word overlap.
- The 512 MB headroom was measured with the queries above run one after another. Several judges
  querying at the same moment could still exceed it. **Render Starter** ($7/month) is also
  512 MB, so it does not help. **Standard** ($25/month, 2 GB) does, and it also fits
  `ORCA_LOCAL_MODELS=1`.

### 2.9 Open-Meteo relay on Cloudflare Workers (free)

**The problem.** On Render, `api.open-meteo.com` answered `429 Too Many Requests` (Render log,
2026-10-01), so every safety answer used the cached weather snapshot (233 h old) and said
CAUTION. Open-Meteo's free API counts requests per IP address, and Render free sends from IPs it
shares with other customers, who use up that quota. Locally the same calls get 200.

**The fix.** `infra/cloudflare/open-meteo-proxy.js` is a Cloudflare Worker that forwards ORCA's
two Open-Meteo calls. Open-Meteo counts Worker traffic by the `CF-Worker` header Cloudflare adds,
not by IP ([open-meteo#1727](https://github.com/open-meteo/open-meteo/pull/1727)), so the Worker
spends its own free quota (10,000 calls a day). The data is the same Open-Meteo data, unchanged
and uncached. The Worker forwards only `/v1/forecast` and `/v1/marine`, and only with the
`X-Orca-Key` header, so it is not an open proxy and nobody else can spend the quota.

The backend uses it when `OPEN_METEO_PROXY_URL` is set (`_fetch_open_meteo` in
`orca/agents/weather_intelligence.py`). Unset, it calls Open-Meteo directly, as locally.

Steps:

1. Make a key: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Sign up at <https://dash.cloudflare.com> (free). **Workers & Pages → Create → Start with Hello
   World** (or **Create Worker**), name it `orca-open-meteo`, **Deploy**.
3. **Edit code**, replace everything with `infra/cloudflare/open-meteo-proxy.js`, **Deploy**.
4. The Worker → **Settings → Variables and Secrets → Add**: type **Secret**, name
   `ORCA_PROXY_KEY`, value the key from step 1. **Deploy**.
5. Check it from Git Bash, with the Worker's URL from its overview page:
   ```bash
   W=https://orca-open-meteo.<you>.workers.dev; K=<the key>
   Q='?latitude=9.28&longitude=79.31&hourly=wind_speed_10m&forecast_days=1'
   curl -s -o /dev/null -w "%{http_code} forecast\n" -H "X-Orca-Key: $K" "$W/v1/forecast$Q"
   curl -s -o /dev/null -w "%{http_code} marine\n"   -H "X-Orca-Key: $K" "$W/v1/marine$Q"
   curl -s -o /dev/null -w "%{http_code} no key (expect 403)\n" "$W/v1/forecast$Q"
   ```
   Expect `200`, `200`, `403`.
6. In Render → Environment add `OPEN_METEO_PROXY_URL` (the Worker URL, no trailing slash) and
   `OPEN_METEO_PROXY_KEY` (the same key). Rebuild and push the image (§2.2), then **Manual
   Deploy → Deploy latest reference**.
7. Ask a safety question on the site. The answer must not say "cached tier1 fallback" or
   "233 h old", and Render's Logs should show `v1/forecast ... 200 OK` with the Worker's host.

---

## 3. Choosing the backend host: every candidate

Checked on 2026-09-30 against each provider's own docs or pricing page where possible. Where only
third-party sources were found, the row says so. Prices are in USD unless marked €, and they
change often, so re-check the linked page before paying.

### 3.1 What ORCA's backend needs from a host

| Need | Value | Why |
|---|---|---|
| RAM | **≥ 512 MB** with `ORCA_LOCAL_MODELS=0`. The measured peak for one user is 337 MB (§2.1). **≥ 2 GB** with local models on, which use about 1.3 GB warmed. | Anything under 512 MB is out. 1 GB gives room for several users at once. |
| Image size | `orca-backend:render` is **8.9 GB uncompressed**: 4.3 GB of code and libraries plus 2.9 GB of `data/`. The code-only image is 4.3 GB. | Hosts with an image cap below this cannot run the baked image. |
| CPU architecture | `linux/amd64` | ARM hosts (Oracle A1, Hetzner CAX, AWS t4g) need the image rebuilt for `arm64` first. |
| Always on, or allowed to sleep | Sentinel is a background loop that polls every 120 s and sends the alerts. | A host that sleeps, or that gives no CPU between requests (Cloud Run request billing, Leapcell), sends no alerts while idle. Chat still works. |
| Region | India, or Singapore as the nearest alternative | Users are Indian fishers. US or EU hosting adds about 150–250 ms to every call. |

**How to read "Fits?":** ✅ runs the current image as it is · ⚠️ runs with a stated change or
limit · ❌ cannot run ORCA as it is.

### 3.2 Free forever (no credit needed)

| Provider | Specs (free) | Sleeps? | India or nearby | Image / disk limit | Fits? |
|---|---|---|---|---|---|
| **Render Free.** The plan in §2. | 512 MB RAM, 0.1 CPU. 750 instance-hours per workspace per month. No persistent disk. | Yes, after 15 min idle. About 1 min to wake, longer with this image. | Singapore | 10 GB **compressed** | ✅ Tested at 512 MB (§2.1). Sentinel stops while asleep. |
| **Oracle Cloud Always Free.** A VM. | **Ampere A1 (ARM): 2 OCPU, 12 GB RAM** (halved from 4 / 24 on 2026-06-15), plus 2 AMD micro VMs (1/8 OCPU, 1 GB). 200 GB block storage in total. | No | Mumbai and Hyderabad exist, but the VM must be in the home region chosen at sign-up | 200 GB disk | ⚠️ The best free specs, but the A1 is ARM, so the image needs an `arm64` rebuild. A1 capacity is often unavailable. A card is needed for verification. |
| **Google Compute Engine e2-micro, Always Free.** A VM. | 1 e2-micro (2 vCPU burstable, 1 GB RAM), 30 GB standard disk | No | **US regions only**: us-east1, us-west1, us-central1 | 30 GB disk | ⚠️ Runs it, but with 1 GB RAM and about 250 ms extra per call from India |
| **Northflank Developer Sandbox** | 2 services, 2 cron jobs, 1 database. CPU and RAM are **not published** ("limited"). Card required. | No | Not verified | Not published | ⚠️ Unknown until tried. The free cron jobs could run the data refresh. |
| **Koyeb Free** | 512 MB RAM, 0.1 vCPU, 2 GB SSD. One per organisation. | Yes, after 1 h idle | **Frankfurt or Washington only** | About 7 GB uncompressed on the free instance | ❌ The 8.9 GB image does not fit |
| **Railway Free** (after the 30-day, $5 trial) | 0.5 GB RAM, 1 vCPU, 1 GB ephemeral disk, 0.5 GB volume. $1 of credit per month. | — | Singapore | **4 GB image** | ❌ The image does not fit |
| **Hugging Face Spaces, CPU Basic** | 2 vCPU, **16 GB RAM**, 50 GB disk that resets on restart | Yes, when unused | Not selectable | 50 GB | ⚠️ **Creating a Docker Space now needs a paid plan (PRO)**, even though CPU Basic itself costs nothing. `data/` would have to be uploaded into a private Space repo. |

Sources: [Render free](https://render.com/docs/free),
[Render prebuilt images](https://docs.render.com/deploy-an-image),
[Oracle A1 cut (InfoQ)](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/),
[Google Cloud free tier](https://cloud.google.com/free),
[Northflank pricing](https://northflank.com/docs/v1/application/billing/pricing-on-northflank),
[Koyeb instances](https://www.koyeb.com/docs/reference/instances),
[Koyeb image size (staff answer)](https://community.koyeb.com/t/image-download-failure-for-past-few-days/2058/2),
[Railway plans](https://docs.railway.com/pricing/plans),
[HF Spaces overview](https://huggingface.co/docs/hub/en/spaces-overview).

### 3.3 Free credits (free for a while, then paid)

| Provider | Credit | What it runs well | Specs of the suggested size | India or nearby | Fits? |
|---|---|---|---|---|---|
| **Azure for Students** | **$100 for 12 months, no card.** A full-time student aged 18+ with a school email. Renewable yearly while a student. Also in the GitHub Student Pack. | **App Service (Linux), B1:** $13.14/month (US price). **Container Apps:** 180,000 vCPU-s, 360,000 GiB-s and 2 M requests free every month. Max 2 vCPU / 4 GiB in a Consumption-only environment. | B1: 1 core, 1.75 GB RAM. B2: 2 cores, 3.5 GB RAM, about $26/month. | Central India (Pune), South India | ✅ B1 runs it for about 7 months on the credit. On Container Apps, Sentinel needs min replicas = 1, which bills the idle rate 24/7. The image-size cap for App Service was not verified. |
| **AWS new account** (since 2025-07-15) | **$100 at sign-up + up to $100 more** from 5 onboarding tasks. "Free plan" accounts close after 6 months or when the credit runs out. | **EC2 t3.small** (free-plan eligible) as a VM, or **Lightsail**. **App Runner closed to new customers on 2026-04-30**, so it is not an option. | t3.small: 2 vCPU, 2 GB RAM. Lightsail $12 bundle: 2 vCPU, 2 GB, 60 GB SSD, 1.5 TB transfer in Mumbai, with **3 months free** for new accounts. | **Mumbai (`ap-south-1`)** | ✅ A VM in Mumbai: `data/` sits on disk and the refresh cron can run on the same machine. |
| **Google Cloud free trial** | **$300 for 90 days.** Card required. Resources are deleted 30 days after the trial unless upgraded. | **Cloud Run.** No image-size limit, up to 32 GiB RAM. Separate monthly free allowance. | 1 vCPU / 1–2 GiB is enough | **Mumbai (`asia-south1`)**, Delhi | ⚠️ Runs it, but with request-based billing there is no CPU between requests, so Sentinel stalls. It needs instance-based billing with min instances = 1, which uses the credit steadily. |
| **DigitalOcean via GitHub Student Pack** | $100–200 credit (sources disagree; check the pack page). Card needed on DigitalOcean. | **Droplet (VM):** $6 for 1 GB / 1 vCPU, **$12 for 2 GB / 1 vCPU**, $24 for 4 GB / 2 vCPU. **App Platform:** $25 for 2 GiB shared. | $12 Droplet: 2 GB RAM, 2 TB transfer | **Bangalore (BLR1)** | ✅ A Droplet runs it like any VM. The $4 Droplet's 10 GB disk is too small for the image. |
| **Heroku via GitHub Student Pack** | $13/month for 24 months | Basic dyno ($7): 512 MB, 1 per process type. Standard-2X ($50): 1 GB. | 512 MB–1 GB | **US and EU only** on the common runtime | ⚠️ Docker images have no size cap, but a boot-time limit applies. With far regions and 512 MB, it is a weak fit. |

Sources: [Azure for Students](https://azure.microsoft.com/en-us/free/students),
[Azure Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/),
[Azure Container Apps billing](https://learn.microsoft.com/en-us/azure/container-apps/billing),
[App Service Linux pricing](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/),
[AWS Free Tier change](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-free-tier-credits-month-free-plan/),
[EC2 free-tier instance types](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.md),
[App Runner availability change](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html),
[Lightsail FAQ](https://aws.amazon.com/lightsail/faq/),
[Google Cloud free trial FAQ](https://cloud.google.com/signup-faqs),
[Cloud Run quotas (no image-size limit)](https://docs.cloud.google.com/run/quotas),
[Cloud Run pricing](https://cloud.google.com/run/pricing),
[GitHub Student Pack](https://education.github.com/pack/),
[DigitalOcean Droplet pricing](https://www.digitalocean.com/pricing/droplets),
[DigitalOcean App Platform pricing](https://docs.digitalocean.com/products/app-platform/details/pricing/),
[Heroku limits](https://devcenter.heroku.com/articles/limits),
[Heroku dyno sizes](https://devcenter.heroku.com/articles/dyno-sizes).

### 3.4 Paid

**Managed container platforms.** You push the image; the platform runs it.

| Provider | Price for a size that fits ORCA | Specs | India or nearby | Image limit | Fits? |
|---|---|---|---|---|---|
| **Render Starter / Standard / Pro** | $7 / **$25** / $85 per month, plus the workspace plan | 512 MB, 0.5 CPU / **2 GB, 1 CPU** / 4 GB, 2 CPU. No sleep. Persistent disk available. | Singapore | 10 GB compressed | ✅ Standard is the step up from §2 and also fits `ORCA_LOCAL_MODELS=1`. |
| **Railway Hobby** | $5/month including $5 of usage. RAM is $10 per GB-month and CPU $20 per vCPU-month, so 1 GB always on is about $10–15/month. | Up to 48 GB RAM and 48 vCPU per service. 100 GB ephemeral disk, 5 GB volume. | Singapore | **100 GB** | ✅ |
| **Fly.io** | No free tier. shared-cpu-1x with 256 MB is about $2/month. Extra RAM is $5 per GB-month. Volumes are $0.15 per GB-month. | Machines up to 128 GB RAM | Mumbai (`bom`), Singapore (`sin`) | A **rootfs limit of 8 GB uncompressed** was reported in 2024; there is a `--rootfs-size` flag | ⚠️ The 8.9 GB image may exceed the rootfs limit. Putting `data/` on a Fly volume instead needs the `ORCA_DATA_DIR` fix (§0). |
| **Northflank (paid)** | $0.01667 per vCPU-hour + $0.00833 per GB-hour. 1 vCPU / 2 GB is $24/month. | 0.1 vCPU / 256 MB up to 32 vCPU / 256 GB | Not verified | Not published | ✅ Likely; the image limit is not published |
| **Zeabur Developer** (third-party data) | $5/month including $5 of credit, then usage | Up to 2 vCPU / 4 GB per service | Not verified | Not published | ⚠️ Unverified |
| **Sevalla** | S1: $10/month, **S2: $40/month** | S1: 0.5 CPU, 1 GB. S2: 1 CPU, 2 GB. (H1 at $5 has 0.3 GB, which is too small.) | Not verified | Not published | ⚠️ S1 or S2 |
| **Koyeb (paid instances)** | Usage-based | Larger instances. The image limit is 5 GB plus the instance's local SSD. | Frankfurt, Washington and others; no India | Depends on the instance | ⚠️ Needs an instance with a large enough SSD |
| **Leapcell** | Serverless, pay per use. Persistent servers are also offered (price not found). | You choose the memory; CPU scales with it. Goes dormant after about 30 min idle. | Not verified | Not published | ⚠️ Dormancy stops Sentinel |
| **Heroku** | Basic $7, Standard-1X $25, Standard-2X $50, Performance-M $250 | 512 MB / 512 MB / 1 GB / 2.5 GB | US and EU | Docker: no size cap, boot-time limited | ⚠️ Far regions |
| **DigitalOcean App Platform** | 1 GiB for $10–12/month, **2 GiB for $25/month** (shared) | 1 vCPU shared | Bangalore | Not verified | ✅ Likely |
| **Azure App Service (Linux)** | B1 $13.14/month, B2 about $26/month (US price; India may differ) | B1: 1 core, 1.75 GB. B2: 2 cores, 3.5 GB. | Central India | Not verified | ✅ |
| **Azure Container Apps** | Per second above the free grant | Up to 2 vCPU / 4 GiB (Consumption-only), 4 vCPU / 8 GiB (workload profiles) | Central India | Not verified | ✅ Needs min replicas = 1 for Sentinel |
| **Google Cloud Run** | Per second. Instance-based billing is needed for Sentinel. | Up to 32 GiB RAM | Mumbai, Delhi | **None** | ✅ |
| **AWS ECS Fargate** (and ECS Express Mode, AWS's App Runner replacement) | About $0.04048 per vCPU-hour + $0.004445 per GB-hour (us-east-1; Mumbai is dearer). 1 vCPU / 2 GB is about $36/month, plus a load balancer. | 20 GB ephemeral storage included, which holds the image, up to 200 GB | Mumbai | 20 GB ephemeral by default | ✅ |
| **AWS Lightsail containers** | Nano $7, **Micro $10** | Nano: 0.25 vCPU, 512 MB. Micro: 0.25 vCPU, 1 GB. 500 GB transfer. | Mumbai | Not verified | ⚠️ 0.25 vCPU is slow for the geospatial work |

**Virtual machines (VPS).** You get a Linux server and run `docker` on it yourself.

| Provider | Price | Specs | India or nearby | Notes |
|---|---|---|---|---|
| **AWS Lightsail** | **$12/month** (3 months free for new accounts) | 2 vCPU, 2 GB, 60 GB SSD, 1.5 TB transfer in Mumbai | **Mumbai** | Billed while stopped, too; only deleting it stops the charge |
| **AWS EC2** | t3.small is free-plan eligible on new accounts; pay-as-you-go after | 2 vCPU, 2 GB | **Mumbai** | Covered by the $100–200 credit |
| **DigitalOcean Droplet** | $6 / **$12** / $24 per month | 1 GB / **2 GB, 1 vCPU** / 4 GB, 2 vCPU | **Bangalore** | Per-second billing, capped at the monthly price |
| **Vultr Cloud Compute** | About $9.40–14.10/month, depending on region | 1 vCPU, 2 GB, 55 GB NVMe | **Bangalore, Mumbai, Delhi** | Backups add 20% |
| **Akamai (Linode) Shared** | $12/month headline; Mumbai may be priced higher | 1 vCPU, 2 GB, 50 GB SSD, 2 TB transfer | **Mumbai, Chennai** | |
| **Hetzner Cloud** | In Singapore, CPX from **€15.49/month**. The cheap CX and CAX plans are EU only and were marked unavailable in September 2026. | CPX12 (EU, €11.99): 1 vCPU, 2 GB, 40 GB NVMe | Singapore | Prices rose twice in 2026 |
| **Oracle Cloud (paid)** | Pay-as-you-go above the Always Free allowance | Ampere A1 and AMD shapes | Mumbai, Hyderabad | A pay-as-you-go account may improve A1 availability |
| **Google Compute Engine / Azure VM** | Pay-as-you-go, or from the trial credits | Any size | Mumbai, Delhi / Central India | |

Sources: [Render pricing](https://render.com/pricing),
[Railway plans](https://docs.railway.com/pricing/plans),
[Fly.io pricing](https://fly.io/docs/about/pricing/),
[Fly.io free trial](https://fly.io/docs/about/free-trial/),
[Fly.io rootfs limit report](https://community.fly.io/t/rootfs-8gb-uncompressed-limit-exceeded-error/18202),
[Northflank pricing](https://northflank.com/docs/v1/application/billing/pricing-on-northflank),
[Zeabur plans](https://zeabur.com/docs/en-US/billing/plans),
[Sevalla application pricing](https://docs.sevalla.com/billing/application-pricing),
[Koyeb storage and image size](https://www.koyeb.com/docs/reference/storage),
[Leapcell pricing](https://leapcell.io/pricing),
[Heroku dyno sizes](https://devcenter.heroku.com/articles/dyno-sizes),
[Heroku container registry](https://devcenter.heroku.com/articles/container-registry-and-runtime),
[DigitalOcean App Platform pricing](https://www.digitalocean.com/pricing/app-platform),
[Azure App Service Linux pricing](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/),
[Azure Container Apps containers](https://learn.microsoft.com/en-us/Azure/container-apps/containers),
[Cloud Run memory limits](https://docs.cloud.google.com/run/docs/configuring/services/memory-limits),
[AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/),
[Lightsail container services](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-container-services.html),
[Lightsail FAQ (Mumbai transfer)](https://aws.amazon.com/lightsail/faq/),
[Vultr vc2-1c-2gb](https://sparecores.com/server/vultr/vc2-1c-2gb),
[Akamai regional pricing](https://www.akamai.com/cloud/pricing),
[Hetzner price adjustment](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/).

### 3.5 Recommendation

- **To pay nothing: Render Free (§2).** It is already prepared and tested. The cost is a
  cold start of a minute or more after 15 idle minutes, and no Sentinel alerts while it sleeps.
  Before a demo, keep it awake with an uptime monitor on `/health` (§2.6).
- **If a team member is an eligible student: Azure for Students.** $100, no card needed, and an
  App Service B1 in Central India (1.75 GB) runs it always on for about 7 months.
- **Best overall for a small cost: a 2 GB VM in India.** Options: AWS Lightsail Mumbai ($12, with
  3 months free), EC2 t3.small on the new-account credit, a DigitalOcean Bangalore Droplet ($12),
  or Vultr Bangalore or Mumbai. It is always on, Sentinel runs, the latency to users is lowest,
  and **`data/` lives on the disk, so the refresh cron (`scripts/cron/refresh_daily.sh`) can run
  on the same machine.** On every other kind of host, `data/` stays frozen until the next image
  push.

Whichever is chosen, §2.3 (Supabase), §2.4 (Upstash) and the frontend's
`NEXT_PUBLIC_API_BASE_URL` redeploy stay the same.

