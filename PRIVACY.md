# Privacy And Data Retention

Reels-analyzer processes uploaded videos, Instagram account metrics, generated analyses, store profiles, and optional audio-license evidence.

## Storage

- OAuth tokens remain in the active Streamlit session unless an operator explicitly configures a server-side token.
- Authenticated local data is stored in a one-way hashed user namespace under `user_reels/`.
- Supabase rows are protected by Row Level Security and must be accessed with an authenticated user session.
- Logs redact fields that look like tokens, API keys, secrets, passwords, and authorization headers.

## User Controls

- Export: `python scripts/manage_user_data.py export AUTH_USER_ID`
- Preview deletion: `python scripts/manage_user_data.py delete AUTH_USER_ID`
- Apply deletion: `python scripts/manage_user_data.py delete AUTH_USER_ID --apply`
- Preview retention purge: `python scripts/manage_user_data.py purge --days 90`
- Apply retention purge: `python scripts/manage_user_data.py purge --days 90 --apply`

Deletion and purge commands default to dry-run behavior. Database deletion must also be executed against the production Supabase account so cascading foreign keys remove owned rows.
