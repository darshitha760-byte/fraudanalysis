# Financial Risk Analysis & Hybrid Fraud Detection System
# Windows PowerShell Deployment Script
# Run as Administrator: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

param(
    [switch]$SkipDocker = $false,
    [switch]$NoDatabaseSeed = $false
)

# Configuration
$ProjectName = "Financial Risk Analysis & Fraud Detection System"
$RequiredDiskSpaceGB = 5

# Color codes
$colors = @{
    'Success' = 'Green'
    'Error'   = 'Red'
    'Warning' = 'Yellow'
    'Info'    = 'Cyan'
    'Header'  = 'Magenta'
}

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor $colors['Header']
    Write-Host $Message -ForegroundColor $colors['Header']
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor $colors['Header']
    Write-Host ""
}

function Write-Success {
    param([string]$Message)
    Write-Host "✓ $Message" -ForegroundColor $colors['Success']
}

function Write-Error {
    param([string]$Message)
    Write-Host "✗ $Message" -ForegroundColor $colors['Error']
}

function Write-Warning {
    param([string]$Message)
    Write-Host "⚠ $Message" -ForegroundColor $colors['Warning']
}

function Write-Info {
    param([string]$Message)
    Write-Host "ℹ $Message" -ForegroundColor $colors['Info']
}

function Test-CommandExists {
    param([string]$Command)
    try {
        if (Get-Command $Command -ErrorAction Stop) {
            return $true
        }
    }
    catch {
        return $false
    }
}

# Check if running as administrator
function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Main script
Write-Header $ProjectName

# Step 0: Check admin privileges
Write-Header "Step 0: Checking Administrator Privileges"
if (-not (Test-Administrator)) {
    Write-Warning "This script should preferably run as Administrator"
    Write-Info "Some features may have limited functionality without admin privileges"
}

# Step 1: Check prerequisites
Write-Header "Step 1: Checking Prerequisites"

$prereqsMet = $true

# Check Docker
if (Test-CommandExists docker) {
    $dockerVersion = docker --version
    Write-Success "Docker is installed: $dockerVersion"
}
else {
    Write-Error "Docker is not installed"
    Write-Info "Download from: https://www.docker.com/products/docker-desktop"
    $prereqsMet = $false
}

# Check Docker Compose
if (Test-CommandExists docker-compose) {
    $composeVersion = docker-compose --version
    Write-Success "Docker Compose is installed: $composeVersion"
}
else {
    Write-Error "Docker Compose is not installed"
    Write-Info "It's usually included with Docker Desktop"
    $prereqsMet = $false
}

# Check Git
if (Test-CommandExists git) {
    $gitVersion = git --version
    Write-Success "Git is installed: $gitVersion"
}
else {
    Write-Error "Git is not installed"
    Write-Info "Download from: https://git-scm.com/download/win"
    $prereqsMet = $false
}

# Check Python (optional, for native installation)
if (Test-CommandExists python) {
    $pythonVersion = python --version
    Write-Success "Python is installed: $pythonVersion"
}
else {
    Write-Warning "Python is not installed (required only for native installation)"
}

# Check disk space
$diskInfo = Get-Volume -DriveLetter $PSScriptRoot[0]
$availableSpaceGB = [math]::Round($diskInfo.SizeRemaining / 1GB, 2)

if ($availableSpaceGB -ge $RequiredDiskSpaceGB) {
    Write-Success "Sufficient disk space: $availableSpaceGB GB"
}
else {
    Write-Warning "Low disk space: $availableSpaceGB GB (minimum $RequiredDiskSpaceGB GB recommended)"
}

if (-not $prereqsMet) {
    Write-Error "Please install missing prerequisites and try again"
    exit 1
}

Write-Success "All prerequisites met!"

# Step 2: Repository setup
Write-Header "Step 2: Repository Setup"

if (-not (Test-Path ".git")) {
    Write-Info "Repository not found at current location"
    $repoUrl = Read-Host "Enter the repository URL"
    
    if ([string]::IsNullOrEmpty($repoUrl)) {
        Write-Error "Repository URL is required"
        exit 1
    }
    
    Write-Info "Cloning repository..."
    git clone $repoUrl .
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Repository cloned successfully"
    }
    else {
        Write-Error "Failed to clone repository"
        exit 1
    }
}
else {
    Write-Info "Repository already exists"
    Write-Info "Pulling latest changes..."
    git pull origin main 2>&1 | Out-Null
    Write-Success "Repository up to date"
}

# Step 3: Environment configuration
Write-Header "Step 3: Environment Configuration"

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item -Path ".env.example" -Destination ".env"
        Write-Success ".env file created from template"
        Write-Warning "IMPORTANT: Please review and update .env with your configuration:"
        Write-Info "  - Database credentials"
        Write-Info "  - Secret key"
        Write-Info "  - API settings"
        
        $continue = Read-Host "Press Enter after updating .env, or type 'skip' to continue anyway"
    }
    else {
        Write-Error ".env.example not found"
        exit 1
    }
}
else {
    Write-Info ".env file already exists"
    $updateEnv = Read-Host "Do you want to review/update .env? (y/n)"
    if ($updateEnv -eq 'y') {
        notepad .env
    }
}

