# Security, Credentials & Access Rules

## 1. Secrets & Token Isolation
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` must NEVER be hardcoded into Python files, workflow YAMLs, config files, or git commits.
- All secrets must be loaded via environment variables (`os.getenv(...)`) or GitHub Actions Secrets (`${{ secrets.TELEGRAM_BOT_TOKEN }}`).
- `.env` must remain strictly ignored in `.gitignore`.

## 2. Dashboard Password Protection
- The web dashboard (`/dashboard`) must enforce password protection.
- Avoid committing static auth bypass keys or plain passwords into client-side code (`app.js`, `login.js`) when the repository is public.
- Store verification hashes in deployment environment variables (e.g. Netlify's `DASH_KEY_HASH`).

## 3. Public Repository Precautions
- When the repository is public, anyone can view code, workflow definitions, and git commit history.
- Never output full tokens into workflow run logs or print them during tests or exceptions.
