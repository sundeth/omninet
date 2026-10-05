# Omninet

Backend API for the Omnipet virtual pet game.

## Overview

Omninet is a FastAPI-based backend server that handles:

- **User Authentication**: Account creation, login, email verification, device linking
- **Module Management**: Publishing, updating, downloading game modules
- **Arena**: Team creation, matchmaking and battles fought by Omnipet's own engine on a server-held copy of Omnipet and its modules
- **Seasons**: Timed seasons with restrictions on pets (stage, attribute, module) and per-season battle settings
- **Activity Logging**: Full history tracking for auditing

## License

Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0)

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis (optional, for production caching)
- Docker & Docker Compose (recommended)

### Development Setup

1. **Clone the repository**:
   ```bash
   cd Omninet
   ```

2. **Create environment file**:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Start with Docker Compose**:
   ```bash
   docker-compose up -d
   ```

4. **Access the API**:
   - API: http://localhost:8000
   - Docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

### Local Development (without Docker)

1. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   .\venv\Scripts\activate  # Windows
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up database**:
   - Ensure PostgreSQL is running
   - Create database: `omnipet_dev`

4. **Run the server**:
   ```bash
   python -m omninet.main
   ```

## API Endpoints

### Authentication (`/api/v1/auth`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/register` | Register new user |
| POST | `/verify-registration` | Verify email with code |
| POST | `/login` | Login with email/password |
| POST | `/verify-login` | Verify login with code |
| POST | `/validate-device` | Validate device key (auto-login) |
| POST | `/generate-pairing-code` | Generate game device pairing code |
| POST | `/validate-pairing-code` | Validate pairing code from game |
| GET | `/coins` | Get user's coin balance |

### Users (`/api/v1/users`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/me` | Get current user profile |
| PATCH | `/me` | Update user profile |
| GET | `/me/devices` | List user's devices |
| DELETE | `/me/devices/{id}` | Delete a device |
| GET | `/{nickname}` | Get public user profile |

### Modules (`/api/v1/modules`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/categories` | List module categories |
| GET | `` | List published modules |
| GET | `/mine` | List user's modules |
| GET | `/{id}` | Get module details |
| POST | `/check-publish` | Check publish permission |
| POST | `/publish` | Publish/update module (upload zip) |
| POST | `/{id}/unpublish` | Unpublish a module |
| GET | `/{id}/download` | Download module zip |
| GET | `/{id}/contributors` | List contributors |
| POST | `/{id}/contributors` | Add contributor |
| DELETE | `/{id}/contributors/{nickname}` | Remove contributor |

### Teams (`/api/v1/teams`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `` | List user's teams |
| GET | `/current` | Get current season team |
| GET | `/{id}` | Get team details |
| POST | `` | Create new team (3 Digimon: identity + care status) |
| DELETE | `/{id}` | Deactivate team |
| POST | `/claim-rewards` | Claim the results of finished seasons |

### Battles (`/api/v1/battles`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/{id}` | Get battle details with replay log |
| GET | `/team/{id}/history` | Get team's attacks and defences |
| POST | `/find/{team_id}` | Find and execute a battle |

### Seasons (`/api/v1/seasons`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `` | List seasons |
| GET | `/current` | Get the running season (404 between seasons) |
| GET | `/{id}` | Get season details |
| POST | `` | Schedule a season (admin only) |

### Arena (`/api/v1`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/arena/modules` | Modules the arena can field this season |
| GET | `/admin/arena/status` | Season, runtime and queued updates (admin) |
| POST | `/admin/arena/updates/omnipet` | Queue an Omnipet build zip (admin) |
| POST | `/admin/arena/updates/sync-published` | Queue every published module (admin) |
| POST | `/admin/arena/season/end` | End the running season now (admin) |
| POST | `/admin/arena/tick` | Run the season clock once (admin) |
| GET/POST | `/dev/arena/...` | Development tools: status, season start/end, runtime apply, dummy teams, bot battles (ENVIRONMENT=dev only; admin `X-Device-Key` or `X-Dev-Token`) |

### Admin (`/api/v1/admin`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/users/{id}/ban` | Ban user |
| POST | `/users/{id}/unban` | Unban user |
| POST | `/users/{id}/coins` | Adjust user coins |
| POST | `/modules/{id}/ban` | Ban module |
| POST | `/modules/{id}/unban` | Unban module |
| POST | `/seasons/update-statuses` | Run the arena season clock once |
| GET | `/logs` | Get activity logs |

