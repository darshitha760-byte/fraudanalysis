# Deployment Guide: Vercel & Render

> **Legacy deployment guide — do not execute as written.** Its
> PostgreSQL/MySQL, `DATABASE_URL`, and Alembic instructions are obsolete.
> Active persistence requires an already provisioned MongoDB service configured
> through `MONGODB_URI` and `MONGODB_DATABASE`. No cloud resources or deployment
> were provisioned or verified.

This guide covers deploying the Financial Risk Analysis & Hybrid Fraud Detection System to Vercel (frontend) and Render (backend).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Vercel (Frontend)                        │
│  - React Dashboard (Dockerfile.frontend)                     │
│  - Streamlit Dashboard (Alternative)                         │
└───────────────────┬───────────────────────────────────────┘
                    │ API Calls
                    ▼
┌─────────────────────────────────────────────────────────────┐
│              Render (Backend API)                             │
│  - FastAPI Application (Dockerfile.api)                      │
│  - Python 3.14 Runtime                                       │
└───────────────────┬───────────────────────────────────────┘
                    │ Database Connection
                    ▼
┌─────────────────────────────────────────────────────────────┐
│         External Database (Railway/Render)                   │
│  - MySQL 8.0                                                 │
│  - Redis 7.0 (Optional Cache)                               │
└─────────────────────────────────────────────────────────────┘
```

---

# PART 1: BACKEND DEPLOYMENT ON RENDER

## Step 1: Prepare Backend for Render

### 1.1 Create Render Configuration File

Create `.render.yaml` in the root directory:

```yaml
services:
  - type: web
    name: fraud-detection-api
    env: python
    region: ohio
    plan: standard
    pythonVersion: 3.14.0
    
    # Build command
    buildCommand: pip install -r requirements.txt && python -m alembic upgrade head
    
    # Start command
    startCommand: gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --timeout 60
    
    # Environment variables (configure in dashboard)
    envVars:
      - key: DATABASE_URL
        value: postgresql://user:password@host:5432/dbname
      - key: REDIS_URL
        value: redis://redis-instance:6379/0
      - key: SECRET_KEY
        generateValue: true
      - key: ENVIRONMENT
        value: production
      - key: DEBUG
        value: "false"
      - key: PYTHON_VERSION
        value: "3.14"

databases:
  - name: fraud-db
    databaseName: fraud_detection
    user: fraud_user
    plan: standard
    region: ohio

redis:
  - name: fraud-cache
    plan: standard
    region: ohio
```

### 1.2 Update Requirements

Create `requirements-production.txt`:

```txt
# Backend Framework
fastapi>=0.115.0
uvicorn[standard]>=0.24.0
gunicorn>=21.2.0
pydantic>=2.12.0
pydantic-settings>=2.10.0
email-validator>=2.2.0

# Database
sqlalchemy>=2.1.5
psycopg2-binary>=2.9.9
alembic>=1.20.0
cryptography>=41.0.5

# Authentication & Security
pyjwt==2.15.1
python-multipart==0.0.6
argon2-cffi==25.1.0

# Data Processing & ML
pandas[parquet]>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
imbalanced-learn>=0.11.0
joblib>=1.3.0
filelock>=3.20.0

# Configuration & Logging
python-dotenv==1.0.0
python-json-logger>=2.0.7

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
httpx>=0.25.0
pytest-cov>=4.1.0

# Utilities
python-dateutil>=2.8.2
requests>=2.31.0
redis>=5.0.1
```

### 1.3 Update Dockerfile.api for Render

Create `Dockerfile.render`:

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements-production.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-production.txt

# Copy application
COPY . ./

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Run application
CMD ["gunicorn", "app.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "60"]
```

---

## Step 2: Deploy Backend to Render

### 2.1 Create Render Account & Project

1. Go to https://render.com
2. Sign up/Login with GitHub
3. Click "New +" → "Web Service"
4. Select your GitHub repository
5. Configure deployment settings:
   - **Name**: fraud-detection-api
   - **Environment**: Docker
   - **Region**: Ohio (or your preferred region)
   - **Plan**: Standard or Pro (depending on needs)
   - **Build Command**: (Leave auto)
   - **Start Command**: (Will use Dockerfile)

### 2.2 Set Environment Variables in Render Dashboard

Navigate to your service → Environment → Add environment variables:

```
DATABASE_URL=postgresql://user:password@host:5432/fraud_detection
REDIS_URL=redis://host:6379/0
SECRET_KEY=<generate-strong-key>
ENVIRONMENT=production
DEBUG=false
API_PORT=8000
MYSQL_DATABASE=fraud_detection
```

