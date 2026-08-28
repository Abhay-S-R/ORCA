# ORCA (SIH26176) — Master Dataset List, Verified Aug 2026

This reconciles your two planning docs (v2 Build Plan + Master Analysis Doc) with a fresh check of each source's live portal. Nothing in your docs was wrong — this adds current confirmation, a few missing datasets, and the exact "what to request" language for each org.

---

## 1. Quick-reference comparison table

| # | Dataset / Source | Owner | What it gives ORCA | Access tier | Free tier? | Needs org permission? |
|---|---|---|---|---|---|---|
| 1 | MOSDAC Open Data | ISRO/SAC | SST, ocean color, wind, ocean currents, salinity — derived products | Anonymous | ✅ Free, no login | ❌ No |
| 2 | MOSDAC Registered (NRT/API/SFTP) | ISRO/SAC | Same as above but near-real-time + programmatic pull | Registered (General/Privileged) | ⚠️ Free but gated | ✅ Yes — SignUp + email approval |
| 3 | INCOIS PFZ Advisory (WebGIS/text) | INCOIS/MoES | Potential Fishing Zone points, ~1,223 coastal nodes | Public page | ✅ Free, no login | ⚠️ No login, but no clean API — email needed for bulk feed |
| 4 | INCOIS Ocean State Forecast (OSF) | INCOIS/MoES | Wave height, currents, SST, mixed layer depth, wind | Public page | ✅ Free | ⚠️ Same as above |
| 5 | INCOIS Hazard Alerts (Tsunami/Storm Surge/High Wave) | INCOIS/MoES | Operational hazard bulletins | Public | ✅ Free | ⚠️ Bulk/API — request |
| 6 | INCOIS Sagar Vani | INCOIS/MoES | Existing multi-channel advisory dissemination (reference model, not a data feed you pull) | N/A | N/A | ✅ Yes, if integrating rather than referencing |
| 7 | Bhuvan / VEDAS (NRSC) | ISRO/NRSC | Geoportal layers incl. PFZ, thematic ocean layers | Registered | ⚠️ Free but gated | ✅ Yes — separate signup from MOSDAC |
| 8 | IMD Cyclone/Weather Warnings | IMD/MoES | Cyclone bulletins, colour-coded warnings, district-wise alerts (issued 4×/day) | Public bulletins; CAP-based dissemination | ✅ Free | ⚠️ No unified public REST API confirmed — use CAP feed / bulletin scraping |
| 9 | Copernicus Marine Service (CMEMS) | EU/Mercator Ocean | Global SST, currents, salinity, sea level, waves — mature API | Registered | ✅ Free | ✅ Yes, but instant self-serve signup |
| 10 | NASA Ocean Color (OB.DAAC / MODIS-Aqua) | NASA | Chlorophyll-a, SST, remote-sensing reflectance | Earthdata Login | ✅ Free | ✅ Yes, instant self-serve (Earthdata account) |
| 11 | Global Fishing Watch API | GFW (Oceana/SkyTruth/Google) | Vessel AIS activity, fishing effort, encounters | API token | ✅ Free tier, rate-limited | ✅ Yes, instant self-serve token |
| 12 | Marine Regions / VLIZ Maritime Boundaries Geodatabase | Flanders Marine Institute | Authoritative EEZ, territorial sea, contiguous zone, IMBL-adjacent boundary polygons | Public download | ✅ Free | ❌ No — direct download, cite source |
| 13 | Protected Planet / WDPA (MPA polygons) | UNEP-WCMC/IUCN | Marine Protected Area boundaries (e.g., Gulf of Mannar Marine National Park) | Public download | ✅ Free | ❌ No, but register for bulk API pull |
| 14 | DAT-SG / Sagarmitra | ISRO + Coast Guard | Distress-alert transmitter integration point (reference/handoff, not a pullable dataset) | N/A | N/A | ✅ Yes, if integrating |
| 15 | data.gov.in (fisheries/catch statistics) | Govt of India (OGD platform) | Historical catch/landing statistics — needed for the "why did catch decline" query | Public/registered per dataset | ✅ Mostly free | ⚠️ Some datasets require registration |
| 16 | CMFRI catch/landing data | ICAR-CMFRI | Historical fish landing data, validated PFZ persistence studies | Publication/request-based | ⚠️ Mixed | ✅ Yes — many datasets are published in papers, not open APIs; direct request likely needed |

---

## 2. Analysis against your two docs

**What your docs already got right (confirmed live, Aug 2026):**
- MOSDAC's two-tier system (Open Data = free/anonymous; General/Privileged registered users = NRT + bulk) is confirmed exactly as described, including the 3-day latency for General users vs. NRT access for Privileged users, and the documented Data Download API + SFTP service.
- INCOIS PFZ is confirmed still WebGIS/text-page first, not a REST API — the ~1,223-node figure is verified live on `incois.gov.in/MarineFisheries/PfzWebGis`. Your "budget scraping time" mitigation stands.
- IMD still has no single unified public REST API for all alert types — it disseminates via bulletins, apps, and **Common Alerting Protocol (CAP)**, confirmed by a March 2026 government statement that IMD pushes district-wise warnings 4×/day via CAP, apps, WhatsApp, and social media. This is a stronger integration path than scraping: **target the CAP feed specifically**, not generic bulletin pages.
- Copernicus Marine and NASA Ocean Color are confirmed free with instant self-serve registration (Earthdata Login for NASA; Copernicus Marine account) — good fallback choices exactly as your doc positioned them.
- Global Fishing Watch confirmed free-tier API with a self-serve token from the GFW API Portal, rate-limited — matches your "optional/stretch" framing.

