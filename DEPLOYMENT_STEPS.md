# Complete Deployment Guide: Render + Vercel

## Quick Summary

Deploy your Financial Risk Analysis & Hybrid Fraud Detection System with:
- **Backend**: Render (FastAPI + Python)
- **Frontend**: Vercel (React Dashboard)
- **Database**: Render PostgreSQL or Railway MySQL

**Estimated Time**: 30-45 minutes
**Cost**: ~$7-15/month (free tier available)

---

## PART 1: ACCOUNT SETUP (5 minutes)

### 1.1 Create Render Account
```
1. Go to https://render.com
2. Click "Sign up"
3. Connect with GitHub
4. Authorize Render to access your repositories
```

### 1.2 Create Vercel Account
```
1. Go to https://vercel.com
2. Click "Sign up"
3. Connect with GitHub
4. Authorize Vercel to access your repositories
```

### 1.3 Create GitHub Personal Access Token
```
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Name: "Render Deployment"
4. Select scopes: repo, read:repo_hook
5. Copy token (save it securely)
6. Repeat for Vercel if needed
```

---

## PART 2: DATABASE SETUP (10 minutes)

### Option A: Render PostgreSQL (Recommended)

#### Step 1: Create Database in Render
```
1. Log in to Render Dashboard
2. Click "New +" → "PostgreSQL"
3. Configure:
   - Name: fraud-detection-db
   - Database: fraud_detection
   - User: fraud_user
   - Password: (auto-generated)
   - Region: Ohio (or your preferred)
   - Plan: Free (up to $87/month)
4. Click "Create Database"
5. Copy the internal database URL
```

#### Step 2: Get Connection String
```
The URL will be in format:
postgresql://user:password@host:5432/dbname

Copy this for later (DATABASE_URL)
```

---

### Option B: Railway MySQL

#### Step 1: Create MySQL Database
```
1. Go to https://railway.app
2. Login/Sign up with GitHub
3. Click "New Project"
4. Select "Provision MySQL"
5. Configure database
6. Copy connection string
```

#### Step 2: Format Connection String
```
Original: mysql://user:password@host:3306/dbname
Convert to: mysql+pymysql://user:password@host:3306/dbname
Use this as DATABASE_URL
```

---

### Option C: PlanetScale MySQL

#### Step 1: Create Database
```
1. Go to https://planetscale.com
2. Sign up with GitHub
3. Create new database
4. Create a user
5. Copy connection string
```

#### Step 2: Get Credentials
```
Get:
- Host
- Username
- Password
- Database name

Format: mysql+pymysql://user:password@host/dbname
```

---

## PART 3: BACKEND DEPLOYMENT (15 minutes)

### Step 1: Prepare Code

Ensure these files exist in your repository:
```
✓ .render.yaml
✓ Dockerfile.render
✓ requirements-production.txt
✓ app/main.py
✓ app/config.py
```

### Step 2: Deploy on Render

#### 2.1 Create Web Service
```
1. Log in to Render Dashboard
2. Click "New +" → "Web Service"
3. Select "Deploy from GitHub"
4. Select your repository: darshitha760-byte/fraudanalysis
5. Configure:
   - Name: fraud-detection-api
   - Environment: Docker
   - Region: Ohio
   - Plan: Standard ($7/month)
6. Click "Create Web Service"
```

#### 2.2 Add Environment Variables
```
Go to Service Settings → Environment Variables
Add the following:

DATABASE_URL=postgresql://user:password@host:5432/fraud_detection
REDIS_URL=redis://localhost:6379/0 (optional, leave empty if not available)
SECRET_KEY=<generate-with: python -c "import secrets; print(secrets.token_urlsafe(32))">
ENVIRONMENT=production
DEBUG=false
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
```

**Important**: Use different values for each variable, don't copy these literally.

#### 2.3 Monitor Deployment
```
1. Go to "Events" tab
2. Watch deployment progress
3. Look for green checkmark when complete
4. Check logs if there are errors
```

#### 2.4 Test Backend
```
Once deployed, test the API:

1. Get your API URL from the Render dashboard
2. Test health endpoint:
   curl https://your-api.onrender.com/health

3. You should see:
   {"status":"ok"}
```

---

## PART 4: DATABASE INITIALIZATION (5 minutes)

### Step 1: Connect to Render Shell
```
1. In Render Dashboard, select your service
2. Click "Shell" tab
3. You now have shell access to the running container
```

### Step 2: Run Migrations
```
In the Render shell, run:

cd /app
python -m alembic upgrade head
```

This creates all database tables.

### Step 3: Seed Sample Data (Optional)
```
To populate sample fraud detection data:

python seed_database.py

Or for minimal data:

python seed_simple.py
```

---

## PART 5: FRONTEND DEPLOYMENT (10 minutes)

### Step 1: Prepare Frontend

