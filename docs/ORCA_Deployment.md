# ORCA — Deployment

> Living document. It records where each part of ORCA is deployed, how to redo it, and what state
> it is in. Update the status table whenever a step is done.

## Status

| Part | Host | Status |
|---|---|---|
| Frontend (Next.js, `frontend/`) | Vercel, Hobby plan (free) | **In progress.** The repo is ready (§1.1). The Vercel project has not been created yet (§1.2). |
| Backend (FastAPI, `backend/`) | Render, free web service, prebuilt Docker Hub image (§2) | **In progress.** The repo is ready (§2.1). The image is not pushed and the service is not created yet. |
| Postgres + PostGIS | Neon, free plan (§2.3) | Not started |
| Redis | Render Key Value, free (§2.4) | Not started |

**Until the backend is deployed, the Vercel site loads but every API call fails.** Every page is
built statically and gets all of its data from the backend.

---

## 1. Frontend on Vercel

### 1.1 What the repo already does for Vercel

- **On Vercel, `frontend/next.config.ts` defaults `NEXT_PUBLIC_API_BASE_URL` to the planned Render
  backend, `https://orca-backend.onrender.com`,** so the frontend deploys before the backend
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
  `orca-backend.onrender.com` is in `.next/static/chunks` with no `localhost:8000`.
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
     | `NEXT_PUBLIC_API_BASE_URL` | The backend's public **https** URL, with no trailing slash | **No, not for now.** If unset, it defaults to `https://orca-backend.onrender.com`. Set it only if Render gives the backend a different URL. |
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
`https://orca-backend.onrender.com`. Pages load, but anything that needs the API shows an error
until the Render service with that name is live (§2.5). Nothing needs redeploying then, unless
Render assigns a different URL.

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

## 2. Backend on Render (free)

The plan: a **Render free web service** running a **prebuilt Docker image** that already contains
`data/`, with **Neon** (free) for Postgres + PostGIS and **Render Key Value** (free) for Redis.

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
   docker build -f infra/render/Dockerfile -t <dockerhub-user>/orca-backend:render .
   docker push <dockerhub-user>/orca-backend:render
   ```
   The first push uploads several GB: the code image plus about 2.8 GB of `data/`. Later pushes
   upload only the changed layers. Render's limit is 10 GB compressed.

### 2.3 Postgres on Neon (free, PostGIS)

Render's own free Postgres **expires 30 days after creation**, which is before mid-December, so
use Neon instead.

1. Sign up at <https://neon.tech>, create a project in region AWS Asia Pacific (Singapore), and
   copy the **connection string**. It looks like
   `postgresql://user:pass@ep-….neon.tech/neondb?sslmode=require`.
2. Run the migrations against it from the repo root. `psql` comes from the PostGIS image, so
   nothing needs to be installed:
   ```bash
   MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD/infra/db:/db" -e DATABASE_URL="<neon-url>" \
     postgis/postgis:16-3.4-alpine bash /db/migrate.sh
   ```
   It prints `apply 001_init.sql` … `migrations up to date`. `001_init.sql` runs
   `CREATE EXTENSION postgis`, which Neon supports. Running it again is safe, because files that
   were already applied are skipped.

### 2.4 Redis on Render Key Value (free)

In the Render dashboard, click **New → Key Value**. Name it `orca-redis`, choose the **Free**
plan, and use the **same region as the web service** (Singapore). Copy its **Internal Key Value
URL** (`redis://red-…:6379`).

Redis is only a cache here. The free Key Value is in-memory and is wiped on restart, which just
means the next query is uncached. If Redis is unreachable, the backend runs uncached after a 1 s
timeout instead of failing.

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
   - **Name:** `orca-backend`, which gives `https://orca-backend.onrender.com`. If that name is
     taken, Render adds a suffix. Use whatever URL it shows.
   - **Region:** Singapore. It is the closest to India, and it must match Key Value.
   - **Instance type:** Free.
   - **Health check path** (under Advanced): `/health`.
4. **Environment variables.** Copy the values from your local `.env`, **except** these, which must
   be new or different:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string (§2.3) |
   | `REDIS_URL` | the Key Value internal URL (§2.4) |
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
  restart. That is fine for ORCA: users and chats live in Neon, and the cache in Key Value.
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
  `docs/ORCA_Prompt_Routing_Revamp.md`, not a deployment issue. With `ORCA_LOCAL_MODELS=0` the e5
  routing tier is off, so routing relies on the LLM read and on word overlap.
- The 512 MB headroom was measured with the queries above run one after another. Several judges
  querying at the same moment could still exceed it. **Render Starter** ($7/month) is also
  512 MB, so it does not help. **Standard** ($25/month, 2 GB) does, and it also fits
  `ORCA_LOCAL_MODELS=1`.

