# Deployment: Microsoft Azure VM (Docker Compose)

Goal: a live URL that stays up around the clock for the judges, with the real data (drugs, interactions, label
chunks **with their embeddings**) and the full login system (email OTP through Gmail SMTP).

> Written 18 Nov 2026. The compose file and Caddyfile in this folder have not been run on a real VM yet. Work through
> section 9 (verification) and fix what it finds before the URL goes into the portal form.

```text
Judge / phone ──HTTPS──▶ Caddy (80/443, automatic certificate)
                           ├─ /api, /admin ─▶ api (gunicorn) ─┬─▶ db (Postgres + pgvector)
                           ├─ /static ──────▶ collected admin files   ├─▶ redis
                           └─ everything else ▶ frontend/dist (React) ├─▶ ollama (embeddings)
                                         worker + beat (Celery) ◀──────┤─▶ mcp (custom MCP server, SSE)
                                                                       └─▶ Gemini API (prescription scan, optional)
```

Only Caddy is reachable from the internet. Postgres, Redis, Ollama and the MCP server stay on the internal Docker network.

---

## 1. What `git clone` does NOT bring to the VM

Cloning gives you code and Docker files. It does **not** give you anything that lives in a Docker volume or is git-ignored:

| Item | On the VM after `git clone` | What to do |
|---|---|---|
| Code, `docker-compose.prod.yml`, Dockerfiles | yes | nothing |
| **Database content** (drugs, DDInter interactions, label chunks, **embeddings**) | **no: an empty database** | section 7: dump on your PC, restore on the VM |
| **Ollama models** (`bge-m3`) | **no: Ollama starts with no model** | section 7: `ollama pull` once |
| `.env` (keys, passwords, SMTP) | **no** (git-ignored) | section 4: create it on the VM |
| `data/raw/`, `data/processed/` | **no** (git-ignored) | not needed at runtime once the database is restored |
| `frontend/dist` (built UI) | **no** | section 6: build it |

Embeddings are stored in Postgres (`Chunk.embedding`, pgvector), not in Ollama. Ollama only computes vectors. So
restoring the database means **you do not re-embed the ~60k chunks**. Re-embedding on the VM would take hours.

---

## 2. Create the Azure VM

- Image: Ubuntu Server (LTS), x86-64. Authentication: **SSH key**, not a password.
- Size: the stack runs Postgres (with a vector index over ~60k chunks), Redis, Ollama (`bge-m3`), the API
  (3 gunicorn workers), a Celery worker, Celery beat, an MCP server and Caddy together. Ollama with `bge-m3` is the
  biggest single consumer. Start with **8 GB RAM** and **30 GB or more of disk**, then watch `docker stats` during
  an analysis in section 9. If everything stays comfortably below the limit you can try a smaller size; if a
  container is killed for memory, resize up. These are starting points, not measured requirements.
- Smaller VM option: leave Ollama out of the stack. The site still works (graph-only label search, no vector
  search), but the evidence is thinner, and you should say so in the pitch. Do not switch to another embedding model
  as a shortcut: the stored vectors are `bge-m3` (1024 dimensions) and would all have to be recomputed.
- Networking: give the public IP a **DNS name label** (Public IP address, Configuration). You get a stable name like
  `<label>.<region>.cloudapp.azure.com`. Use this name as `SITE_ADDRESS`.
- Network security group (inbound):

| Port | Source | Why |
|---|---|---|
| 80, 443 | Any | Caddy (certificate and site) |
| 22 | **Only your own IP** | SSH |
| everything else | closed | Postgres 5433, Redis 6379, Ollama 11434, MCP 8001 must **not** be open |

- Cost: set a **budget alert** in Azure Cost Management. Keep the VM running until the judging results are out, then
  stop or delete it.

---

## 3. Install Docker and get the code

```bash
ssh <user>@<label>.<region>.cloudapp.azure.com
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
git clone https://github.com/Sadman-Devx/predictrx.git && cd predictrx
```

Shortcut used in the rest of this file (run from `predictrx/deploy`):

```bash
cd ~/predictrx/deploy
alias dc='docker compose --env-file ../.env -f docker-compose.prod.yml'
```

---

## 4. Create `.env` on the VM

```bash
cd ~/predictrx
cp deploy/env.production.example .env
chmod 600 .env
nano .env        # fill every empty value; see the comments in the file
```

