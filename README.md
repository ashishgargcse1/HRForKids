# Healthy Routine for Kids

Local chores + points + rewards web app for families (self-hosted, Docker, SQLite).

## Stack
- Backend: Python 3.11, FastAPI, Uvicorn
- DB: SQLite at `/data/app.db`
- Auth: session cookie auth (server-side signed session), password hashes with bcrypt via Passlib
- Frontend: server-rendered Jinja2 templates + simple JS/CSS
- Container: Docker + docker-compose

## Run (Docker Compose)
1. Optional: set env vars in shell:
   - `export APP_PORT=8080`
   - `export APP_DB_PATH=/data/app.db`
   - `export APP_SECRET='change-this-secret'`
2. Start:
   - `docker compose up --build`
3. Open from any device on your local network:
   - `http://<HOST_LOCAL_IP>:8080`
4. Default first-run admin login:
   - Username: `admin`
   - Password: `admin123`

The app prints a startup warning when default admin is created. Change the password immediately from the dashboard prompt.

## Data Persistence
- `docker-compose.yml` mounts `./data` to `/data`
- SQLite file persists at `./data/app.db` across container restarts

## Self-Check Script
A minimal API check script is included at `app/tests_or_checks/self_check.sh`.

Run:
```bash
./app/tests_or_checks/self_check.sh http://localhost:8080
```

Checks included:
- `GET /health`
- admin login via `POST /api/login`
- `GET /api/me`
- create parent + child via `POST /api/users`

## Key URLs
- UI login: `/login`
- Dashboard: `/dashboard`
- Chores: `/chores`
- Approvals: `/approvals`
- Rewards: `/rewards`
- Ledger: `/ledger`
- Admin users: `/users`

## Design Notes
- Auth method: session cookie (`SessionMiddleware`). Simpler and lightweight for local-network use.
- RBAC: enforced in service layer and route layer for all API/UI actions.
- Recurrence strategy: when a `DAILY` or `WEEKLY` chore is approved, a new chore instance is auto-created with same metadata/assignees and next due date.
- Points accounting: immutable ledger (`ledger` table). Points are awarded only on chore approval and deducted only on reward redemption approval.
- Reward points reservation: not implemented (simple mode). Points are deducted only when parent/admin approves redemption.

## API Endpoints Implemented
- `POST /api/login`
- `POST /api/logout`
- `GET /api/me`
- `GET/POST /api/users`
- `PATCH /api/users/{id}`
- `POST /api/users/{id}/reset-password`
- `GET/POST /api/chores`
- `GET /api/chores/{id}`
- `POST /api/chores/{id}/done`
- `POST /api/chores/{id}/approve`
- `POST /api/chores/{id}/reject`
- `GET/POST /api/rewards`
- `POST /api/rewards/{id}/redeem`
- `GET /api/redemptions`
- `POST /api/redemptions/{id}/approve`
- `POST /api/redemptions/{id}/deny`
- `GET /api/ledger?user_id=`
- `GET /health`

## Local Dev (without Docker)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt
export APP_DB_PATH=./data/app.db
export APP_SECRET=local-dev-secret
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Raspberry Pi (Standalone Linux Service)
This repository now includes native Raspberry Pi deployment scripts (no Docker required).

### Build Deployable Archive (from this machine)
```bash
bash scripts/package_rpi.sh
```
This creates `dist/hrforkids-rpi-<timestamp>.tar.gz`.

### Install on Raspberry Pi
1. Copy the archive to the Pi:
```bash
scp dist/hrforkids-rpi-<timestamp>.tar.gz pi@<pi-ip>:/tmp/
```
2. SSH into the Pi and install:
```bash
ssh pi@<pi-ip>
sudo mkdir -p /opt/hrforkids-src
sudo tar -xzf /tmp/hrforkids-rpi-<timestamp>.tar.gz -C /opt/hrforkids-src
cd /opt/hrforkids-src/hrforkids-rpi
sudo bash deploy/raspberrypi/install.sh
```

### Service Management on Pi
- Service name: `hrforkids`
- Environment file: `/etc/hrforkids/hrforkids.env`
- Data file: `/var/lib/hrforkids/app.db`

Commands:
```bash
sudo systemctl status hrforkids
sudo systemctl restart hrforkids
sudo journalctl -u hrforkids -f
```

After install, update `/etc/hrforkids/hrforkids.env` with a strong `APP_SECRET` and restart:
```bash
sudo systemctl restart hrforkids
```

### Install Directly From GitHub (recommended once pushed)
On Raspberry Pi:
```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/ashishgargcse1/HRForKids.git
cd HRForKids
sudo bash deploy/raspberrypi/install.sh
```

Default first login after a fresh install:
- Username: `admin`
- Password: `admin123`

Change the admin password immediately after login.

Seeded demo users in the default DB:
- Parent: `parent1` / `parent123`
- Child: `child1` / `child123`
- Child: `child2` / `child234`

These users are included to pre-assign starter chores in a fresh install. Change all default passwords.

### Uninstall From Raspberry Pi
Keep data (`/var/lib/hrforkids/app.db`):
```bash
cd /opt/hrforkids
sudo bash deploy/raspberrypi/uninstall.sh
```

Remove data too:
```bash
cd /opt/hrforkids
sudo bash deploy/raspberrypi/uninstall.sh --delete-data
```

## Seeded Defaults (Research-Based)
The packaged default database includes starter chores and rewards based on common examples in pediatric/family guidance:
- Common chores by age and family routines:
  - https://www.webmd.com/parenting/kids-chores
  - https://www.sharp.com/health-news/age-appropriate-chores-for-kids
- Reward systems and practical rewards:
  - https://www.cdc.gov/parents/essentials/consequences/rewards.html
  - https://www.verywellfamily.com/reward-ideas-for-kids-1094894

Recurring chore visibility rule:
- Recurring chores (`DAILY`, `WEEKLY`) are created immediately after approval, but remain hidden until their `due_date`.
- This prevents the same recurring chore from reappearing multiple times in one day.