# Step 4: Build Docker images
if (-not $SkipDocker) {
    Write-Header "Step 4: Building Docker Images"
    
    Write-Info "Building Docker images (this may take several minutes)..."
    docker-compose build --no-cache
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Docker images built successfully"
    }
    else {
        Write-Error "Failed to build Docker images"
        exit 1
    }
}
else {
    Write-Info "Skipping Docker build (as requested)"
}

# Step 5: Start services
Write-Header "Step 5: Starting Services"

Write-Info "Starting all services..."
docker-compose up -d

if ($LASTEXITCODE -eq 0) {
    Write-Success "Services started successfully"
}
else {
    Write-Error "Failed to start services"
    exit 1
}

# Wait for services
Write-Info "Waiting for services to become healthy (15 seconds)..."
Start-Sleep -Seconds 15

# Step 6: Verify services
Write-Header "Step 6: Verifying Services"

$services = @("redis", "api", "frontend", "dashboard")

foreach ($service in $services) {
    $status = docker-compose ps $service 2>&1 | Select-String "Up" | Measure-Object | Select-Object -ExpandProperty Count
    
    if ($status -gt 0) {
        Write-Success "$service is running"
    }
    else {
        Write-Warning "$service may not be running"
    }
}

# Step 7: Database initialization
if (-not $NoDatabaseSeed) {
    Write-Header "Step 7: Database Initialization"
    
    Write-Info "Checking MongoDB connectivity and initializing indexes..."
    docker-compose exec -T api python run_migrations.py 2>&1 | Select-Object -Last 3
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "MongoDB connectivity verified and indexes initialized"
    }
    else {
        Write-Warning "MongoDB index initialization may have issues (check logs)"
    }
    
    Write-Info "Seeding sample data..."
    docker-compose exec -T api python seed_database.py 2>&1 | Select-Object -Last 3
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Database seeded with sample data"
    }
    else {
        Write-Warning "Database seeding may have issues (check logs)"
    }
}
else {
    Write-Info "Skipping database seeding (as requested)"
}

# Step 8: Health checks
Write-Header "Step 8: Health Checks"

Start-Sleep -Seconds 5

Write-Info "Checking API health..."
try {
    $apiHealth = Invoke-WebRequest -Uri "http://localhost:8000/health" -ErrorAction SilentlyContinue
    if ($apiHealth.StatusCode -eq 200) {
        Write-Success "API is healthy (HTTP 200)"
    }
    else {
        Write-Warning "API returned status code: $($apiHealth.StatusCode)"
    }
}
catch {
    Write-Warning "Could not reach API at http://localhost:8000"
}

Write-Info "Checking database connection..."
try {
    $dbHealth = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health/db" -ErrorAction SilentlyContinue
    if ($dbHealth.StatusCode -eq 200) {
        Write-Success "Database connection is healthy (HTTP 200)"
    }
    else {
        Write-Warning "Database check returned status code: $($dbHealth.StatusCode)"
    }
}
catch {
    Write-Warning "Could not check database health"
}

# Step 9: Display access information
Write-Header "Deployment Complete!"

Write-Success "Your application is now running!"
Write-Host ""
Write-Info "Access the application at:"
Write-Host "  API:                  http://localhost:8000" -ForegroundColor $colors['Success']
Write-Host "  API Documentation:    http://localhost:8000/docs" -ForegroundColor $colors['Success']
Write-Host "  Dashboard:            http://localhost:8501" -ForegroundColor $colors['Success']
Write-Host ""

Write-Info "Database access:"
Write-Host "  Host:          localhost" -ForegroundColor Cyan
Write-Host "  Port:          3307" -ForegroundColor Cyan
Write-Host "  Database:      fraud_detection" -ForegroundColor Cyan
Write-Host "  Username:      fraud_user" -ForegroundColor Cyan
Write-Host ""

Write-Info "Useful commands:"
Write-Host "  View logs:            docker-compose logs -f" -ForegroundColor $colors['Warning']
Write-Host "  Stop services:        docker-compose down" -ForegroundColor $colors['Warning']
Write-Host "  Restart services:     docker-compose restart" -ForegroundColor $colors['Warning']
Write-Host "  Rebuild images:       docker-compose build --no-cache" -ForegroundColor $colors['Warning']
Write-Host ""

Write-Warning "IMPORTANT - PRODUCTION SETUP CHECKLIST:"
Write-Host "  [ ] Update .env with strong, unique passwords" -ForegroundColor Yellow
Write-Host "  [ ] Configure SSL/TLS certificates" -ForegroundColor Yellow
Write-Host "  [ ] Set up automated database backups" -ForegroundColor Yellow
Write-Host "  [ ] Configure monitoring and logging" -ForegroundColor Yellow
Write-Host "  [ ] Run security audit" -ForegroundColor Yellow
Write-Host "  [ ] Set up rate limiting" -ForegroundColor Yellow
Write-Host ""

Write-Info "Documentation files:"
Write-Host "  DEPLOYMENT_TO_ANOTHER_SYSTEM.md   - Comprehensive deployment guide" -ForegroundColor Cyan
Write-Host "  DEPLOYMENT_GUIDE.md                - Detailed deployment instructions" -ForegroundColor Cyan
Write-Host "  OPERATIONS_RUNBOOK.md              - Operational procedures" -ForegroundColor Cyan
Write-Host ""

Write-Success "Setup completed at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""
