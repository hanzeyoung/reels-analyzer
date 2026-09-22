# Reels Analyzer Development Notes

## Active Project Root

Use `E:\reels-analyzer` as the active project root.

The folders below are legacy local copies or broken environments and are intentionally ignored:

- `reels-analyzer/`
- `{app/`
- `venv/`
- `.venv/`
- `.venv311/`
- `.python-packages/`

The current working runtime uses:

- Python: `C:\Users\JEONGMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
- Local packages: `.python-test-packages`

## Run The App

```powershell
.\scripts\run_app.ps1
```

Then open:

```text
http://127.0.0.1:8501
```

The launcher also starts the mobile coach static server at:

```text
http://127.0.0.1:8502/mobile-coach.html
```

For phone camera access, deploy the coach over HTTPS and set `MOBILE_COACH_BASE_URL`. Plain LAN HTTP is not a secure browser context on most phones.

Use another port if needed:

```powershell
.\scripts\run_app.ps1 8502
```

## Verify Locally

```powershell
.\scripts\run_env_check.ps1
.\scripts\run_tests.ps1
```

For read-only external API checks:

```powershell
$env:PYTHONPATH="E:\reels-analyzer\.python-test-packages;E:\reels-analyzer"
$env:PYTHONDONTWRITEBYTECODE="1"
& "C:\Users\JEONGMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" scripts\api_smoke_check.py
```

## External Integrations

- Meta: configure app id, secret, redirect URI, and Instagram business scopes. OAuth tokens remain in the Streamlit session; an environment token is also supported for development.
- Supabase: apply `sql/schema.sql` before syncing. Local JSON data remains available if cloud sync fails.
- Weekly market watch: save at least one watch in the UI, set an optional webhook, then run `scripts\install_weekly_watch_task.ps1` from an administrator PowerShell.
- Audio rights: the app only marks a track safe when an approved source or business license record exists. Unknown and mainstream tracks remain review-required.

## Background Operations

- `scripts\run_app.ps1` starts both Streamlit and the persistent video-analysis worker.
- `scripts\run_job_worker.ps1 --once` processes at most one queued analysis for smoke testing.
- `scripts\run_meta_sync.ps1` performs one unattended Meta sync using `META_ACCESS_TOKEN`.
- `scripts\install_meta_sync_task.ps1` installs the daily 06:00 Windows task. Do not install it until a working long-lived token is configured.
- Set `REQUIRE_APP_LOGIN=true` only after Supabase Auth and the RLS schema have been applied and verified.

## Product Boundaries

- Timeline retention is a heuristic based on measured motion/audio signals plus Gemini diagnostics, not Instagram's private viewer-retention curve.
- Meta synchronization and OAuth require a real Professional account, app review/permissions where applicable, and valid production credentials.
- Commercial Music Library availability has no public per-track lookup in this app. The rights registry stores the source and evidence used for a human-verifiable decision.
- Store pattern recommendations remain provisional until enough measured posts exist; the UI exposes sample count and confidence.

## Current Status

- Streamlit app imports and serves locally.
- Unit tests pass.
- Local MP4 frame extraction works.
- Apify and Gemini read-only smoke checks pass.
- Supabase smoke check currently fails because the configured project host does not resolve in DNS. Update `SUPABASE_URL` and `SUPABASE_ANON_KEY` in `.env` after confirming the active Supabase project.
- Meta OAuth/insights cannot be end-to-end verified without a real approved Meta app and account token.
- `.env` contains real local keys and must not be shared.
