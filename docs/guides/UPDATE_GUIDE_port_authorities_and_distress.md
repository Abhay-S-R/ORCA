# Update Guide — Port Authorities, Distress Survival Guidance & Incident Dispatch

> **For teammates and AI agents:** Follow these steps in order after pulling the latest changes from `main`. Run each verification step to ensure your local PostgreSQL database, backend, and frontend are synchronized.

---

## 1. What Changed

This update enhances ORCA's **Distress Agent (Agent 12)** and **District Ops (`/ops`)** emergency response pipeline:

1. **Actionable Emergency Survival Guidance**:
   - The distress agent now returns tailored, life-saving survival instructions to mariners in distress while authorities are en route.
   - 5 specialized emergency categories are handled deterministically (CI model-free compliant):
     - **Sinking / Flooding**: Life jackets, bilge pumps & breach plugging, Mayday VHF 16, grab bag/life raft, stay with hull, H.E.L.P. cold water posture.
     - **Medical Emergency**: Direct compression bleeding control, recovery position, CPR, deck evacuation prep, shock/hypothermia prevention.
     - **Engine Failure / Adrift**: Sea anchor/drogue deployment, PAN-PAN urgency call, day shapes & navigation lights, holding anchor, power/water conservation.
     - **Man Overboard (MOB)**: Immediate flotation toss, continuous pointing watch, GPS MOB waypoint, upwind sea break maneuver, hypothermia treatment.
     - **General Emergency**: PFD fastening, VHF 16 Mayday, visual flares/smoke, stay with vessel, phone battery preservation.
2. **Coastal Authority Accounts for Every Major Port**:
   - Standardized accounts created for 12 major Indian ports (Mumbai, Chennai, Thoothukudi, Kochi, Visakhapatnam, Mangalore, Rameswaram, Kanyakumari, Paradip, Veraval, Kakinada, Kolkata/Haldia).
   - Each account has:
     - **Email**: `authority.<port_slug>@orca.test` (e.g. `authority.mumbai@orca.test`)
     - **Password**: `orca-authority-local-dev`
     - **Role**: `authority`
     - **Default Persona**: `coastal_authority`
3. **Automated Authority Alert Dispatch**:
   - When a user sends a distress query (e.g. *"Our boat is sinking near Mumbai"*), the system resolves the user's home port (or GPS coordinates) to the responsible coastal authority.
   - Triggers an in-app `danger` alert notification directly into that coastal authority's account (`/alerts` and live SSE stream).
   - Enqueues the incident in the District Ops (`/ops`) distress queue with the assigned authority badge, target port, and survival instructions.
4. **UI Upgrades**:
   - **Fullscreen Red Alert Takeover**: Automatic emergency overlay triggered on distress queries with an authentic synthesized alarm siren looping continuously, contact details for Coast Guard & Coastal Authority, well-formatted numbered cards for **CRITICAL SURVIVAL ACTIONS WHILE AUTHORITIES REACH YOU**, sound mute/unmute control, and a close button.
   - **Formatted Chatbot Distress Response**: Dedicated emergency card in the chat with one-touch dial buttons (`tel:`), VHF Channel 16 badges, categorized survival checklists, and a button to re-open the fullscreen red alert screen.
   - **`/ops` Console**: Emergency beacon banner, assigned coastal authority badge, port filter ("All sectors" vs "Assigned to your port"), and collapsible vessel survival guidance view.

---

## 2. Step 1 — Pull Latest Changes

From your repository root:

```bash
git pull origin main
```

Check that the new migration and files are present:
- `infra/db/010_port_authorities_and_distress.sql`
- `scripts/seed_port_authorities.py`
- `backend/orca/ops/port_authorities.py`
- `backend/tests/unit/test_port_authority_distress.py`
- `frontend/app/components/DistressAlertOverlay.tsx`
- `frontend/app/components/DistressChatCard.tsx`

---

## 3. Step 2 — Apply the Database Migration

The update adds columns (`target_port`, `authority_name`, `survival_suggestions`) and an index to `distress_events`.

Make sure your Postgres container is running:
```bash
docker ps --format "{{.Names}} {{.Image}}"
```
*(Look for `orca-postgres-1` or `orca-postgres`).*

### Option A — Using Docker (Recommended for Windows / WSL)

Copy and execute the migration file inside the Postgres container:

```bash
docker cp infra/db/010_port_authorities_and_distress.sql orca-postgres-1:/tmp/010.sql
```

```bash
docker exec orca-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d orca -v ON_ERROR_STOP=1 --single-transaction -f /tmp/010.sql -c "INSERT INTO schema_migrations (filename) VALUES ('"'"'010_port_authorities_and_distress.sql'"'"') ON CONFLICT DO NOTHING;"'
```

### Option B — Using `migrate.sh` (If `psql` is installed locally)

```bash
DATABASE_URL="<value of DATABASE_URL from your .env>" ./infra/db/migrate.sh
```

### Verify Migration Success

Run this check inside the container:

```bash
docker exec orca-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d orca -tAc "SELECT column_name FROM information_schema.columns WHERE table_name='\''distress_events'\'' AND column_name IN ('\''target_port\'', '\''authority_name\'', '\''survival_suggestions'\'');"'
```

**Expected output:**
```text
authority_name
survival_suggestions
target_port
```

---

## 4. Step 3 — Seed Coastal Authority Accounts

Seed all 12 port authority accounts into PostgreSQL:

