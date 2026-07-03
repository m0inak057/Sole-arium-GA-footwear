# Local Setup Guide

Complete guide to clone and run the Sole-Arium Gait Analysis system locally.

## Prerequisites

- **Docker Desktop** ([install here](https://www.docker.com/products/docker-desktop/)) - includes Docker Compose  
- **Node.js 18+** ([install here](https://nodejs.org/)) - for the frontend
- **Git** - for cloning the repository

---

## Quick Start (3 steps, ~10 minutes)

### Step 1: Clone and Prepare

```bash
git clone <repo-url>
cd Orthopedic_Footwear_GA

# Copy environment file (if .env doesn't exist)
cp .env.example .env
```

### Step 2: Start Backend Services

```bash
# Build and start all services (API, Celery, Postgres, Redis, MinIO)
docker compose build
docker compose up -d
```

**Wait ~30 seconds** for services to initialize. Check status:

```bash
docker compose ps
```

All services should show as "healthy" or "running".

**Verify API is working:**
```bash
curl http://localhost:8000/health
```

You should see: `{"status":"ok"}`

### Step 3: Start Frontend

In a **new terminal**:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Success Indicators ✓

- [ ] API responds to http://localhost:8000/health
- [ ] Frontend loads at http://localhost:5173
- [ ] You can see the dashboard in the browser
- [ ] No errors in terminal logs

---

## Service Endpoints

| Service       | URL                              | Credentials |
|---------------|----------------------------------|-------------|
| **Frontend**  | http://localhost:5173            | -           |
| **API**       | http://localhost:8000            | -           |
| **API Docs**  | http://localhost:8000/docs       | -           |
| **MinIO Console** | http://localhost:9001        | minioadmin / minioadmin |
| **Celery Flower** | http://localhost:5555        | -           |
| **PostgreSQL**    | localhost:5444               | gait_user / gait_password |
| **Redis**         | localhost:6380               | redis_password |

---

## Stopping Services

```bash
# Stop all containers (data persists)
docker compose down

# Stop and delete all data (full reset)
docker compose down -v

# View logs
docker compose logs -f
```

---

## Troubleshooting

### "Port already in use" Error

If you get an error about port 8000, 5173, or another port:

```bash
# Check what's using that port (example: port 8000)
# macOS/Linux:
lsof -i :8000
# Windows:
netstat -ano | findstr :8000

# Kill the process or use a different port in docker-compose.yml
```

### Services Won't Start / Health Check Fails

```bash
# Check container logs for errors
docker compose logs api
docker compose logs postgres
docker compose logs redis

# Rebuild and restart
docker compose down
docker compose build --no-cache
docker compose up -d
```

### "Cannot GET /" on http://localhost:5173

This means the frontend dev server isn't running:

```bash
cd frontend
npm install  # ensure dependencies are installed
npm run dev  # start the dev server
```

### API Won't Connect to Database

```bash
# Wait longer - first startup can take 1-2 minutes
sleep 30
docker compose logs postgres

# Or restart just the database
docker compose restart postgres
```

### "npm: command not found"

Node.js is not installed. Download and install from https://nodejs.org/

### "docker: command not found"

Docker is not installed. Download Docker Desktop from https://docker.com/products/docker-desktop

---

## Environment Variables

The `.env` file is already configured for local development:

- **Database**: PostgreSQL at `localhost:5444`
- **Cache**: Redis at `localhost:6380`
- **Storage**: MinIO at `localhost:9000`
- **API**: FastAPI at `localhost:8000`
- **Frontend**: Vite dev server at `localhost:5173`

**Do NOT commit `.env` to git** (it's in `.gitignore`). It contains sensitive keys.

If you need to change something, edit `.env` locally. For team changes, update `.env.example` instead.

---

## File Structure

```
Orthopedic_Footwear_GA/
├── docker-compose.yml      ← Services configuration
├── Dockerfile              ← Backend container
├── .env                    ← Local environment (DO NOT COMMIT)
├── .env.example            ← Template for .env
├── src/                    ← Python backend code
├── frontend/               ← React frontend
│   ├── package.json
│   ├── vite.config.js
│   └── src/
├── configs/                ← Configuration files
├── data/                   ← Local data storage
├── logs/                   ← Application logs
└── README.md               ← Project overview
```

---

## Advanced: Running Backend Without Docker

If you prefer to run the API locally:

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Start services (still need Docker for Postgres, Redis, MinIO)
# Or run with Docker for those services only

# Start API
uvicorn src.gait.api.main:app --reload --port 8000

# In another terminal, start worker
celery -A src.gait.api.tasks worker --loglevel=info
```

---

## First-Time Setup Checklist

- [ ] Docker Desktop is running
- [ ] Cloned the repository
- [ ] Copied `.env.example` to `.env`
- [ ] Ran `docker compose build`
- [ ] Ran `docker compose up -d`
- [ ] All services show as "healthy" in `docker compose ps`
- [ ] `curl http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] Ran `npm install` in frontend directory
- [ ] Ran `npm run dev` in frontend directory
- [ ] Frontend loads at http://localhost:5173

---

## Getting Help

1. Check service logs: `docker compose logs -f <service-name>`
2. View all logs: `docker compose logs -f`
3. Verify services are healthy: `docker compose ps`
4. Check that ports aren't in use: `lsof -i :<port>`
5. Review the main [README.md](./README.md) for architecture details

If you're still stuck:
- Search issues in the repository
- Check Docker Desktop's status
- Ensure internet connection for pulling Docker images
- Try `docker compose down && docker system prune && docker compose up -d` for a fresh start