## Arena

Battles are fought by Omnipet's arena engine (`python -m battle.arena`, OMNIPET rules with the DMX default patterns), run from a copy of Omnipet's source and module JSON that the server keeps under `ARENA_STORAGE_PATH` (default `storage/arena`).  A copy never changes during a season: Omnipet builds dropped into `updates/` and module updates (queued automatically when a module is published) are installed only when a season ends.  Build a runtime zip from an Omnipet checkout with `python utilities/claude/build_arena_runtime.py`; the details are in Omnipet's `utilities/claude/docs/arena.md` and `omninet/arena/runtime.py`.

A team upload names each Digimon (module, name, version) and carries its care status.  Stage, attribute, power, HP and attacks come from the server's module data; a module the server does not have is refused.

### Season Restrictions

Seasons can restrict which pets are allowed to participate based on:

- **Stage**: Only pets of certain evolution stages (0-7)
- **Attribute**: Only pets with specific attributes (Vaccine, Data, Virus, Free; or Va/Da/Vi)
- **Module**: Only pets from specific game modules

A season's `config` overrides the battle settings: `attacks_per_day`, `charge` (0-3 or `"random"`), `win_score`, `loss_score`, `draw_score`, `participation_coins`.

Example season:
```json
{
  "restrictions": {"allowed_stages": [4, 5, 6], "allowed_attributes": ["Vaccine", "Data"]},
  "config": {"attacks_per_day": 20, "charge": "random"}
}
```

## Authentication Flow

### Application Login

1. User enters email/password
2. Server validates and sends 6-digit code to email
3. User enters code
4. Server returns device secret key
5. Application stores key for auto-login

### Game Device Linking

1. User generates 4-character pairing code in application
2. Code appears on screen (valid 5 minutes)
3. User enters code in game
4. Server validates and creates device
5. Game receives secret key for auto-login

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | dev or prd | dev |
| `DATABASE_URL` | PostgreSQL connection string | - |
| `SECRET_KEY` | JWT secret key | - |
| `REDIS_URL` | Redis connection string | redis://localhost:6379/0 |
| `SMTP_HOST` | SMTP server host | smtp.gmail.com |
| `SMTP_PORT` | SMTP server port | 587 |
| `ARENA_STORAGE_PATH` | Arena runtime store (Omnipet copies, update drop folder) | ./storage/arena |
| `ARENA_SEASON_LENGTH_HOURS` | Length of automatic seasons | 168 |
| `ARENA_SEASON_ANCHOR` | Start of the automatic season schedule | 2026-01-04T00:00:00+00:00 |
| `ARENA_SEASON_RESTRICTIONS` / `ARENA_SEASON_CONFIG` | JSON forced onto automatic seasons | (empty) |
| `ARENA_TICK_SECONDS` | Season clock interval | 60 |
| `ARENA_DEV_BOTS` | Dev only: dummy players attack on a timer | false |
| `SMTP_USER` | SMTP username | - |
| `SMTP_PASSWORD` | SMTP password | - |
| `MAX_DAILY_BATTLES` | Max battles per team per day | 10 |
| `MAX_TEAMS_PER_USER` | Max teams per user per season | 1 |

## Project Structure

```
omninet/
├── __init__.py
├── config.py           # Settings management
├── database.py         # Database connection
├── main.py             # FastAPI application
├── models/             # SQLAlchemy models
│   ├── user.py
│   ├── module.py
│   ├── battle.py
│   └── logs.py
├── schemas/            # Pydantic schemas
│   ├── user.py
│   ├── module.py
│   ├── battle.py
│   └── common.py
├── services/           # Business logic
│   ├── auth.py
│   ├── user.py
│   ├── device.py
│   ├── module.py
│   ├── team.py
│   ├── battle.py
│   ├── season.py
│   ├── logging.py
│   └── email.py
└── routes/             # API endpoints
    ├── auth.py
    ├── users.py
    ├── modules.py
    ├── teams.py
    ├── battles.py
    ├── seasons.py
    └── admin.py
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues and feature requests, please use the GitHub issue tracker.
