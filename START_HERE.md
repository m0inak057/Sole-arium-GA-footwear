# 🚀 START HERE

You just cloned the Sole-Arium Gait Analysis system. Here's how to get it running in **5 minutes**.

## Prerequisites Check

Before starting, make sure you have:

- ✓ **Docker Desktop** installed ([get it here](https://www.docker.com/products/docker-desktop/))
- ✓ **Node.js 18+** installed ([get it here](https://nodejs.org/))
- ✓ **Git** for cloning (you already have this!)

**Don't have them?** Install them first, then come back.

## Option 1: Automatic Setup (Easiest) ⭐

### macOS / Linux

```bash
./startup.sh
```

### Windows

```cmd
startup.bat
```

Done! The script will:
1. Check you have everything needed
2. Set up the environment
3. Start all services
4. Launch the frontend

Open **http://localhost:5173** in your browser.

---

## Option 2: Manual Setup (If You Prefer)

```bash
# Step 1: Copy environment file
cp .env.example .env

# Step 2: Build and start services
docker compose build
docker compose up -d

# Wait 30 seconds for services to start...

# Step 3: In a new terminal, start frontend
cd frontend
npm install
npm run dev
```

Then open **http://localhost:5173**

---

## ✅ Success Checklist

- [ ] API responds: http://localhost:8000/health
- [ ] Frontend loads: http://localhost:5173
- [ ] No errors in terminal
- [ ] You can see the dashboard

---

## 🔗 Service Endpoints

| What | Where |
|------|-------|
| **Dashboard** | http://localhost:5173 |
| **API** | http://localhost:8000 |
| **File Storage (MinIO)** | http://localhost:9001 |
| **Task Monitor (Flower)** | http://localhost:5555 |

**MinIO Login:** `minioadmin` / `minioadmin`

---

## ⚠️ If Something Goes Wrong

### "Port already in use"

Another application is using the port. Either:
- Close the other application, or
- Change the port in `docker-compose.yml`

### "Docker not running"

Open Docker Desktop and wait for it to start.

### "npm: command not found"

Node.js isn't installed. Install it from https://nodejs.org/

### "docker: command not found"

Docker isn't installed. Install Docker Desktop from https://docker.com

### Services won't start

```bash
# Check what's wrong
docker compose logs api

# Restart everything
docker compose down
docker compose up -d
```

---

## 📚 Next Steps

- Read [SETUP.md](./SETUP.md) for detailed instructions
- Read [README.md](./README.md) for the full project overview
- Check [API docs](http://localhost:8000/docs) when API is running

---

## 🆘 Still Stuck?

1. Check `docker compose logs -f` to see what's happening
2. Make sure Docker Desktop is actually running
3. Make sure you have internet (Docker needs to download images)
4. Try: `docker compose down && docker system prune && docker compose up -d`

---

**Good luck! 🎉**