```bash
python scripts/seed_port_authorities.py
```

*(Note: FastAPI also automatically runs this seeding routine on startup lifespan, so subsequent restarts keep accounts verified and updated).*

### Authority Accounts Roster

All authority accounts use the shared local-development password:  
**Password**: `orca-authority-local-dev`

| Port | Email | Authority Name | Emergency Unit |
|---|---|---|---|
| **Mumbai** | `authority.mumbai@orca.test` | Mumbai Coastal Authority | Mumbai Port Trust & Yellow Gate Coastal Police |
| **Thoothukudi** | `authority.thoothukudi@orca.test` | Thoothukudi Coastal Authority | Thoothukudi Coastal Security Group |
| **Chennai** | `authority.chennai@orca.test` | Chennai Coastal Authority | Chennai Port Trust & Coastal Police |
| **Kochi** | `authority.kochi@orca.test` | Kochi Coastal Authority | Cochin Port Signal Station & Coastal Police Kerala |
| **Visakhapatnam**| `authority.visakhapatnam@orca.test` | Visakhapatnam Port Authority | Vizag Port Operations & Coastal Security Police |
| **Mangalore** | `authority.mangalore@orca.test` | New Mangalore Port Authority | NMPA Signal Station & Coastal Security Police |
| **Rameswaram** | `authority.rameswaram@orca.test` | Rameswaram Coastal Police | Marine Police Station Mandapam / Rameswaram |
| **Kanyakumari** | `authority.kanyakumari@orca.test` | Kanyakumari Marine Police | Coastal Security Group Kanyakumari |
| **Paradip** | `authority.paradip@orca.test` | Paradip Port Authority | Paradip Marine Police & Port Signal Station |
| **Veraval** | `authority.veraval@orca.test` | Veraval Coastal Authority | Veraval Marine Police & Gujarat Maritime Board |
| **Kakinada** | `authority.kakinada@orca.test` | Kakinada Port Authority | Kakinada Port Operations & Marine Police |
| **Kolkata** | `authority.kolkata@orca.test` | Kolkata / Haldia Port Authority | Syama Prasad Mookerjee Port Control |

---

## 5. Step 4 — Run Backend Tests

Run the dedicated test suite to verify everything passes on your local machine:

```bash
cd backend
python -m pytest tests/unit/test_port_authority_distress.py tests/unit/test_distress.py -v
```

**Expected result:** `40 passed` (or `74 passed` if running the entire distress test group).

---

## 6. Step 5 — Start Services & Verify End-to-End

### 1. Start the Backend

From `backend/`:

```bash
# Windows
.venv\Scripts\uvicorn.exe orca.api.main:app --host 0.0.0.0 --port 8000 --reload --timeout-graceful-shutdown 3

# macOS / Linux
.venv/bin/uvicorn orca.api.main:app --host 0.0.0.0 --port 8000 --reload --timeout-graceful-shutdown 3
```

Check health:
```bash
curl http://localhost:8000/health
# Returns: {"status":"healthy"} (HTTP 200)
```

### 2. Start the Frontend

From `frontend/`:

```bash
npm run dev
```

### 3. End-to-End Walkthrough

1. **Submit a Distress Query as a User**:
   - Open `http://localhost:3000/ask`.
   - Ask: `"Our boat is sinking off Mumbai port"`.
   - Verify the response includes:
     - Coast Guard MRCC details (`+91-22-2438-8065` / `1554`, VHF Ch 16).
     - Dispatch alert line: `"Alert triggered and sent to Mumbai Coastal Authority (Mumbai Port Trust & Yellow Gate Coastal Police, Tel: 022-22612348). Authorities are mobilizing."`
     - Numbered checklist: `"CRITICAL SURVIVAL ACTIONS WHILE AUTHORITIES REACH YOU (Vessel Sinking / Taking on Water): 1. DON LIFE JACKETS... 2. ACTIVATE BILGE PUMPS..."`
2. **Log into the Mumbai Authority Account**:
   - Sign in via Watches / Login with:
     - **Email**: `authority.mumbai@orca.test`
     - **Password**: `orca-authority-local-dev`
3. **Inspect the Alert in `/alerts`**:
   - Navigate to `http://localhost:3000/alerts`.
   - Look for the high-priority `danger` alert:
     - **Title**: `🚨 DISTRESS ALERT: Mumbai Coastal Sector`
     - **Body**: Incident summary with coordinates, matched phrase, and notification of survival advice dispatched to the vessel.
4. **Inspect the Incident in `/ops` Console**:
   - Navigate to `http://localhost:3000/ops`.
   - You will see:
     - The top banner: `🚨 CRITICAL DISTRESS SIGNAL ACTIVE: Coastal authorities alerted & rescue units mobilizing.`
     - The event entry tagged with: `Assigned: Mumbai Coastal Authority` and `Your Port Unit`.
     - Expandable **"Vessel Survival Instructions"** detailing the exact steps given to the vessel.
     - Controls to **Acknowledge** or **Close** the incident.

---

## 7. Troubleshooting

- **`column "target_port" does not exist`**:
  - The migration in Step 2 was not applied. Re-run `docker cp` and `docker exec` commands in Step 2.
- **Port Authority Login fails (`Invalid credentials`)**:
  - Run `python scripts/seed_port_authorities.py` again to ensure the password hash is properly set in the `users` table.
- **TypeScript compile check**:
  - Run `npx tsc --noEmit` from the `frontend/` directory to verify frontend integrity.