Ensure files exist:
```
✓ frontend/package.json
✓ frontend/vercel.json
✓ frontend/.env.production
✓ frontend/src/App.jsx
✓ frontend/public/index.html
```

### Step 2: Update Environment

Edit `frontend/.env.production`:
```env
REACT_APP_API_URL=https://fraud-detection-api.onrender.com
REACT_APP_API_TIMEOUT=30000
REACT_APP_ENV=production
```

Replace `fraud-detection-api` with your actual Render service name.

### Step 3: Deploy on Vercel

#### 3.1 Create Project
```
1. Log in to Vercel Dashboard
2. Click "Add New..." → "Project"
3. Select your GitHub repository
4. Click "Import"
5. Configure:
   - Framework Preset: React
   - Root Directory: frontend
   - Build Command: npm run build
   - Output Directory: dist
   - Install Command: npm ci
6. Click "Deploy"
```

#### 3.2 Add Environment Variables
```
Before clicking Deploy:
1. Click "Environment Variables"
2. Add:
   - REACT_APP_API_URL=https://your-api.onrender.com
   - REACT_APP_API_TIMEOUT=30000
   - REACT_APP_ENV=production
3. Click "Deploy"
```

#### 3.3 Monitor Deployment
```
1. Watch the deployment progress
2. Wait for "Ready" status
3. Get your Vercel URL: https://your-project.vercel.app
```

---

## PART 6: VERIFICATION (5 minutes)

### Step 1: Test Backend
```bash
# Test API health
curl https://fraud-detection-api.onrender.com/health

# Expected response:
{"status":"ok"}

# Test API endpoint
curl https://fraud-detection-api.onrender.com/api/health

# Should also return OK
```

### Step 2: Test Frontend
```
1. Open https://your-project.vercel.app in browser
2. Dashboard should load
3. Check browser console (F12) for any errors
4. Network tab should show requests to your API
```

### Step 3: Test API Connectivity
```
1. Open browser Developer Tools (F12)
2. Go to Network tab
3. Navigate through dashboard
4. Look for API requests to your Render backend
5. Requests should be successful (200 status)
```

### Step 4: Check Logs
```
Render:
1. Dashboard → Select service
2. Click "Logs" tab
3. Should see successful requests

Vercel:
1. Dashboard → Select project
2. Click "Logs" tab
3. Check for any build or runtime errors
```

---

## PART 7: CUSTOM DOMAIN (Optional, 10 minutes)

### Render Backend

```
1. Go to your Render service
2. Settings → Custom Domains
3. Add your domain (e.g., api.fraud-detection.com)
4. Follow DNS configuration instructions
5. HTTPS enabled automatically
```

### Vercel Frontend

```
1. Go to your Vercel project
2. Settings → Domains
3. Add your domain (e.g., fraud-detection.com)
4. Configure DNS records
5. HTTPS enabled automatically
```

---

## PART 8: PRODUCTION CONFIGURATION

### Update Backend for Production

Edit `app/config.py`:

```python
ALLOWED_ORIGINS: list = [
    "https://fraud-detection.com",        # Your domain
    "https://your-project.vercel.app",    # Vercel domain
    "https://www.fraud-detection.com",    # WWW version
]

# Disable debug logging in production
DEBUG = False
LOG_LEVEL = "info"
```

Then push to GitHub and Render will auto-redeploy.

### Configure Security Headers

Add to `app/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

# Add Trusted Host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "fraud-detection.com",
        "www.fraud-detection.com",
        "your-project.vercel.app",
    ]
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## PART 9: MONITORING & ALERTS

### Render Monitoring

```
1. Dashboard → Service → Metrics
2. Monitor:
   - CPU Usage
   - Memory Usage
   - Network (In/Out)
   - Requests/sec

3. Set up alerts:
   - Restart count > 3
   - High memory usage
   - Service down
```

### Vercel Monitoring

```
1. Dashboard → Project → Analytics
2. Monitor:
   - Build duration
   - Response time
   - Error rate
   - Deployments
```

### Error Tracking (Optional)

Add Sentry for error tracking:

```python
import sentry_sdk

sentry_sdk.init(
    dsn="your-sentry-dsn",
    traces_sample_rate=0.1,
)
```

---

## PART 10: CONTINUOUS DEPLOYMENT

### Auto-Deploy on Push

**Render** and **Vercel** are configured to auto-deploy:

```
1. Push to main branch
2. Services automatically redeploy
3. No manual action needed
4. Monitor via dashboard

To disable:
- Render: Service → Settings → Auto-Deploy
- Vercel: Project → Settings → Git
```

### Deployment Workflow

```
1. Make changes locally
2. Test locally:
   cd frontend && npm run build
   cd app && pytest

3. Commit and push:
   git add .
   git commit -m "Your message"
   git push target main

