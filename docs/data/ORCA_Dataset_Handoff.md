# ORCA — Dataset Handoff (replacing your `data/` with the shared one)

**Status:** active procedure. **Issued:** 2026-09-23.
**Grounded in:** `docs/ORCA_PS_SIH26176_Problem_Statement.md` (canonical),
`docs/ORCA_Data_Freshness_Contract.md` (which defines LIVE / DAILY / WEEKLY / STATIC),
`docs/ORCA_Stale_Data_Cleanup.md` (the register that produced this dataset), and
`docs/Guide/ORCA_Data_Refresh_Cron_Guide.md` (the refresh jobs referenced below).

---

## What this is, and why you are getting it

`data/` is gitignored. It has never been part of a clone, so every developer built their own copy
by running the refresh jobs, and every copy drifted differently. On 2026-09-23 one copy was audited
file by file against `docs/ORCA_Stale_Data_Cleanup.md` and **49 stale or orphaned files totalling
20.53 GB were deleted**, taking `data/` from 22.35 GB to about 2.3 GB. That trimmed copy is now the
single source of truth, and this document is how you adopt it.

Your current `data/` still holds those 49 files. They are not dangerous, they are dead weight: no
code path reads any of them, which was verified by removing all 49 at once and re-running the whole
suite. Adopting the shared copy is how you drop them without repeating that audit yourself.

**You are not expected to trust this blindly.** The archive ships with `MANIFEST.txt`, a SHA-256
and byte size for all ~26,400 files. Section 3 below is how you check every one of them.

## What you receive

| File | What it is |
|---|---|
| `orca_data_20260923.zip` | the whole of `data/`, stored relative to `data/` |
| `orca_data_20260923.zip.sha256` | digest of the archive, for checking the download |
| `MANIFEST.txt` | SHA-256 + size of every file (also inside the zip) |

---

## 0. The one rule

**Never be in a state where you have no working `data/`.**

Unpack and verify the new copy *first*, swap second, delete last. The procedure below is written
so that at every step you still have something that works. Do not reorder it to save disk —
you need about 6 GB free for the overlap (your existing `data/`, the unpacked copy, and the 1.29 GB
zip), which is far cheaper than re-downloading a dataset whose upstream streams are partly retired.

Read that again if you are tempted to `rm -rf data/` before unzipping. Some of what is in `data/`
**cannot be re-downloaded at any price** — the INCOIS RSMC bundle that carried `TEMP`, `SALN`,
`SSH`, `MLD`, `TCHP` was retired upstream. Nothing reads those variables any more, which is why
they were dropped deliberately rather than lost accidentally. The difference matters.

---

## 1. Check the download before you unpack it

WhatsApp and Drive both re-encode or resume transfers, and a truncated zip can still open.

```bash
cd /path/to/downloads
sha256sum -c orca_data_20260923.zip.sha256
```

On Windows without `sha256sum`:

```powershell
certutil -hashfile orca_data_20260923.zip SHA256
```

and compare it by eye with the contents of `orca_data_20260923.zip.sha256`.

**If it does not match, stop and get the file again.** Everything below assumes it did.

## 2. Unpack it beside your current `data/`, not over it

From the repo root:

```bash
unzip -q orca_data_20260923.zip -d data_new
```

You now have `data_new/` alongside your untouched `data/`. Nothing has been lost yet, and
nothing will be until section 4.

## 3. Verify every file

The manifest is inside the archive as well, so this checks what actually landed on your disk.

```bash
cd data_new
grep -E '^[0-9a-f]{64} ' MANIFEST.txt \
  | sed -E 's/^([0-9a-f]{64})[[:space:]]+[0-9]+[[:space:]]+/\1  /' > sums.txt
sha256sum -c --quiet sums.txt && echo "ALL FILES VERIFIED"
rm sums.txt
```

The `sed` just drops the size column, because `sha256sum -c` wants only `<hash>  <path>`.
`--quiet` prints nothing for files that pass, so silence followed by `ALL FILES VERIFIED` is
success; any line it does print is a file to worry about.

PowerShell equivalent, if you have no `sha256sum`:

```powershell
cd data_new
$bad = 0
Get-Content MANIFEST.txt | Where-Object { $_ -match '^[0-9a-f]{64}\s+\d+\s+' } | ForEach-Object {
    $p = $_ -split '\s+', 3
    if (Test-Path $p[2]) {
        if ((Get-FileHash $p[2] -Algorithm SHA256).Hash -ne $p[0].ToUpper()) {
            Write-Host "MISMATCH $($p[2])"; $bad++
        }
    } else { Write-Host "MISSING  $($p[2])"; $bad++ }
}
"$bad problem(s)"
```

