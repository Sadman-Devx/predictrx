# Day 1 — Lead Dev checklist

## 1. Push the repo (once)
```bash
cd predictrx
git init -b main
git add .
git commit -m "chore: initial scaffold (backend, frontend, mcp-server, docs)"
git branch dev
# create an EMPTY repo on GitHub first (no README/.gitignore), then:
git remote add origin https://github.com/<your-username-or-org>/predictrx.git
git push -u origin main
git push -u origin dev
```
Before the first push run `git status` and make sure no `.env`, no `node_modules/`, no data files are staged.

## 2. GitHub settings
- Add the 4 teammates as collaborators (Settings → Collaborators).
- Protect `main`: require a pull request before merging; (optional) protect `dev` too.
- Optional: set `dev` as the default branch so PRs target it by default.
- Create a Project board (Todo / In progress / Review / Done) — Docs/QA runs it.

## 3. Each teammate's first commands
```bash
git clone https://github.com/<owner>/predictrx.git && cd predictrx
git checkout dev && git checkout -b feature/<area>-setup
cp .env.example .env
```
Then follow the Quick start in `README.md`.

## 4. Lead's other Day 1 tasks
- [ ] Fill `docs/scope-lock.md` (core vs cuttable, KPI table, open questions)
- [ ] Skim `.cursor/rules/` and adjust to how the team actually works
- [ ] Share `docs/roadmap.md` → "Member Task Plan" with the team
- [ ] Start reading openFDA + DDInter terms and fill `data/SOURCES.md` (due Day 2)
- [ ] Review the first PRs from teammates (setup verification)

## 5. End-of-day check
- [ ] Everyone can push a branch and open a PR into `dev`
- [ ] Backend dev's `runserver` + Frontend dev's `npm run dev` both work
- [ ] Portal deadline confirmed (Docs/QA)
