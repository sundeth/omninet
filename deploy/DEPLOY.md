# Omninet Deployment Guide

## Architecture

```
GitHub Actions (on push to develop/main)
  → Lint with ruff
  → Build Docker image
  → Push to ghcr.io/sundeth/omninet:<branch>
  → SSH into Unraid
    → Ensure postgres is up
    → Run Alembic migrations
    → Restart the app container
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
| Staging API     | `omninet-server-dev`  | 8000  | Cloudflare tunnel → `/dev/*`     |
| Production API  | `omninet-server-prd`  | 8001  | Cloudflare tunnel → `/`          |
| SSH             | (host)                | 22    | For GitHub Actions deploys       |

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
mkdir -p /mnt/user/appdata/omninet
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
> docker exec omninet-postgres psql -U postgres -c "CREATE DATABASE omnipet_dev OWNER postgres;"
> ```

### 5. Seed storage data (shop sync)

The app's shop sync service reads JSON files + images from `/app/storage` (which is a Docker volume).
These files are **not** built into the Docker image — you must copy them manually on first deploy.

Find the volume mount point:
```bash
# For staging
docker volume inspect omninet_staging-storage --format '{{ .Mountpoint }}'

# For production
docker volume inspect omninet_production-storage --format '{{ .Mountpoint }}'
```

Copy the seed files from your local `storage/` directory:
```bash
# Replace <VOLUME_MOUNT> with the actual path from above
# Required subdirectories: backgrounds/, items/, gameplay/
scp -r storage/backgrounds/ root@<UNRAID_IP>:<VOLUME_MOUNT>/backgrounds/
scp -r storage/items/       root@<UNRAID_IP>:<VOLUME_MOUNT>/items/
scp -r storage/gameplay/    root@<UNRAID_IP>:<VOLUME_MOUNT>/gameplay/
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

### 6. Generate an SSH key for GitHub Actions

On your local machine:

```bash
ssh-keygen -t ed25519 -f omninet-deploy -C "omninet-deploy-key"
```

Copy the **public** key to Unraid:

```bash
ssh-copy-id -i omninet-deploy.pub root@<UNRAID_IP>
```

### 7. Configure GitHub Secrets

Go to **GitHub → Repository Settings → Secrets and variables → Actions** and add:

| Secret           | Value                                         |
|------------------|-----------------------------------------------|
| `UNRAID_HOST`    | Your Unraid IP or hostname                    |
| `UNRAID_USER`    | `root` (or your SSH user)                     |
| `UNRAID_SSH_KEY` | Contents of `omninet-deploy` private key file |
| `UNRAID_SSH_PORT`| `22` (or your custom SSH port)                |
| `GHCR_PAT`      | GitHub PAT with `read:packages` scope*        |

> *The `GHCR_PAT` is needed for the Unraid server to pull images from ghcr.io.
> Create one at https://github.com/settings/tokens with `read:packages` scope.

### 8. Configure Cloudflare Tunnel

In your Cloudflare Zero Trust dashboard, add two public hostname rules to your existing tunnel:

1. **Production:** `omnipet.app.br` → `http://localhost:8001`
2. **Staging:** `omnipet.app.br` with path `/dev/*` → `http://localhost:8000`

### 9. First deploy

Push to the `develop` branch — GitHub Actions will build, push, and deploy automatically.

To start both environments manually:

```bash
cd /mnt/user/appdata/omninet
docker compose -f docker-compose.deploy.yml --profile staging --profile production up -d
```

---

## Manual Operations

### View logs

```bash
# Staging
docker logs -f omninet-server-dev

# Production
docker logs -f omninet-server-prd
```

### Run migrations manually

```bash
docker run --rm \
  --network omninet_omninet-network \
  --env-file /mnt/user/appdata/omninet/.env.staging \
  ghcr.io/sundeth/omninet:develop \
  python -m alembic upgrade head
```

### Rollback a migration

```bash
docker run --rm \
  --network omninet_omninet-network \
  --env-file /mnt/user/appdata/omninet/.env.production \
  ghcr.io/sundeth/omninet:main \
  python -m alembic downgrade -1
```

### Restart services

```bash
cd /mnt/user/appdata/omninet
docker compose -f docker-compose.deploy.yml --profile staging restart omninet-dev
docker compose -f docker-compose.deploy.yml --profile production restart omninet-prd
```
