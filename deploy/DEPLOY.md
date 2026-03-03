# Omninet Deployment Guide

## Architecture

```
GitHub Actions (on push to develop/main)
  → Lint with ruff
  → Build Docker image
  → Push to ghcr.io/sundeth/omninet:<branch>

Watchtower (on Unraid, polls every 60s)
  → Detects new image tag
  → Pulls new image
  → Recreates container (rolling restart)
  → entrypoint.sh runs Alembic migrations
  → uvicorn starts
```

**Branch → Environment mapping:**

| Branch    | Environment | Internal Port | Public URL                     | Database      |
|-----------|-------------|---------------|--------------------------------|---------------|
| `develop` | Staging     | 8000          | `https://omnipet.app.br/dev`   | `omnipet_dev` |
| `main`    | Production  | 8001          | `https://omnipet.app.br`       | `omnipet_prd` |

**Infrastructure on Unraid:**

| Service         | Container             | Port  | Notes                            |
|-----------------|-----------------------|-------|----------------------------------|
| PostgreSQL      | `omninet-postgres`    | 5433  | Dedicated instance (not shared)  |
| Watchtower      | `omninet-watchtower`  | —     | Auto-pulls & restarts on update  |
| Staging API     | `omninet-server-dev`  | 8000  | Cloudflare tunnel → `/dev/*`     |
| Production API  | `omninet-server-prd`  | 8001  | Cloudflare tunnel → `/`          |

**Cloudflare Tunnel configuration:**

| Public hostname         | Service                      |
|-------------------------|------------------------------|
| `omnipet.app.br`       | `http://localhost:8001`      |
| `omnipet.app.br/dev/*` | `http://localhost:8000`      |

> The staging app has `ROOT_PATH=/dev` set so FastAPI correctly handles the subpath.

---

## Initial Unraid Setup (one-time)

### 1. Create the deployment directory

```bash
mkdir -p /mnt/user/appdata/omninet/{dev,prd}
```

### 2. Copy deployment files

Copy these files from the `deploy/` folder to your Unraid server:

```bash
scp deploy/docker-compose.deploy.yml  root@<UNRAID_IP>:/mnt/user/appdata/omninet/
scp deploy/init-multi-db.sh           root@<UNRAID_IP>:/mnt/user/appdata/omninet/
scp deploy/.env.example               root@<UNRAID_IP>:/mnt/user/appdata/omninet/.env
scp deploy/.env.staging.example       root@<UNRAID_IP>:/mnt/user/appdata/omninet/.env.staging
scp deploy/.env.production.example    root@<UNRAID_IP>:/mnt/user/appdata/omninet/.env.production
```

> **Two separate env files:**
> - `.env` — read by `docker compose` itself for infrastructure variables (`DB_PASSWORD`)
> - `.env.staging` / `.env.production` — read by the app containers at runtime

### 3. Configure environment files on Unraid

```bash
ssh root@<UNRAID_IP>
cd /mnt/user/appdata/omninet

# Set the postgres container password (used by docker compose for the postgres container)
nano .env

# Set app-level secrets
nano .env.staging
nano .env.production
```

**Critical: Change these values:**
- `.env` → `DB_PASSWORD` — the postgres container password. Must match the password in `DATABASE_URL` in both app env files.
- `.env.staging` / `.env.production` → `SECRET_KEY` — generate with `openssl rand -hex 32`
- `.env.production` → SMTP credentials

### 4. Start PostgreSQL

```bash
cd /mnt/user/appdata/omninet
docker compose -f docker-compose.deploy.yml up -d postgres
```

This creates both `omnipet_prd` (default) and `omnipet_dev` (via init script) databases.

> **If the init script didn't run** (volume already existed), create `omnipet_dev` manually:
> ```bash
> docker exec omninet-postgres psql -U omnipet -d omnipet_prd -c "CREATE DATABASE omnipet_dev OWNER omnipet;"
> ```

### 5. Seed storage data (shop sync)

The app's shop sync service reads JSON files + images from `/app/storage` (bind-mounted from `./dev` or `./prd`).
These files are **not** built into the Docker image — place them manually on first deploy.

```bash
# Copy seed files to staging
cp -r storage/backgrounds/ /mnt/user/appdata/omninet/dev/backgrounds/
cp -r storage/items/       /mnt/user/appdata/omninet/dev/items/
cp -r storage/gameplay/    /mnt/user/appdata/omninet/dev/gameplay/

# Copy seed files to production
cp -r storage/backgrounds/ /mnt/user/appdata/omninet/prd/backgrounds/
cp -r storage/items/       /mnt/user/appdata/omninet/prd/items/
cp -r storage/gameplay/    /mnt/user/appdata/omninet/prd/gameplay/
```

**What each directory contains:**
| Directory      | Contents                                         |
|----------------|--------------------------------------------------|
| `backgrounds/` | Background PNGs + `backgrounds.json` (shop data) |
| `items/`       | Item icon PNGs + `items.json` (shop data)         |
| `gameplay/`    | `gameplay.json` (shop data)                       |
| `modules/`     | Created automatically (user-uploaded modules)     |
| `logs/`        | Created automatically (app logs)                  |

> If the JSON files are missing, the shop sync service will skip seeding (no error) and the shop will be empty until the files are placed.

### 6. Configure Cloudflare Tunnel

In your Cloudflare Zero Trust dashboard, add two public hostname rules to your existing tunnel:

1. **Production:** `omnipet.app.br` → `http://localhost:8001`
2. **Staging:** `omnipet.app.br` with path `/dev/*` → `http://localhost:8000`

### 7. Start all services

```bash
cd /mnt/user/appdata/omninet
docker compose -f docker-compose.deploy.yml --profile staging --profile production up -d
```

This starts postgres, watchtower, and both app containers.

### 8. First deploy

Push to the `develop` branch — GitHub Actions will lint, build, and push the image to GHCR.
Watchtower will detect the new image within 60 seconds and automatically restart the container.

---

## How deploys work

1. You push code to `develop` or `main`
2. GitHub Actions builds the Docker image and pushes it to `ghcr.io/sundeth/omninet:<branch>`
3. Watchtower (running on Unraid) polls GHCR every 60 seconds
4. When it detects a new image, it pulls it and recreates the container
5. The container's `entrypoint.sh` runs `alembic upgrade head` (migrations) then starts uvicorn

No SSH, no webhooks — fully automatic.

---

## Manual Operations

### View logs

```bash
# Staging
docker logs -f omninet-server-dev

# Production
docker logs -f omninet-server-prd

# Watchtower (to see update activity)
docker logs -f omninet-watchtower
```

### Run migrations manually

Migrations run automatically on every container start via `entrypoint.sh`.
To run them manually:

```bash
docker exec omninet-server-dev python -m alembic upgrade head
```

### Rollback a migration

```bash
docker exec omninet-server-prd python -m alembic downgrade -1
# Then restart to pick up the code changes
docker compose -f docker-compose.deploy.yml --profile production restart omninet-prd
```

### Restart services

```bash
cd /mnt/user/appdata/omninet
docker compose -f docker-compose.deploy.yml --profile staging restart omninet-dev
docker compose -f docker-compose.deploy.yml --profile production restart omninet-prd
```

