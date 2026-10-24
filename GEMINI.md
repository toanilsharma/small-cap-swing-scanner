# Security & Confidentiality Rules

## Core Directives
1. **No Hardcoded Secrets or Tokens**:
   - NEVER commit or hardcode `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, GitHub Personal Access Tokens (PAT), or API keys into any source code, tests, documentation, or commit messages.
   - All credentials must be read exclusively from environment variables locally (`.env` which is git-ignored) and from GitHub Actions Secrets (`${{ secrets.TELEGRAM_BOT_TOKEN }}`, `${{ secrets.TELEGRAM_CHAT_ID }}`) in CI/CD.

2. **Public Repository Safety**:
   - Assume this repository may be public. Therefore:
     - Keep `.env` strictly in `.gitignore`.
     - Never expose secrets in log outputs or error messages.
     - Never put sensitive tokens or auth bypass keys in client-side static JavaScript files.

3. **Dashboard Password Protection**:
   - The trading terminal and portfolio dashboard must require login password protection.
   - Never embed actual sensitive passphrases or unhashed secret keys in client-side JavaScript committed to the public repo.
   - Authentication must be validated against environment variables (e.g., Netlify environment variables `DASH_KEY_HASH`).

4. **Trading & State Privacy**:
   - Ensure trade history, open positions, and alert configurations are safeguarded against unauthorized tampering or unintended public exposure.