**Two things your docs under-specified that I'd add:**
1. **Maritime boundary data source was named generically ("official/published EEZ shapefiles") but never pinned down.** Use the **Marine Regions / VLIZ Maritime Boundaries Geodatabase** (Flanders Marine Institute) — it's the de facto authoritative, freely downloadable global EEZ/territorial-sea/IMBL-adjacent dataset used across GIS research, and it directly solves your Section 4 pain point ("geofencing correctness... don't hand-draw approximate lines"). No permission needed, just cite it.
2. **MPA boundary source was named narratively (Gulf of Mannar Marine National Park) but no dataset was named.** Use **Protected Planet / WDPA (World Database on Protected Areas)**, maintained by UNEP-WCMC and IUCN — it has the polygon for Gulf of Mannar and every other Indian MPA, free to download, bulk API available with a free registration.
3. **Historical catch/landing data for the "why did catch decline" query** — both docs flag this as the hardest query and suggest "CMFRI/INCOIS catch statistics" vaguely. Concretely: check **data.gov.in** first (Open Government Data platform — searchable, many datasets need no registration) before assuming you need a CMFRI research request; CMFRI's own granular data is often only available via direct request or embedded in published papers, which takes longer than a hackathon timeline allows — so data.gov.in should be your primary attempt, CMFRI email request a stretch/parallel action, not a dependency.

---

## 3. What to specifically request from each org (copy-paste-able asks)

**MOSDAC (mosdac.gov.in)** — after SignUp + email verification + approval:
- Ask for: **Registered General User access** (sufficient for most of your build) — only escalate to **Privileged/NRT access** if you specifically need near-real-time (not 3-day-latency) SST/ocean-color/wind for your live demo window.
- Additionally request: **API/SFTP credentials** explicitly — these are not automatically granted with SignUp alone.

**Bhuvan / VEDAS (bhuvan.nrsc.gov.in)** — separate registration from MOSDAC:
- Ask for: geoportal **API/WMS access** to the PFZ and thematic ocean layers you plan to overlay, not just browser-based viewing.

**INCOIS (ESSO-INCOIS, Hyderabad)** — direct email/contact-form request:
- Ask for: (a) a **structured/bulk data feed or documented API for PFZ advisories** for your specific coastal sector (North TN / South TN if you're following the Palk Bay/Gulf of Mannar pilot region), and (b) any **documented Ocean State Forecast API**, since the public interface is map/text only.
- Mention "SIH 2026, ISRO PS SIH26176" for context — this is a legitimate, common ask and may speed a response, but don't build your timeline assuming a fast reply; keep the scraping fallback live in parallel.

**Copernicus Marine (marine.copernicus.eu)**:
- Just self-serve register — no special ask needed, instant approval historically.

**NASA Earthdata / Ocean Color (urs.earthdata.nasa.gov)**:
- Just self-serve register for an Earthdata Login — required for any OB.DAAC download, but instant, no approval wait.

**Global Fishing Watch (globalfishingwatch.org/our-apis)**:
- Self-serve API token request through the GFW API Portal — only pursue if geofencing/vessel-tracking becomes an actual demo feature, not by default.

**data.gov.in**:
- Check per-dataset — most fisheries/catch datasets are open-download; a few require a free OGD platform account. No special request email needed typically.

**CMFRI (if pursuing historical catch-decline analysis beyond what data.gov.in offers)**:
- Ask for: any publicly citable **catch/landing time-series for your pilot region** (e.g., Thoothukudi sector) — treat this as a parallel, best-effort request, not a blocking dependency; your fallback is to scope the "why did catch decline" query narrowly around whatever historical data you can get from data.gov.in or published CMFRI papers.

**Marine Regions (VLIZ) / Protected Planet (WDPA)**:
- No request needed — direct shapefile/GeoJSON download. Just cite the source in your UI (both explicitly require attribution in their license terms).

---

## 4. Net priority order for Phase 0 (this week)

1. MOSDAC SignUp (has the longest approval lag historically — start first)
2. Bhuvan/VEDAS SignUp (same NRSC approval pattern)
3. Copernicus Marine + NASA Earthdata registration (instant, do in parallel, zero excuse to delay)
4. Global Fishing Watch token (instant, only if geofencing/route features are in scope)
5. Marine Regions EEZ + WDPA MPA downloads (no registration — just download and store locally now)
6. INCOIS direct email request (slow — send early, don't wait on it, build the scraping fallback regardless)
7. Confirm which data.gov.in catch/landing datasets exist for your pilot sector before committing to the root-cause query as a live demo feature
