# ✅ Render & Vercel Deployment Checklist

## Pre-Deployment Phase

### Local Development
- [ ] Code committed to Git
- [ ] All tests passing locally
- [ ] Frontend builds successfully (`npm run build`)
- [ ] Backend starts without errors
- [ ] Environment variables configured locally
- [ ] Database migrations tested locally
- [ ] No console errors in browser

### Code Repository
- [ ] Push to GitHub main branch
- [ ] All commits pushed: `git push target main`
- [ ] No uncommitted changes: `git status` shows clean
- [ ] Verify files on GitHub:
  - [ ] `.render.yaml`
  - [ ] `Dockerfile.render`
  - [ ] `requirements-production.txt`
  - [ ] `frontend/vercel.json`
  - [ ] `frontend/.env.production`

---

## Account Setup Phase

### Render Setup
- [ ] Create Render account (https://render.com)
- [ ] Connect GitHub account to Render
- [ ] Authorize Render to access repositories
- [ ] Verify email

### Vercel Setup
- [ ] Create Vercel account (https://vercel.com)
- [ ] Connect GitHub account to Vercel
- [ ] Authorize Vercel to access repositories
- [ ] Verify email

### Database Setup
**Choose ONE option:**

#### Option A: Render PostgreSQL
- [ ] Create PostgreSQL database in Render
- [ ] Name: fraud-detection-db
- [ ] Database name: fraud_detection
- [ ] Region: Ohio (or your preference)
- [ ] Copy connection string
- [ ] Save as DATABASE_URL

#### Option B: Railway MySQL
- [ ] Create MySQL database in Railway
- [ ] Copy connection string
- [ ] Convert to `mysql+pymysql://...` format
- [ ] Save as DATABASE_URL

#### Option C: PlanetScale MySQL
- [ ] Create database in PlanetScale
- [ ] Create user and copy credentials
- [ ] Format connection string
- [ ] Save as DATABASE_URL

---

## Backend Deployment Phase

### Create Web Service on Render
- [ ] Go to Render Dashboard
- [ ] Click "New +" → "Web Service"
- [ ] Select GitHub repository
- [ ] Service name: `fraud-detection-api`
- [ ] Environment: Docker
- [ ] Dockerfile: Dockerfile.render
- [ ] Region: Ohio (or your preference)
- [ ] Plan: Standard ($7/month)

### Configure Environment Variables
- [ ] DATABASE_URL: (Your PostgreSQL/MySQL connection)
- [ ] REDIS_URL: (Optional, leave blank if none)
- [ ] SECRET_KEY: (Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
- [ ] ENVIRONMENT: `production`
- [ ] DEBUG: `false`
- [ ] PYTHONUNBUFFERED: `1`
- [ ] PYTHONDONTWRITEBYTECODE: `1`

### Deploy Backend
- [ ] Click "Create Web Service"
- [ ] Wait for deployment to complete (2-5 minutes)
- [ ] Check "Events" tab for any errors
- [ ] Service should show "Live" status
- [ ] Copy API URL (e.g., https://fraud-detection-api.onrender.com)

### Verify Backend
- [ ] Test health endpoint: `curl https://YOUR_API/health`
- [ ] Response should be: `{"status":"ok"}`
- [ ] Check logs for any errors
- [ ] No 500 errors in logs

---

## Database Initialization Phase

### Access Service Shell
- [ ] Go to Render service dashboard
- [ ] Click "Shell" tab
- [ ] You should see a command prompt

### Run Migrations
- [ ] In shell, run: `python -m alembic upgrade head`
- [ ] Wait for migrations to complete
- [ ] No errors should appear

### Seed Database (Optional)
- [ ] In shell, run: `python seed_database.py`
- [ ] Or for minimal data: `python seed_simple.py`
- [ ] Check for any errors
- [ ] Database should be populated

### Verify Database
- [ ] Connect to database (if you have access)
- [ ] Verify tables exist
- [ ] Verify sample data exists
- [ ] No connection errors in API logs

---

## Frontend Deployment Phase

### Update Frontend Configuration
- [ ] Edit `frontend/.env.production`
- [ ] Set `REACT_APP_API_URL=https://YOUR_API.onrender.com`
- [ ] Verify URL is correct (no trailing slash)
- [ ] Commit changes: `git add . && git commit -m "Update API URL"`
- [ ] Push to GitHub: `git push target main`

### Create Project on Vercel
- [ ] Go to Vercel Dashboard
- [ ] Click "Add New..." → "Project"
- [ ] Select your GitHub repository
- [ ] Click "Import"

### Configure Build Settings
- [ ] Framework: React
- [ ] Root Directory: `frontend`
- [ ] Build Command: `npm run build`
- [ ] Output Directory: `dist` or `build`
- [ ] Install Command: `npm ci`

### Configure Environment Variables
- [ ] REACT_APP_API_URL: Your Render API URL
- [ ] REACT_APP_API_TIMEOUT: `30000`
- [ ] REACT_APP_ENV: `production`

### Deploy Frontend
- [ ] Click "Deploy"
- [ ] Wait for build and deployment (2-5 minutes)
- [ ] Check build logs for any errors
- [ ] Deployment should show "Ready" status
- [ ] Copy Vercel URL (e.g., https://project-xyz.vercel.app)

---

## Post-Deployment Verification

### Test Backend API
- [ ] Open terminal/PowerShell
- [ ] Run: `curl https://YOUR_API.onrender.com/health`
- [ ] Response should be: `{"status":"ok"}`
- [ ] Run: `curl https://YOUR_API.onrender.com/api/health`
- [ ] Both endpoints should return 200 OK

### Test Frontend
- [ ] Open browser
- [ ] Navigate to https://YOUR_PROJECT.vercel.app
- [ ] Page should load without 404 errors
- [ ] Dashboard should be visible
- [ ] Check for console errors (F12 → Console tab)

### Test API Connectivity
- [ ] Open browser DevTools (F12)
- [ ] Go to Network tab
- [ ] Perform an action in dashboard
- [ ] Look for API requests
- [ ] Requests should go to your Render API
- [ ] Status codes should be 200-299 (success)
- [ ] No 4xx or 5xx errors

### Check Service Logs
- [ ] Render Dashboard → Service → Logs
  - [ ] Look for error messages
  - [ ] Should see request logs
  - [ ] No "Connection refused" errors
- [ ] Vercel Dashboard → Project → Logs
  - [ ] Look for build errors
  - [ ] Check runtime errors
  - [ ] No 500 errors

### Test Key Features
- [ ] Dashboard loads
- [ ] Charts/visualizations render
- [ ] Data loads from API
- [ ] Filters/search work
- [ ] No API timeout errors
- [ ] No CORS errors

---

## Update Backend CORS (if needed)

### If Frontend Domain Changes
- [ ] Edit `app/config.py`
- [ ] Update ALLOWED_ORIGINS with Vercel domain
- [ ] Example:
  ```python
  ALLOWED_ORIGINS = [
      "https://your-project.vercel.app",
      "https://fraud-detection.com",  # If custom domain
  ]
  ```
- [ ] Commit and push
- [ ] Render will auto-redeploy
- [ ] Wait for deployment
- [ ] Test API again

---

## Custom Domain Setup (Optional)

### Add Custom Domain to Render Backend
- [ ] Render Dashboard → Service → Settings → Custom Domains
- [ ] Add domain (e.g., api.fraud-detection.com)
- [ ] Follow DNS instructions
- [ ] Verify domain connects
- [ ] Test: `curl https://api.fraud-detection.com/health`

### Add Custom Domain to Vercel Frontend
- [ ] Vercel Dashboard → Project → Settings → Domains
- [ ] Add domain (e.g., fraud-detection.com)
- [ ] Follow DNS instructions
- [ ] Verify domain connects
- [ ] Test: Open https://fraud-detection.com in browser

### Update Frontend/Backend References
- [ ] Backend: Update ALLOWED_ORIGINS with custom domain
- [ ] Frontend: Update REACT_APP_API_URL if using custom domain
- [ ] Re-test everything

---

## Production Hardening

### Security Configuration
- [ ] Enable HTTPS (automatic on Render/Vercel)
- [ ] Set DEBUG=false in backend
- [ ] Update SECRET_KEY to a random value
- [ ] Configure CORS properly
- [ ] Add request validation
- [ ] Rate limiting configured

### Monitoring Setup
- [ ] Set up error tracking (optional: Sentry)
- [ ] Configure alerts on Render
- [ ] Configure alerts on Vercel
- [ ] Monitor database size
- [ ] Set up backup strategy

### Documentation
- [ ] Document API URL
- [ ] Document frontend URL
- [ ] Document database connection
- [ ] Create runbook for common issues
- [ ] Document deployment process

---

## Success Criteria

You're done when:
- ✅ Backend API responds to health check
- ✅ Frontend loads without errors
- ✅ API requests from frontend succeed
- ✅ Dashboard displays data
- ✅ No console errors
- ✅ No API errors in logs
- ✅ Database is populated
- ✅ All features work as expected

---

## Sign-Off

- [ ] Deployment completed successfully
- [ ] All tests passed
- [ ] Performance verified
- [ ] Security verified
- [ ] Team notified
- [ ] Documentation updated

**Deployment Date**: _________________

**Deployed By**: _________________

**Verified By**: _________________

**Notes**: 
```
[Add any additional notes or issues]
```

---

**Version**: 1.0.0  
**Last Updated**: November 1, 2026  
**Status**: ✅ Ready to Use