Points that have caused problems before:

- **Each key once.** django-environ keeps the *first* value it reads. A second `SCAN_VISION_LOCAL` or `EMAIL_BACKEND`
  line is silently ignored.
- For prescription scans through Gemini: `GEMINI_API_KEY` and `GEMINI_MODEL` set **and** `SCAN_VISION_LOCAL=false`.
  If `SCAN_VISION_LOCAL=true`, `ai/llm/router.py` always uses local Ollama and never calls Gemini.
- The Gemini key must be a **new** key. Never paste keys into chat apps or commit them; revoke any key that was shared.
- `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` and `FRONTEND_URL` must all use the public
  name. `FRONTEND_URL` ends up inside emailed links; if it says `localhost` the links are useless.
- `NUM_PROXIES=1`: Caddy is one proxy. Without it every visitor shares one IP and the 5/min login throttle becomes
  one bucket for everybody.
- The compose file sets `DJANGO_SETTINGS_MODULE=config.settings.production`, `DATABASE_URL`, `REDIS_URL`,
  `OLLAMA_BASE_URL` and `MCP_SERVER_URL` itself. Do not copy the dev values for those.

Generate secrets:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # DJANGO_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # POSTGRES_PASSWORD
```

---

## 5. Gmail SMTP and the 60-second OTP

Registration emails a one-time code. It is valid for **60 seconds** (`OTP_TTL_SECONDS` in
`backend/apps/accounts/email_verification.py`) and allows at most **5 wrong guesses**. Doctor and pharmacist accounts
cannot log in until the code is verified (`REQUIRE_EMAIL_VERIFICATION=true`).

1. Google Account, Security: turn on **2-Step Verification**.
2. Create an **App Password** at <https://myaccount.google.com/apppasswords>. It has 16 characters; write it into
   `.env` **without spaces**. Your normal Gmail password does not work.
3. In `.env`: `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST=smtp.gmail.com`,
   `EMAIL_PORT=587`, `EMAIL_USE_TLS=True`, `EMAIL_HOST_USER=<gmail address>`, `EMAIL_HOST_PASSWORD=<app password>`,
   `DEFAULT_FROM_EMAIL=PredictRx <gmail address>`.
4. After the stack is running (section 8), send a test mail:

```bash
dc exec api python manage.py sendtestemail you@example.com
```

5. Then register a new account in the UI and **time** it: mail arrives, code accepted, within 60 seconds. The UI has
   a resend action; if delivery is slow, use it. If nothing arrives: `dc logs --tail=100 api`.

Limits to plan around:

- Gmail caps how many messages an account may send per day, so do not rely on live registration for many judges.
- **Give the judges ready-made, already verified demo accounts** (section 8). Put the credentials in the portal
  notes, **not in the repository**.
- Do not weaken authentication to make the demo easier (`rule.md` section 3).

---

## 6. Build the frontend

The UI is a static build served by Caddy from `frontend/dist`. It calls `/api` on the same origin, so leave
`VITE_API_URL` unset.

```bash
cd ~/predictrx/frontend
# Optional Google sign-in: echo "VITE_GOOGLE_CLIENT_ID=<public client id>" > .env
# (and add https://<your host> as an authorized JavaScript origin in the Google console)
docker run --rm -v "$PWD":/app -w /app node:22 sh -c "npm ci && npm run build"
ls dist/index.html
```

`npm run build` runs `tsc -b` first: a TypeScript error stops the build. Rebuild after every frontend change.

---

## 7. Start the database, load the data, pull the model

### 7a. On your PC, before you leave: dump only the knowledge tables

Run from `backend/` on your PC (Git Bash or WSL; not PowerShell, which corrupts binary redirects). First write down
the counts so you can compare them on the VM:

```bash
docker compose exec db psql -U predictrx -d predictrx -c "
select (select count(*) from drugs_drug) drugs, (select count(*) from drugs_interaction) interactions,
       (select count(*) from knowledge_knowledgedocument) labels, (select count(*) from knowledge_chunk) chunks,
       (select count(*) from knowledge_chunk where embedding is null) chunks_without_embedding;"
