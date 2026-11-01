# Quick Deployment Guide for Render and Vercel (PowerShell)
# Run this script to get started with cloud deployment

$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Green
Write-Host "Financial Risk Analysis & Fraud Detection System" -ForegroundColor Green
Write-Host "Render & Vercel Deployment Quick Start" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host ""

# Helper functions
function Write-Step {
    param([string]$Message)
    Write-Host "▶ $Message" -ForegroundColor Green
}

function Write-Warning-Custom {
    param([string]$Message)
    Write-Host "⚠ $Message" -ForegroundColor Yellow
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "✗ $Message" -ForegroundColor Red
}

# Step 1: Check prerequisites
Write-Step "Step 1: Checking Prerequisites"
Write-Host ""

if (Get-Command git -ErrorAction SilentlyContinue) {
    Write-Step "✓ Git is installed"
} else {
    Write-Error-Custom "Git is not installed. Please install Git first."
    exit 1
}

if (Get-Command npm -ErrorAction SilentlyContinue) {
    Write-Step "✓ npm is installed"
} else {
    Write-Warning-Custom "npm is not installed. You'll need it for frontend deployment."
}

Write-Host ""

# Step 2: Prepare files
Write-Step "Step 2: Verifying Deployment Configuration Files"
Write-Host ""

$files_to_check = @(
    ".render.yaml",
    "Dockerfile.render",
    "requirements-production.txt",
    "frontend/vercel.json",
    "frontend/.env.example",
    "frontend/.env.production",
    "VERCEL_RENDER_DEPLOYMENT.md"
)

$missing_files = @()
foreach ($file in $files_to_check) {
    if (Test-Path $file) {
        Write-Step "✓ Found: $file"
    } else {
        Write-Error-Custom "Missing: $file"
        $missing_files += $file
    }
}

if ($missing_files.Count -gt 0) {
    Write-Host ""
    Write-Error-Custom "Some configuration files are missing."
    exit 1
}

Write-Host ""

# Step 3: Git setup
Write-Step "Step 3: Setting up Git"
Write-Host ""

$git_dir = git rev-parse --git-dir 2>$null
if ($null -eq $git_dir) {
    Write-Error-Custom "Not a git repository. Please run: git init"
    exit 1
}

Write-Step "✓ Git repository found"

Write-Host ""

# Step 4: Environment setup
Write-Step "Step 4: Environment Variables Setup"
Write-Host ""

if (-not (Test-Path ".env")) {
    Write-Warning-Custom "No .env file found. Creating from template..."
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Step "✓ Created .env from .env.example"
        Write-Warning-Custom "Please update .env with your configuration"
    }
}

if (-not (Test-Path "frontend/.env")) {
    Write-Warning-Custom "No frontend/.env file found. Creating from template..."
    if (Test-Path "frontend/.env.example") {
        Copy-Item "frontend/.env.example" "frontend/.env"
        Write-Step "✓ Created frontend/.env from frontend/.env.example"
    }
}

Write-Host ""

# Step 5: Backend deployment info
Write-Step "Step 5: Render Backend Deployment Instructions"
Write-Host ""

$backend_info = @"
┌─────────────────────────────────────────────────────────────┐
│ BACKEND DEPLOYMENT ON RENDER                                │
└─────────────────────────────────────────────────────────────┘

1. Go to https://render.com
2. Sign in with GitHub
3. Click "New +" → "Web Service"
4. Connect your GitHub repository
5. Configure:
   - Name: fraud-detection-api
   - Environment: Docker
   - Dockerfile: Dockerfile.render
   - Region: Ohio (or your preferred region)
   - Plan: Standard (\$7/month)

6. Add Environment Variables:
   - DATABASE_URL: (Get from PostgreSQL database service)
   - REDIS_URL: (Get from Redis cache service or leave empty)
   - SECRET_KEY: (Generate a secure key)
   - ENVIRONMENT: production
   - DEBUG: false

7. Click "Deploy"
8. Monitor deployment in the Events tab
9. Once deployed, test: curl https://your-api.onrender.com/health

"@

Write-Host $backend_info

Write-Host ""

