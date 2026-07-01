# Local Setup Guide

## Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- [Node.js 18+](https://nodejs.org/) (for the frontend)

---

## 1. Clone and start the backend

```bash
git clone <repo-url>
cd Orthopedic_Footwear_GA

# Start all backend services (API, Celery worker, Postgres, Redis, MinIO)
docker-compose up --build
```

Wait until you see:
```
gait-api  | INFO:     Application startup complete.
```

The API will be available at http://localhost:8000  
API docs at http://localhost:8000/api/docs

---

## 2. Start the frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

## Service ports

| Service   | URL                        |
|-----------|----------------------------|
| Frontend  | http://localhost:5173       |
| API       | http://localhost:8000       |
| API Docs  | http://localhost:8000/api/docs |
| MinIO UI  | http://localhost:9001       |
| Flower    | http://localhost:5555       |
| Postgres  | localhost:5444              |

MinIO credentials: `minioadmin` / `minioadmin`  
Redis password: `redis_password`

---

## Stopping

```bash
docker-compose down          # stop containers (keeps data volumes)
docker-compose down -v       # stop and delete all data volumes (full reset)
```