```

`chunks_without_embedding` should be 0; if not, finish `manage.py index_knowledge` first.

```bash
docker compose exec db pg_dump -U predictrx -d predictrx -Fc --data-only --no-owner \
  -t drugs_drug -t drugs_brandmapping -t drugs_interaction \
  -t knowledge_knowledgedocument -t knowledge_chunk -t knowledge_graphedge \
  -t evaluation_evalcase \
  -f /tmp/predictrx-data.dump
docker compose cp db:/tmp/predictrx-data.dump ./predictrx-data.dump
scp predictrx-data.dump <user>@<label>.<region>.cloudapp.azure.com:~/predictrx/
```

Why only these tables: a full dump would also copy your local user accounts (password hashes), patients, audit logs
and prescription records into the public server. The demo uses fresh, synthetic data on the VM. The dump file contains
DDInter-derived rows (CC BY-NC-SA 4.0): **never commit it or put it on a public link** (`data/SOURCES.md`).
Size is roughly a few hundred MB (about 4 KB of vector per chunk, plus text).

### 7b. On the VM: create the schema, then restore

```bash
cd ~/predictrx/deploy
dc build api
dc up -d db redis ollama
dc run --rm api python manage.py migrate --noinput        # creates the empty tables and the pgvector extension

# The migration created an HNSW vector index. Loading ~60k vectors into an existing HNSW index is slow and
# memory-hungry, so drop it first and rebuild it once after the data is in.
dc exec db psql -U predictrx -d predictrx -c "DROP INDEX IF EXISTS chunk_embedding_hnsw;"

dc cp ../predictrx-data.dump db:/tmp/predictrx-data.dump
dc exec db pg_restore -U predictrx -d predictrx --data-only --disable-triggers --no-owner /tmp/predictrx-data.dump

# Rebuild the index (same definition as apps/knowledge/models.py). Use 512MB instead of 1GB on a 4 GB VM.
dc exec db psql -U predictrx -d predictrx -c "SET maintenance_work_mem='1GB'; CREATE INDEX chunk_embedding_hnsw ON knowledge_chunk USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);"

# reset the id counters so new rows do not collide with the restored ids
dc run --rm -T api python manage.py sqlsequencereset drugs knowledge evaluation | dc exec -T db psql -U predictrx -d predictrx
```

If the restore reports duplicate keys, a migration already inserted rows in that table: empty the affected tables
(`TRUNCATE ... CASCADE` on the knowledge tables only) and run the restore again.

### 7c. Pull the embedding model (once)

```bash
dc exec ollama ollama pull bge-m3
dc exec ollama ollama list
```

It must be **the same model** that produced the stored vectors, with `EMBEDDING_DIM=1024`. A different model gives
vectors that do not match and retrieval quality collapses silently. Only if `SCAN_VISION_LOCAL=true` or the optional
local-LLM features are enabled do you also need `dc exec ollama ollama pull <LOCAL_LLM_MODEL>`.

**Ollama is still needed after the data is embedded.** Embedding the stored chunks is finished, but every analysis
embeds one short query per drug pair (`embed_query` in `ai/rag/retriever.py`) to search those chunks. Without Ollama
the retriever can only follow the graph links (no vector search): analyses still run, label evidence gets thinner.
Prescription scans do not use Ollama when Gemini is configured.

By default Ollama unloads a model after 5 idle minutes, and the next request pays the load time (the label-search
budget per analysis is `AI_RAG_BUDGET_SECONDS`, 20 s by default). The compose file sets `OLLAMA_KEEP_ALIVE=24h` so
`bge-m3` stays in memory; that costs RAM permanently.

---

## 8. Start everything

```bash
cd ~/predictrx/deploy
dc up -d
dc run --rm api python manage.py collectstatic --noinput
dc ps                                   # every service "running"; db "healthy"
```

Open `https://<label>.<region>.cloudapp.azure.com`. The first request may take a moment while Caddy obtains its
certificate. If the certificate fails: DNS name label set? ports 80 and 443 open in the NSG? `dc logs caddy`.

Create accounts:

```bash
dc exec api python manage.py createsuperuser            # admin (email + password prompts)

# Already-verified demo accounts for the judges (one doctor, one family). Use a unique password; rotate it after judging.
dc exec -e DEMO_PW='<unique password>' api python manage.py shell -c "
import os
from apps.accounts.models import User
User.objects.create_user('doctor.demo@example.com', os.environ['DEMO_PW'], role='doctor',
                         display_name='Dr. Demo', email_verified=True)
User.objects.create_user('family.demo@example.com', os.environ['DEMO_PW'], role='family',
                         display_name='Family Demo', email_verified=True)"
```

