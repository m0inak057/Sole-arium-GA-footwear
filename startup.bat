@echo off
REM Sole-Arium Gait Analysis - Startup Script for Windows
REM This script automates the local setup process

setlocal enabledelayedexpansion

echo.
echo ==========================================
echo   Sole-Arium Gait Analysis System
echo   Local Setup ^& Startup (Windows)
echo ==========================================
echo.

REM Check prerequisites
echo [1/6] Checking prerequisites...

where docker >nul 2>nul
if errorlevel 1 (
    echo Error: Docker is not installed. Please install Docker Desktop from https://docker.com
    pause
    exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
    echo Error: Node.js is not installed. Please install from https://nodejs.org/
    pause
    exit /b 1
)

echo OK - Docker and Node.js are installed
echo.

REM Create .env if it doesn't exist
echo [2/6] Checking environment configuration...
if not exist .env (
    echo Creating .env from .env.example...
    copy .env.example .env
    echo OK - .env created
) else (
    echo OK - .env already exists
)
echo.

REM Check if Docker daemon is running
echo [3/6] Checking Docker daemon...
docker ps >nul 2>nul
if errorlevel 1 (
    echo Error: Docker daemon is not running. Please start Docker Desktop.
    pause
    exit /b 1
)
echo OK - Docker daemon is running
echo.

REM Build Docker images
echo [4/6] Building Docker images...
echo (This may take a few minutes on first run...)
call docker compose build
if errorlevel 1 (
    echo Error: Docker build failed
    pause
    exit /b 1
)
echo.

REM Start services
echo [5/6] Starting services...
call docker compose up -d
if errorlevel 1 (
    echo Error: Failed to start services
    pause
    exit /b 1
)
echo.

REM Wait for services
echo Waiting for services to initialize...
timeout /t 10 /nobreak
echo.

REM Check API health
echo [6/6] Checking service health...
set RETRIES=30
:health_check
curl -s http://localhost:8000/health >nul 2>nul
if !errorlevel! equ 0 (
    echo OK - API is healthy
    goto services_ready
)

if !RETRIES! gtr 0 (
    set /a RETRIES=!RETRIES!-1
    echo Waiting for API... (!RETRIES! attempts remaining)
    timeout /t 2 /nobreak
    goto health_check
) else (
    echo Warning: API health check failed. Services may still be starting.
    echo Run: docker compose logs api
)

:services_ready
echo.
echo Setting up frontend...
cd frontend

if not exist node_modules (
    echo Installing npm dependencies...
    call npm install
    if errorlevel 1 (
        echo Error: npm install failed
        pause
        exit /b 1
    )
    echo OK - Dependencies installed
) else (
    echo OK - npm dependencies already installed
)
echo.

echo ==========================================
echo   Setup Complete!
echo ==========================================
echo.
echo Service Endpoints:
echo   Frontend:    http://localhost:5173
echo   API:         http://localhost:8000
echo   API Docs:    http://localhost:8000/docs
echo   MinIO:       http://localhost:9001 (minioadmin/minioadmin)
echo   Flower:      http://localhost:5555
echo.
echo Starting frontend dev server...
echo Press Ctrl+C to stop
echo.

REM Start frontend dev server
call npm run dev

endlocal
