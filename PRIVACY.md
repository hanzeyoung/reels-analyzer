# Privacy And Data Retention

Reels-analyzer processes uploaded videos, Instagram account metrics, generated analyses, store profiles, and optional audio-license evidence.

## Storage

- OAuth tokens remain in the active Streamlit session unless an operator explicitly configures a server-side token.
- Authenticated local data is stored in a one-way hashed user namespace under `user_reels/`.
- Supabase rows are protected by Row Level Security and must be accessed with an authenticated user session.
- Member accounts (built-in backend) are stored in `user_reels/accounts.json` with scrypt password hashes and per-account salts; plaintext passwords are never stored or logged. Five failed sign-ins lock an account for five minutes.
- Guest (signed-out) work is kept per session under `user_reels/guests/` and removed after 24 hours.
- Instagram OAuth `state` values are stored server-side as SHA-256 digests, single-use, bound to the requesting member, and expire after 15 minutes.
- Logs redact fields that look like tokens, API keys, secrets, passwords, and authorization headers.

## User Controls

- Export: `python scripts/manage_user_data.py export AUTH_USER_ID`
- Preview deletion: `python scripts/manage_user_data.py delete AUTH_USER_ID`
- Apply deletion: `python scripts/manage_user_data.py delete AUTH_USER_ID --apply`
- Preview retention purge: `python scripts/manage_user_data.py purge --days 90`
- Apply retention purge: `python scripts/manage_user_data.py purge --days 90 --apply`

Deletion and purge commands default to dry-run behavior. Database deletion must also be executed against the production Supabase account so cascading foreign keys remove owned rows.