### 2.3 Connect Database (Render PostgreSQL)

1. In Render Dashboard → Create Database → PostgreSQL
2. Copy connection string to `DATABASE_URL` environment variable
3. Run migrations:
   ```bash
   # Via Render dashboard shell or:
   curl -X POST https://your-api.onrender.com/api/migrate
   ```

### 2.4 Deploy

1. Connect your GitHub repository
2. Render will auto-deploy on every push to main branch
3. Monitor deployment in "Events" tab
4. Verify: `curl https://your-api.onrender.com/health`

---

## Step 3: Update API Configuration for Production

### 3.1 Update `app/config.py`

```python
from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    # API Configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", 8000))
    API_TITLE: str = "Fraud Detection API"
    API_VERSION: str = "1.0.0"
    
    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./fraud.db")
    
    # Redis Configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # CORS Settings
    ALLOWED_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:8501",
        "https://your-vercel-domain.vercel.app",  # Update with your Vercel domain
        "https://your-dashboard-domain.com"
    ]
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
```

### 3.2 Update `app/main.py` CORS Settings

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings

app = FastAPI(title="Fraud Detection API")

settings = get_settings()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rest of your app...
```

---

# PART 2: FRONTEND DEPLOYMENT ON VERCEL

## Step 1: Prepare Frontend for Vercel

### 1.1 Check Frontend Structure

Vercel supports:
- **React** (Recommended for this project)
- **Streamlit** (Alternative - see Section 1.5)

Verify your `frontend/` directory contains:
```
frontend/
├── package.json
├── package-lock.json (or yarn.lock)
├── public/
├── src/
│   ├── App.jsx
│   ├── index.jsx
│   └── ...
├── .env.example
└── vercel.json
```

### 1.2 Create `frontend/vercel.json`

```json
{
  "version": 2,
  "buildCommand": "npm run build",
  "devCommand": "npm run dev",
  "installCommand": "npm ci",
  "env": {
    "REACT_APP_API_URL": "@react_app_api_url",
    "REACT_APP_API_TIMEOUT": "30000"
  },
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "https://fraud-detection-api.onrender.com/$1",
      "headers": {
        "Cache-Control": "no-cache"
      }
    },
    {
      "src": "/static/(.*)",
      "dest": "/public/static/$1",
      "headers": {
        "Cache-Control": "max-age=31536000"
      }
    },
    {
      "src": "/(.*)",
      "dest": "/index.html",
      "status": 200
    }
  ]
}
```

### 1.3 Update `frontend/.env.example`

```env
REACT_APP_API_URL=http://localhost:8000
REACT_APP_API_TIMEOUT=30000
REACT_APP_ENV=development
REACT_APP_VERSION=1.0.0
```

### 1.4 Create `frontend/.env.production`

```env
REACT_APP_API_URL=https://fraud-detection-api.onrender.com
REACT_APP_API_TIMEOUT=30000
REACT_APP_ENV=production
REACT_APP_VERSION=1.0.0
```

### 1.5 Update API Service in Frontend

Create `frontend/src/services/api.js`:

```javascript
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const API_TIMEOUT = parseInt(process.env.REACT_APP_API_TIMEOUT || '30000');

const apiClient = {
  async request(endpoint, options = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);
    
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`);
      }
      
      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  },

  async get(endpoint) {
    return this.request(endpoint, { method: 'GET' });
  },

  async post(endpoint, data) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async put(endpoint, data) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' });
  },
};

export default apiClient;
```

### 1.6 (Alternative) Deploy Streamlit Dashboard to Vercel

Create `streamlit/vercel.json`:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "streamlit_app.py",
      "use": "@vercel/python",
      "config": {
        "maxLambdaSize": "15gb"
      }
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/index.py"
    }
  ]
}
```

Create `api/index.py`:

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import streamlit.web.bootstrap as bootstrap
import streamlit.config as config_module

app = FastAPI()

@app.get("/{path:path}")
async def serve_streamlit(path: str):
    # Configure Streamlit for serverless
    config_module.set_option("server.port", 8000)
    config_module.set_option("server.headless", True)
    
    # Run Streamlit app
    return StreamingResponse(
        bootstrap.run("streamlit_app.py", is_hello=False, args=[]),
        media_type="text/html"
    )
```

---

## Step 2: Deploy Frontend to Vercel

### 2.1 Create Vercel Account & Project