Then create the synthetic demo patient(s) in the UI, with consent, and link the family account the normal way.
Only synthetic data on this server (`rule.md` section 3). The "DEMO DATA" badge stays visible.

Routine commands:

```bash
dc logs -f --tail=100 api worker       # follow logs
dc restart api worker                  # after editing .env
git pull && dc build api && dc up -d   # deploy new code (rebuild frontend/dist first if the UI changed)
dc down                                # stop (keeps volumes)
```

**Never run `dc down -v`.** It deletes the volumes: the database (all embeddings) and the Ollama models.

---

## 9. Verification checklist (do this before submitting)

Run from a **phone on mobile data**, in a private tab, not from the machine you built on.

- [ ] `https://<host>/api/health/` returns `{"status":"ok", ...}`. (It only proves the API is up, not the database.)
- [ ] Counts match your PC (run on the VM):

```bash
dc exec api python manage.py shell -c "
from apps.drugs.models import Drug, Interaction, BrandMapping
from apps.knowledge.models import KnowledgeDocument, Chunk
print('drugs', Drug.objects.count(), '| interactions', Interaction.objects.count(), '| brands', BrandMapping.objects.count())
print('labels', KnowledgeDocument.objects.count(), '| chunks', Chunk.objects.count(),
      '| without embedding', Chunk.objects.filter(embedding__isnull=True).count())"
```

- [ ] `without embedding` is **0**.
- [ ] `sendtestemail` arrives; a **new registration** gets its OTP and verifies within 60 seconds.
- [ ] Log in as the demo doctor; run an analysis (for example warfarin and aspirin). Check the **agent trace**:
  tool calls should say `mcp_sse`. If they say `direct`, the MCP server was not reached (`dc logs mcp`); the result
  is still correct but the "custom MCP over SSE" claim would not be.
- [ ] The retrieval trace should not say `embeddings not configured`. Evidence chips from labels appear.
- [ ] A **synthetic** prescription scan returns a draft list; the scan record shows the Gemini model name as provider.
- [ ] Family view works for the family demo account; revoked consent hides it.
- [ ] `/admin/` loads with its styling (proves `collectstatic` and the `/static` route).
- [ ] Reboot the VM (`sudo reboot`), wait a few minutes, reload the URL. Everything must come back by itself.
- [ ] `docker stats` shows no container near its memory limit while an analysis and a scan run.
- [ ] Add a free uptime monitor on `/api/health/` and check it on 19 Nov and the morning of 20 Nov.

---

## 10. Security checklist

- [ ] NSG: only 80 and 443 open to everyone; SSH only from your IP.
- [ ] `.env` is `chmod 600`, never committed. `DJANGO_DEBUG=False`. A new `DJANGO_SECRET_KEY` (production refuses the
  dev key).
- [ ] No published ports other than Caddy's (`dc ps` shows only 80 and 443).
- [ ] Demo password is unique and is rotated after judging.
- [ ] Gemini key: new key, restricted if the console allows it. The scan sends the image to Google, so use synthetic
  prescriptions only, and only after the patient's `analysis` consent.
- [ ] The database dump file is not in Git, not on a public link, and is deleted from the VM after the restore.
- [ ] Keep a copy of the dump somewhere private as your backup. Rebuilding embeddings would take hours.

---

## 11. Fallbacks

- **Cloudflare quick tunnel** (`cloudflared tunnel --url http://localhost:5173`) is only a backup. Its
  `trycloudflare.com` address changes on every start and dies when your PC sleeps, so never give it to the judges as
  the main link.
- A **pre-recorded demo video** made from real runs, plus screenshots, stays in the portal submission in case the
  live site is unreachable.

---

## 12. Notes for the portal ("tunnel / hosting documented" field)

Fill from what was actually done, nothing else:

- Hosting: Microsoft Azure VM (size: ____, region: ____), Docker Compose, Caddy for HTTPS.
- Public URL: ____ (DNS name label on the VM's public IP).
- Who keeps it running during judging: ____. VM stays up until: ____.
- Data: restored from a database dump made on the build machine (knowledge tables only); embeddings were not recomputed.
- AI tools: Gemini (prescription scan), Ollama `bge-m3` (embeddings), ____ (other).