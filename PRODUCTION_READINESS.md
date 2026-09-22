# Production Readiness Checklist

This file is the canonical checklist for the remaining production work. An item is only complete after implementation and verification.

## P0: Required Before Real Users

- [ ] Meta Instagram end-to-end validation with a real Professional account and approved permissions
- [ ] Supabase DNS/project recovery, schema application, and read/write verification
- [~] User isolation and RLS: optional Supabase login, authenticated sessions, RLS, local library namespaces, and job ownership are implemented; production migration and real-project verification remain
- [~] Real-data dashboard: local/Meta data takes priority and source/account/period filters are implemented; production Supabase read verification remains
- [~] HTTPS deployment: Docker, worker, Nginx gateway, health check, and mobile-coach route are prepared; a public domain, TLS termination, OAuth redirect, and real-phone verification remain

## P1: Operational Reliability

- [~] Background video-analysis queue: persistent SQLite queue, worker, progress, pending/running cancellation, late-result protection, retry, and deduplication are implemented; production process supervision remains
- [~] Scheduled Meta synchronization: unattended multi-user encrypted-token runner, service-role cloud writes, 24-hour/3-day/7-day comparisons, and a verified daily Windows task are implemented; a real long-lived token remains
- [~] Competitor tracking operations: runner, verified weekly Windows task, three-attempt retry, run history, stable-media comparison, and duplicate-alert suppression exist; real watch data and production collection verification remain
- [~] Notification channels: Slack, Discord, and generic webhook formats, per-user enable/threshold preferences, 14-day deduplication, and delivery receipts exist; production webhook verification remains
- [~] Audio rights workflow: conservative classification, evidence files, URLs, source, notes, and expiry enforcement exist; real library availability still requires human verification
- [~] Creator learning: confidence thresholds and recency weighting exist; real measured samples remain
- [~] Prediction validation: account bias calibration and an 80% residual interval exist; a larger real validation dataset remains

## P2: Quality, Security, And Release

- [ ] Real iPhone Safari and Android Chrome validation
- [~] Security and privacy: RLS, user namespaces, encrypted persistent Meta tokens, log redaction, ZIP export, dry-run-first deletion, retention purge, cloud account deletion, and a privacy document exist; production key management and real-project verification remain
- [~] Observability: rotating JSON logs, operation duration/failure events, API usage ledger, daily Gemini/Apify limits, an in-app operator dashboard, and optional Sentry wiring exist; production DSN verification remains
- [~] Integration testing: 31 tests, worker workflow, queue cancellation, multi-user Meta paths, token encryption, privacy, alerts, and all five Streamlit navigation routes exist; real Meta/Supabase and real-device workflows remain
- [ ] Repository review, feature commits, legacy nested-project cleanup, and release tag

## Current External Blockers

- Supabase host does not resolve in DNS with the current configured URL.
- No `META_ACCESS_TOKEN` or verified Meta OAuth account is available.
- HTTPS deployment target and public domain are not configured.
