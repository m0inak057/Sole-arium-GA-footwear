#!/bin/bash

# Sole-Arium Gait Analysis - Startup Script
# This script automates the local setup process

set -e  # Exit on any error

echo "=========================================="
echo "  Sole-Arium Gait Analysis System"
echo "  Local Setup & Startup"
echo "=========================================="
echo ""

# Check prerequisites
echo "📋 Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker Desktop from https://docker.com"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please update Docker Desktop."
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install from https://nodejs.org/"
    exit 1
fi

echo "✓ Docker, Docker Compose, and Node.js are installed"
echo ""

# Create .env if it doesn't exist
echo "⚙️  Checking environment configuration..."
if [ ! -f .env ]; then
    echo "  Creating .env from .env.example..."
    cp .env.example .env
    echo "  ✓ .env created"
else
    echo "  ✓ .env already exists"
fi
echo ""

# Check if Docker daemon is running
echo "🐳 Checking Docker daemon..."
if ! docker ps > /dev/null 2>&1; then
    echo "❌ Docker daemon is not running. Please start Docker Desktop."
    exit 1
fi
echo "✓ Docker daemon is running"
echo ""

# Build Docker images
echo "🔨 Building Docker images..."
echo "   (This may take a few minutes on first run...)"
docker compose build

echo ""
echo "🚀 Starting services..."
docker compose up -d

echo ""
echo "⏳ Waiting for services to initialize..."
sleep 10

# Check if services are healthy
echo ""
echo "🏥 Checking service health..."
RETRIES=30
while [ $RETRIES -gt 0 ]; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ API is healthy"
        break
    fi
    RETRIES=$((RETRIES-1))
    if [ $RETRIES -gt 0 ]; then
        echo "  Waiting for API... ($RETRIES attempts remaining)"
        sleep 2
    fi
done

if [ $RETRIES -eq 0 ]; then
    echo "⚠️  API health check failed. Services may still be starting."
    echo "   Run: docker compose logs api"
fi

echo ""
echo "📦 Setting up frontend..."
cd frontend

if [ ! -d node_modules ]; then
    echo "  Installing npm dependencies..."
    npm install
    echo "  ✓ Dependencies installed"
else
    echo "  ✓ npm dependencies already installed"
fi

echo ""
echo "=========================================="
echo "  ✅ Setup Complete!"
echo "=========================================="
echo ""
echo "📍 Service Endpoints:"
echo "   Frontend:    http://localhost:5173"
echo "   API:         http://localhost:8000"
echo "   API Docs:    http://localhost:8000/docs"
echo "   MinIO:       http://localhost:9001 (minioadmin/minioadmin)"
echo "   Flower:      http://localhost:5555"
echo ""
echo "🚀 Starting frontend dev server..."
echo "   Press Ctrl+C to stop"
echo ""

# Start frontend dev server
npm run dev
