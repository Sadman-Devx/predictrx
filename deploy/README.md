# Deployment & Cloudflare Tunnel

Goal: a live demo URL reachable from another network (roadmap Day 11, owner: Backend Dev).

## Run the stack
```bash
cd backend && docker compose up -d          # Postgres+pgvector, Redis, Ollama
cp ../.env.example ../.env                   # then edit values
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
celery -A config worker -l info              # separate terminal
python ../mcp-server/server.py               # separate terminal
cd ../frontend && npm install && npm run build && npm run preview   # or serve dist/ behind the API
```

## Cloudflare Tunnel (quick tunnel for demos)
Install `cloudflared`, then expose the web app:
```bash
cloudflared tunnel --url http://localhost:5173
```
It prints a public `https://<random>.trycloudflare.com` URL. Add that host to `DJANGO_ALLOWED_HOSTS`,
`CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` in `.env`, and restart the API.
Quick-tunnel URLs change on every start; a named tunnel with your own domain is stable (see Cloudflare docs).

## Notes to fill in (for the Congress "Tunnel documented" field)
- Which command/tunnel type was used, the final URL, and who keeps it running during judging.
- Fallback: a pre-recorded demo clip (real run) in case the tunnel fails.
