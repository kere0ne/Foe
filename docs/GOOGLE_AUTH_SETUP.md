# Google sign-in and persistent storage

## Google OAuth setup

1. Open [Google Cloud Console](https://console.cloud.google.com/) and select/create a project.
2. Configure the OAuth consent screen (Google Auth Platform). For a private test app, add your Google account as a test user; publish/verify the app as needed for public use.
3. Create an OAuth client ID of type **Web application**.
4. Add this exact authorized redirect URI: `https://foe-agent.onrender.com/api/auth/google/callback`.
5. In Render → Foe service → Environment, set:
   - `GOOGLE_CLIENT_ID` = the client ID from Google
   - `GOOGLE_CLIENT_SECRET` = the client secret (keep private)
   - `GOOGLE_REDIRECT_URI` = `https://foe-agent.onrender.com/api/auth/google/callback`
6. Redeploy and use **Continue with Google**. Foe validates the OAuth state cookie and Google's verified email, then issues its own 30-day session. Google access tokens are not stored.
7. Email/password registration and login endpoints have been removed from the application UI/API.

## Persist account and project data

Foe uses `DATABASE_URL` for PostgreSQL metadata (accounts, sessions, projects, tasks, and bot ownership). Add a PostgreSQL instance in Render or use another trusted PostgreSQL provider, then set `DATABASE_URL` to its private connection URL. The app creates its schema automatically. Protect the URL as a secret.

Project source files are stored on disk under `FOE_DATA_DIR`. To retain those files through deploys/restarts, attach a persistent disk to the web service and set `FOE_DATA_DIR` to its mount path, for example `/var/data`. The disk mount must be writable by the app. A database does not automatically preserve the source files. Render's free web service has ephemeral storage; don't claim durable saves until persistent storage is actually configured.

Existing local SQLite records are not automatically copied into PostgreSQL by this change. Back up/export any existing project data before switching database backends. If you have no existing data, start with a fresh database.

## Security

- Never put Google client secrets or the database URL in GitHub.
- Only use HTTPS in production.
- Keep OAuth redirect URIs exact; do not use wildcard redirect URIs.
- Review Google's consent screen publishing/testing status.