# Step 6: Frontend deployment info
Write-Step "Step 6: Vercel Frontend Deployment Instructions"
Write-Host ""

$frontend_info = @"
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND DEPLOYMENT ON VERCEL                               │
└─────────────────────────────────────────────────────────────┘

1. Go to https://vercel.com
2. Sign in with GitHub
3. Click "Add New..." → "Project"
4. Select your GitHub repository
5. Configure:
   - Framework: React
   - Root Directory: frontend/ (if using monorepo)
   - Build Command: npm run build
   - Output Directory: dist or build

6. Add Environment Variables:
   - REACT_APP_API_URL: https://fraud-detection-api.onrender.com
   - REACT_APP_API_TIMEOUT: 30000
   - REACT_APP_ENV: production

7. Click "Deploy"
8. Visit your site at: https://your-project.vercel.app

"@

Write-Host $frontend_info

Write-Host ""

# Step 7: Database setup
Write-Step "Step 7: Database Setup Options"
Write-Host ""

$db_info = @"
Choose one option for your database:

┌─ Option A: Render PostgreSQL (Recommended) ──────────────┐
│ 1. In Render Dashboard → New → PostgreSQL                │
│ 2. Name: fraud-detection-db                              │
│ 3. Database: fraud_detection                             │
│ 4. Copy connection string → DATABASE_URL                 │
└──────────────────────────────────────────────────────────┘

┌─ Option B: Railway MySQL ────────────────────────────────┐
│ 1. Go to https://railway.app                             │
│ 2. New Project → Provision MySQL                         │
│ 3. Copy connection string                                │
│ 4. Format: mysql+pymysql://user:pwd@host/db              │
└──────────────────────────────────────────────────────────┘

┌─ Option C: PlanetScale MySQL ────────────────────────────┐
│ 1. Go to https://planetscale.com                         │
│ 2. Create new database                                    │
│ 3. Get connection string                                  │
│ 4. Use in DATABASE_URL                                    │
└──────────────────────────────────────────────────────────┘

"@

Write-Host $db_info

Write-Host ""

# Step 8: Final checklist
Write-Step "Step 8: Pre-Deployment Checklist"
Write-Host ""

$checklist = @"
Before deploying, ensure you have:

□ GitHub account and repository
□ Render account (https://render.com)
□ Vercel account (https://vercel.com)
□ Database service set up (PostgreSQL, MySQL, or equivalent)
□ Updated REACT_APP_API_URL in frontend/.env.production
□ Committed all changes to Git
□ Tested locally:
  - Backend: gunicorn app.main:app --workers 1 --bind 0.0.0.0:8000
  - Frontend: npm run build && npm start

"@

Write-Host $checklist

Write-Host ""

# Step 9: Verification
Write-Step "Step 9: Post-Deployment Verification"
Write-Host ""

$verification = @"
After deployment, verify everything works:

1. Backend Health Check:
   curl https://fraud-detection-api.onrender.com/health

2. Frontend Access:
   Open https://your-project.vercel.app in browser

3. API Connectivity:
   Open browser console (F12)
   Check Network tab for API calls
   Should see requests to your Render backend

4. Check Logs:
   Render: Dashboard → Logs
   Vercel: Dashboard → Function Logs

"@

Write-Host $verification

Write-Host ""

# Step 10: Support
Write-Step "Step 10: Documentation & Support"
Write-Host ""
Write-Host "For detailed instructions, see:"
Write-Host "  📄 VERCEL_RENDER_DEPLOYMENT.md"
Write-Host ""
Write-Host "Resources:"
Write-Host "  🔗 Render Docs: https://render.com/docs"
Write-Host "  🔗 Vercel Docs: https://vercel.com/docs"
Write-Host "  🔗 FastAPI Docs: https://fastapi.tiangolo.com"
Write-Host ""

# Final summary
Write-Host ""
Write-Step "Setup Complete!"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Push changes to GitHub: git add . && git commit -m 'Add cloud deployment config'"
Write-Host "2. Create services on Render and Vercel"
Write-Host "3. Monitor deployments in dashboards"
Write-Host "4. Test end-to-end connectivity"
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "Deployment Guide Complete" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