Expect **0 problems**. A mismatch means the transfer was damaged; re-download rather than
continuing, because the rest of this procedure deletes your fallback.

## 4. Swap, and keep the old copy until you are sure

```bash
cd /path/to/orca
mv data data_old
mv data_new data
```

Two renames on the same volume, so this is instant regardless of size, and trivially reversible:
if anything goes wrong, `mv data data_new && mv data_old data` puts you exactly back.

## 5. Prove it works before deleting anything

Run all four. They take a few minutes and they are the whole point of keeping `data_old/` around.

```bash
cd backend
.venv/Scripts/python.exe -m orca.data.freshness          # see the note below about breaches
cd ..
backend/.venv/Scripts/python.exe scripts/build_pfz_fallback.py
backend/.venv/Scripts/python.exe scripts/verify_gazetteer_at_sea.py
cd backend && .venv/Scripts/python.exe -m pytest -q tests/unit
```

What a healthy result looks like:

| Check | Expected |
|---|---|
| `build_pfz_fallback.py` | 6 zones written, reading the newest `SST_NIO_*.nc` |
| `verify_gazetteer_at_sea.py` | `203 entries checked: 203 at sea, 0 no GEBCO coverage, 0 ON LAND` |
| `pytest -q tests/unit` | `700 passed, 1 skipped` |
| `orca.data.freshness` | `28 sources \| 0 breach(es)` — **but read the next section first** |

The suite exits 139 (a segmentation fault) *after* printing its summary, on runs that load torch.
That is a known interpreter-teardown crash, not a test failure — all 700 tests report a pass
before it happens. Judge the run by the summary line, not the exit code.

### Freshness will probably breach on arrival, and that is not damage

The DAILY sources in this archive carry content dated 2026-09-22/23. If you unpack it a few days
later, `orca.data.freshness` will report breaches immediately — typically `incois_osf_hycom`,
`incois_osf_ww3`, `mosdac_nrt_sst` and `mosdac_open_sst`, with an age of two days or more.

**This means the data is old, not missing.** The gate grades files by the date in the filename,
so a correct dataset still ages. Clear it by running the daily job once:

```bash
scripts\cron\refresh_daily.cmd
```

then re-run the freshness check and expect `0 breach(es)`, exit 0.

The discriminating question, whenever you see a breach after a change: **did the source's newest
content date move?** If its newest file is still the newest file, nothing was lost and you are
looking at age. If its newest file disappeared, that is damage. File *count* is not the signal —
this dataset has deliberately fewer files than yours.

## 6. Only now, delete the old copy

Once section 5 is green:

```bash
rm -rf data_old
```

Keep the zip until the whole team has done this and reported clean. It is the only copy of this
exact dataset state, and `data/` cannot be restored from git.

---

## 7. Afterwards: keep it current

This dataset goes stale on its own. Refresh it on a schedule rather than by remembering to:

- `scripts\cron\refresh_daily.cmd` — DAILY sources
- `scripts\cron\refresh_weekly.cmd` — WEEKLY sources

`docs/Guide/ORCA_Data_Refresh_Cron_Guide.md` §3 covers registering both as Windows scheduled tasks,
which needs an elevated PowerShell session. Both wrappers set `PYTHONIOENCODING=utf-8`; do not
remove that. Several gazetteer entries carry Tamil-script aliases, and on a cp1252 console the job
dies mid-run with a `UnicodeEncodeError` — including inside its own exception handler — so the
freshness gate never reports. When that bug was fixed, the first clean weekly run wrote ERA5
baselines for six ports that had never received one.

`orca.data.freshness` exits non-zero on a breach, which is deliberate: Task Scheduler records it in
`LastTaskResult`, so a silently stale dataset shows up as a failed task rather than nothing at all.

## 8. Do not repeat the stale-data delete

`docs/ORCA_Stale_Data_Cleanup.md` is marked **EXECUTED**. The 49 files it lists are already absent
from this archive. Running that register against the shared dataset will find nothing to do, and
its §5 rule ("keep one previous run") now refers to runs that are not in here. Treat it as the
reasoning behind this dataset, not as a task list.

If you find something in `data/` you believe is dead, do not delete it locally — the copies will
diverge again, which is the problem this handoff exists to solve. Raise it, and it gets removed
from the shared dataset once.
