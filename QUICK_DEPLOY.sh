#!/bin/bash
# Quick Deployment Guide for Render and Vercel
# Run this script to get started with cloud deployment

set -e

echo "=================================================="
echo "Financial Risk Analysis & Fraud Detection System"
echo "Render & Vercel Deployment Quick Start"
echo "=================================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
print_step() {
    echo -e "${GREEN}▶ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Step 1: Check prerequisites
print_step "Step 1: Checking Prerequisites"
echo ""

if ! command -v git &> /dev/null; then
    print_error "Git is not installed. Please install Git first."
    exit 1
fi
print_step "✓ Git is installed"

if ! command -v npm &> /dev/null; then
    print_warning "npm is not installed. You'll need it for frontend deployment."
else
    print_step "✓ npm is installed"
fi

echo ""

# Step 2: Prepare files
print_step "Step 2: Verifying Deployment Configuration Files"
echo ""

files_to_check=(
    ".render.yaml"
    "Dockerfile.render"
    "requirements-production.txt"
    "frontend/vercel.json"
    "frontend/.env.example"
    "frontend/.env.production"
    "VERCEL_RENDER_DEPLOYMENT.md"
)

missing_files=()
for file in "${files_to_check[@]}"; do
    if [ -f "$file" ]; then
        print_step "✓ Found: $file"
    else
        print_error "Missing: $file"
        missing_files+=("$file")
    fi
done

if [ ${#missing_files[@]} -gt 0 ]; then
    echo ""
    print_error "Some configuration files are missing. Please ensure all files are present."
    exit 1
fi

echo ""

# Step 3: Git setup
print_step "Step 3: Setting up Git"
echo ""

# Check if we're in a git repo
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    print_error "Not a git repository. Please run: git init"
    exit 1
fi

print_step "✓ Git repository found"

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    print_warning "You have uncommitted changes. Commit them before deployment."
    echo "Run: git add . && git commit -m 'Prepare for cloud deployment'"
fi

echo ""

# Step 4: Environment setup
print_step "Step 4: Environment Variables Setup"
echo ""

if [ ! -f ".env" ]; then
    print_warning "No .env file found. Creating from template..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        print_step "✓ Created .env from .env.example"
        print_warning "Please update .env with your configuration"
    fi
fi

if [ ! -f "frontend/.env" ]; then
    print_warning "No frontend/.env file found. Creating from template..."
    if [ -f "frontend/.env.example" ]; then
        cp frontend/.env.example frontend/.env
        print_step "✓ Created frontend/.env from frontend/.env.example"
    fi
fi

echo ""

# Step 5: Backend deployment info
print_step "Step 5: Render Backend Deployment Instructions"
echo ""
cat << 'EOF'
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
   - Plan: Standard ($7/month)

6. Add Environment Variables:
   - DATABASE_URL: (Get from PostgreSQL database service)
   - REDIS_URL: (Get from Redis cache service or leave empty)
   - SECRET_KEY: (Generate a secure key)
   - ENVIRONMENT: production
   - DEBUG: false

7. Click "Deploy"
8. Monitor deployment in the Events tab
9. Once deployed, test: curl https://your-api.onrender.com/health

EOF

echo ""

# Step 6: Frontend deployment info
print_step "Step 6: Vercel Frontend Deployment Instructions"
echo ""
cat << 'EOF'
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

EOF

echo ""

# Step 7: Database setup
print_step "Step 7: Database Setup Options"
echo ""
cat << 'EOF'
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

EOF

echo ""

# Step 8: Final checklist
print_step "Step 8: Pre-Deployment Checklist"
echo ""
cat << 'EOF'
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

EOF

echo ""

# Step 9: Verification
print_step "Step 9: Post-Deployment Verification"
echo ""
cat << 'EOF'
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

EOF

echo ""

# Step 10: Support
print_step "Step 10: Documentation & Support"
echo ""
echo "For detailed instructions, see:"
echo "  📄 VERCEL_RENDER_DEPLOYMENT.md"
echo ""
echo "Resources:"
echo "  🔗 Render Docs: https://render.com/docs"
echo "  🔗 Vercel Docs: https://vercel.com/docs"
echo "  🔗 FastAPI Docs: https://fastapi.tiangolo.com"
echo ""

# Final summary
echo ""
print_step "Setup Complete!"
echo ""
echo "Next steps:"
echo "1. Push changes to GitHub: git add . && git commit -m 'Add cloud deployment config'"
echo "2. Create services on Render and Vercel"
echo "3. Monitor deployments in dashboards"
echo "4. Test end-to-end connectivity"
echo ""
echo "=================================================="
echo "Deployment Guide Complete"
echo "=================================================="
