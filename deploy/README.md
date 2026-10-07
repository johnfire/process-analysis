# Deployment

Push to `main` → CI (lint, types, tests, integration on Postgres, score ratchet, dependency audit,
secret scan) → image `ghcr.io/johnfire/process-analysis:<sha>` → SSH to the VPS → migrate → `up -d`
→ `/health` on the VPS → `/health` and the landing page over HTTPS. The VPS never builds; it pulls.

Live at `https://process-analysis.christopherrehm.de`. Container port 8000, published only on
`127.0.0.1:8110`; Apache on the host terminates TLS.

## One-time setup

Done once, by hand. After it, every push to `main` deploys.

1. **DNS:** `process-analysis  A  82.165.32.162` on christopherrehm.de.
2. **GitHub secrets** on `johnfire/process-analysis`: `VPS_HOST`, `VPS_USER`, `VPS_PORT`,
   `VPS_SSH_KEY` (same values as flashkarte's).
3. **VPS checkout and secrets:**
   ```bash
   ssh claude@82.165.32.162
   sudo git clone https://github.com/johnfire/process-analysis.git /opt/process-analysis
   sudo chown -R claude:claude /opt/process-analysis
   cd /opt/process-analysis
   cp .env.example .env
   sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
   chmod 600 .env
   ```
4. **Apache and certificate** (after DNS resolves):
   ```bash
   sudo cp deploy/apache/process-analysis.conf /etc/apache2/sites-available/
   sudo a2ensite process-analysis
   sudo apache2ctl configtest && sudo systemctl reload apache2
   sudo certbot --apache -d process-analysis.christopherrehm.de
   ```
5. Push to `main` (or re-run the workflow) and watch the `verify-live` job go green.

## Operating

- Health: `curl -s http://127.0.0.1:8110/health` on the VPS; reports database, migrations, worker.
- Logs: `docker compose -f docker-compose.prod.yml logs -f web worker` (JSON lines with
  `correlation_id`).
- Roll back: `IMAGE_TAG=<older sha> docker compose -f docker-compose.prod.yml up -d web worker`.
  Migrations are forward-only in production; a rollback across a migration needs its own plan.
- Backups: daily dumps in `/opt/process-analysis/backups` (7 daily, 4 weekly, 3 monthly).