1. Go to https://vercel.com
2. Sign up/Login with GitHub
3. Click "Add New..." → "Project"
4. Select your GitHub repository (or fork it if needed)
5. Configure project:
   - **Framework Preset**: React
   - **Root Directory**: `frontend/` (if using monorepo)
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist` or `build`
   - **Install Command**: `npm ci`

### 2.2 Add Environment Variables in Vercel

1. Go to your project settings → Environment Variables
2. Add production environment variables:

```
REACT_APP_API_URL=https://fraud-detection-api.onrender.com
REACT_APP_API_TIMEOUT=30000
REACT_APP_ENV=production
```

### 2.3 Deploy

1. Click "Deploy"
2. Vercel will auto-build and deploy
3. Monitor deployment progress
4. Get your Vercel domain: `https://your-project.vercel.app`

### 2.4 Custom Domain (Optional)

1. Go to Settings → Domains
2. Add your custom domain (e.g., fraud-detection.com)
3. Configure DNS records as instructed
4. Enable HTTPS (automatic)

---

## Step 3: Update Backend CORS for Vercel Frontend

Update `app/config.py` with your Vercel domain:

```python
ALLOWED_ORIGINS: list = [
    "http://localhost:3000",
    "https://your-project.vercel.app",
    "https://your-custom-domain.com",  # Your custom domain
]
```

Then redeploy the backend on Render.

---

# PART 3: DATABASE SETUP

## Option A: Using Render PostgreSQL (Recommended)

1. In Render Dashboard → New → PostgreSQL
2. Configure:
   - **Name**: fraud-detection-db
   - **Database Name**: fraud_detection
   - **Region**: Ohio (match API region)
   - **PostgreSQL Version**: 15
3. Copy connection string
4. Update `DATABASE_URL` in backend environment variables

## Option B: Using Railway MySQL

1. Go to https://railway.app
2. New Project → Provision MySQL
3. Copy connection string
4. Update `DATABASE_URL` in backend environment variables
5. Format: `mysql+pymysql://user:password@host:port/dbname`

## Option C: Using PlanetScale (MySQL)

1. Go to https://planetscale.com
2. Create new database
3. Generate connection string
4. Add to backend environment variables

---

# PART 4: DATABASE MIGRATIONS & SEEDING

## Step 1: Initialize Database

After database is connected:

```bash
# Option 1: Via API endpoint (if implemented)
curl -X POST https://your-api.onrender.com/api/init

# Option 2: Via Render shell
# Connect to your Render service → Shell
cd /app
python -m alembic upgrade head

# Option 3: Manual SQL execution
# Connect to database and run migration scripts
```

## Step 2: Seed Sample Data

```bash
# Via Render shell
cd /app
python seed_database.py

# Or run specific seed script
python seed_simple.py
```

---

# PART 5: MONITORING & LOGGING

## Render

1. **Dashboard**: Monitor service health
2. **Events**: View deployment history
3. **Logs**: Real-time application logs
4. **Metrics**: CPU, memory, requests/sec

Configure in `app/main.py`:

```python
import logging
import json
from pythonjsonlogger import jsonlogger

# JSON logging for Render
logger = logging.getLogger()
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
```

## Vercel

1. **Dashboard**: Deployment status
2. **Logs**: Build and runtime logs
3. **Analytics**: Performance metrics
4. **Monitoring**: Error tracking

---

# PART 6: TROUBLESHOOTING

## Backend Issues

### Issue: "Service crashed" on Render

**Solution**:
```bash
# Check logs in Render Dashboard
# Verify DATABASE_URL format
# Ensure dependencies are installed

# Test locally:
pip install -r requirements-production.txt
gunicorn app.main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 60
```

### Issue: Database connection timeout

**Solution**:
- Verify `DATABASE_URL` is correct
- Check database service is running
- Add IP whitelisting if applicable
- Increase connection timeout

### Issue: CORS errors

**Solution**:
- Update `ALLOWED_ORIGINS` in backend
- Ensure frontend URL is in the list
- Redeploy backend after changes

## Frontend Issues

### Issue: "API requests failing" on Vercel

**Solution**:
```bash
# Verify REACT_APP_API_URL is set
# Check network tab in browser console
# Ensure backend CORS allows your domain
# Check for mixed content (HTTPS/HTTP)
```

### Issue: Build fails on Vercel

**Solution**:
```bash
# Check build logs in Vercel Dashboard
# Ensure package.json is in correct directory
# Verify NODE_VERSION is compatible
# Check for missing environment variables
```