4. Services auto-deploy
5. Monitor dashboards
6. Test in production
```

---

## TROUBLESHOOTING

### Backend Won't Start

**Symptoms**: Service crashes immediately

**Solutions**:
```bash
1. Check logs in Render dashboard
2. Verify DATABASE_URL format
3. Test database connection:
   psql postgresql://user:password@host:5432/dbname

4. Check for Python errors:
   pip install -r requirements-production.txt
   python app/main.py

5. Rebuild with fresh dependencies:
   - Delete node_modules/.pnpm-store (if using pnpm)
   - Push new commit to trigger rebuild
```

### API Requests Failing from Frontend

**Symptoms**: 
- CORS errors in console
- Network requests timing out
- 401/403 errors

**Solutions**:
```
1. Check frontend .env.production:
   REACT_APP_API_URL must match Render URL

2. Check backend CORS settings:
   ALLOWED_ORIGINS must include Vercel domain

3. Verify API is running:
   curl https://your-api.onrender.com/health

4. Check browser console for exact error

5. Verify no mixed content (HTTP/HTTPS)
```

### Database Connection Issues

**Symptoms**: "Connection refused" errors

**Solutions**:
```
1. Verify DATABASE_URL:
   - Correct host/port
   - Correct username/password
   - Database exists

2. Test connection locally:
   psql "postgresql://user:pass@host:5432/db"

3. Check firewall/IP whitelist

4. Increase connection timeout in backend config

5. Verify database service is running
```

### Build Fails on Vercel

**Symptoms**: Red X on deployment, build errors

**Solutions**:
```
1. Check build logs in Vercel dashboard
2. Verify Node.js version compatibility
3. Ensure package.json in correct directory
4. Check for missing dependencies:
   npm install (locally first)
5. Check for TypeScript errors:
   npm run build (locally)
6. Verify all environment variables set
```

---

## PERFORMANCE TIPS

### Backend Optimization

```python
# Use connection pooling
pool_size=10
max_overflow=20

# Enable response compression
from fastapi.middleware.gzip import GZIPMiddleware
app.add_middleware(GZIPMiddleware, minimum_size=1000)

# Cache frequently accessed data
from functools import lru_cache

@lru_cache(maxsize=128)
def get_fraud_rules():
    return rules_from_db()
```

### Frontend Optimization

```javascript
// Code splitting
const Dashboard = lazy(() => import('./Dashboard'));

// Image optimization
import Image from 'next/image';

// Caching with Service Workers
// Already enabled in Create React App
```

---

## MAINTENANCE

### Weekly Tasks
- [ ] Check error logs
- [ ] Monitor service health
- [ ] Review performance metrics

### Monthly Tasks
- [ ] Update dependencies
- [ ] Review security updates
- [ ] Check disk usage (database)
- [ ] Verify backups

### Quarterly Tasks
- [ ] Security audit
- [ ] Performance review
- [ ] Database optimization
- [ ] Capacity planning

---

## COSTS BREAKDOWN

| Service | Plan | Cost | Notes |
|---------|------|------|-------|
| Render API | Standard | $7/mo | 0.5GB memory, 50GB bandwidth |
| Render Database | Starter | Free-$7 | Up to 256MB free, then paid |
| Vercel Frontend | Pro | $20/mo | Or free for hobby projects |
| Domain | Custom | $10-15/yr | Optional |
| **Total** | **~** | **$27-52/mo** | Can start free with limitations |

---

## NEXT STEPS

1. ✅ Create accounts on Render and Vercel
2. ✅ Set up database
3. ✅ Deploy backend to Render
4. ✅ Initialize database
5. ✅ Deploy frontend to Vercel
6. ✅ Test end-to-end
7. ✅ Set up custom domain (optional)
8. ✅ Configure monitoring
9. ✅ Set up backup strategy
10. ✅ Document in team wiki

---

## SUPPORT RESOURCES

- **Render Documentation**: https://render.com/docs
- **Vercel Documentation**: https://vercel.com/docs
- **FastAPI Guide**: https://fastapi.tiangolo.com
- **React Documentation**: https://react.dev
- **Project Repo**: https://github.com/darshitha760-byte/fraudanalysis

---

## QUICK REFERENCE

### Deploy Backend
```bash
# 1. Make changes
# 2. Commit and push
git push target main
# 3. Render auto-deploys
# 4. Check https://your-api.onrender.com/health
```

### Deploy Frontend
```bash
# 1. Make changes
# 2. Commit and push
git push target main
# 3. Vercel auto-deploys
# 4. Check https://your-project.vercel.app
```

### Check Logs
```bash
# Render: Service → Logs
# Vercel: Project → Logs
```

### Update Environment Variables
```bash
# Render: Service → Settings → Environment Variables
# Vercel: Project → Settings → Environment Variables
```

---

**Version**: 1.0.0  
**Updated**: November 1, 2026  
**Status**: ✅ Production Ready

For questions or issues, refer to the comprehensive guide: `VERCEL_RENDER_DEPLOYMENT.md`
