# Contributing (team of 5)

## Branches
- `main` — tested, demo-ready. Only merged from `dev`.
- `dev` — integration branch. Everyone's PRs land here.
- `feature/<area>-<short-name>` — your work, e.g. `feature/backend-patients-api`, `feature/frontend-review-screen`.

## Flow
1. `git checkout dev && git pull`
2. `git checkout -b feature/<area>-<name>`
3. Small commits, clear messages (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
4. Open a PR into `dev`. Fill the PR template. **Lead Dev reviews** before merge.
5. `main` is updated from `dev` only after QA passes.

## Rules (short version — full list in `docs/rule.md`)
- Never commit `.env`, secrets, datasets, prescription images, or real patient data.
- No dosing/stop/start text anywhere. No "safe" state. Every warning needs a source.
- Backend: logic in `services.py`, audit every patient-data access, LLM work in Celery.
- Frontend: all strings via i18n (Bangla default), tokens only, severity never by colour alone.
- Run before opening a PR: `cd backend && pytest` and `cd frontend && npm run build`.
- **Feature freeze: 16 Nov.** After that, bug fixes only.