---

# PART 7: PERFORMANCE OPTIMIZATION

## Backend

1. **Connection Pooling**:
```python
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    echo=False,
)
```

2. **Caching**:
```python
from functools import lru_cache
import redis

cache = redis.from_url(REDIS_URL)
```

3. **Async Operations**:
```python
from fastapi import FastAPI, BackgroundTasks

@app.post("/tasks/")
async def create_task(background_tasks: BackgroundTasks):
    background_tasks.add_task(long_running_function)
    return {"status": "processing"}
```

## Frontend

1. **Code Splitting**:
```javascript
import React, { lazy, Suspense } from 'react';

const Dashboard = lazy(() => import('./Dashboard'));

<Suspense fallback={<div>Loading...</div>}>
  <Dashboard />
</Suspense>
```

2. **Image Optimization**:
```javascript
import Image from 'next/image'; // If using Next.js
// Or use vercel/web-analytics
```

3. **Caching Headers**:
Set in `vercel.json` routes configuration

---

# PART 8: MONITORING & ALERTS

## Recommended Tools

- **Sentry**: Error tracking (frontend & backend)
  ```python
  import sentry_sdk
  sentry_sdk.init("your-sentry-dsn")
  ```

- **LogRocket**: Frontend session replay
- **Datadog**: Performance monitoring
- **PagerDuty**: Incident alerts

---

# PART 9: DEPLOYMENT CHECKLIST

## Pre-Deployment

- [ ] GitHub repository updated with latest code
- [ ] `.env` files configured (not committed)
- [ ] `requirements-production.txt` reviewed
- [ ] Tests passing locally
- [ ] Database migrations tested
- [ ] Frontend build tested (`npm run build`)
- [ ] API endpoints responding to requests

## Render Backend

- [ ] Create PostgreSQL database
- [ ] Create Web Service
- [ ] Connect GitHub repository
- [ ] Set all environment variables
- [ ] Configure custom domain (optional)
- [ ] Enable auto-deploy
- [ ] Test `/health` endpoint

## Vercel Frontend

- [ ] Create project from GitHub
- [ ] Set `REACT_APP_API_URL` environment variable
- [ ] Configure custom domain (optional)
- [ ] Enable analytics (optional)
- [ ] Test all pages in production

## Post-Deployment

- [ ] [ ] Verify API health: `curl https://your-api.onrender.com/health`
- [ ] Test frontend at `https://your-project.vercel.app`
- [ ] Check CORS requests in browser console
- [ ] Monitor Render/Vercel dashboards
- [ ] Set up error tracking (Sentry)
- [ ] Document URLs in team wiki

---

# PART 10: COST ESTIMATION

## Render

- **Web Service**: $7/month (starter) to $25/month (standard)
- **PostgreSQL Database**: $7-30/month depending on storage
- **Redis Cache**: $5-15/month (optional)
- **Total**: ~$20-70/month

## Vercel

- **Free tier**: Includes hobby projects
- **Pro**: $20/month for faster builds, advanced features
- **Enterprise**: Custom pricing

## Alternative: Railway

- Pay-as-you-go starting at $5/month
- Includes database + backend in one place

---

# QUICK START COMMANDS

```bash
# 1. Deploy Backend to Render
# - Push to GitHub
# - Connect in Render Dashboard
# - Set environment variables
# - Deploy automatically

# 2. Deploy Frontend to Vercel
# - Push to GitHub
# - Connect in Vercel Dashboard
# - Set REACT_APP_API_URL
# - Deploy automatically

# 3. Local testing before deployment
cd frontend && npm run build
cd app && python -m pytest
gunicorn app.main:app --bind 0.0.0.0:8000

# 4. Monitor deployments
# Render: https://dashboard.render.com
# Vercel: https://vercel.com/dashboard
```

---

## Support & Resources

- **Render Docs**: https://render.com/docs
- **Vercel Docs**: https://vercel.com/docs
- **FastAPI**: https://fastapi.tiangolo.com
- **React**: https://react.dev

---

## Next Steps

1. Update GitHub repository with deployment configs
2. Create Render account and deploy backend
3. Create Vercel account and deploy frontend
4. Test end-to-end connectivity
5. Set up monitoring and alerts
6. Document deployment URLs
7. Plan CI/CD pipeline improvements

---

**Last Updated**: November 1, 2026
**Project**: Financial Risk Analysis & Hybrid Fraud Detection System
**Version**: 1.0.0
