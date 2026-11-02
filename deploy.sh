#!/bin/bash

# Financial Risk Analysis & Hybrid Fraud Detection System
# Automated Deployment Script
# This script automates the setup process for a new system

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="Financial Risk Analysis & Fraud Detection System"
DOCKER_REQUIRED=true
INTERACTIVE=true

# Functions
print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

check_command() {
    if command -v $1 &> /dev/null; then
        print_success "$1 is installed"
        return 0
    else
        print_error "$1 is not installed"
        return 1
    fi
}

# Main script starts here
print_header "$PROJECT_NAME - Deployment Script"

# Step 1: Check prerequisites
print_header "Step 1: Checking Prerequisites"

OS_TYPE=$(uname -s)
print_info "Detected OS: $OS_TYPE"

# Check Docker
if check_command docker; then
    DOCKER_VERSION=$(docker --version)
    print_info "Docker version: $DOCKER_VERSION"
else
    print_error "Docker is required but not installed"
    print_info "Install Docker from: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check Docker Compose
if check_command docker-compose; then
    COMPOSE_VERSION=$(docker-compose --version)
    print_info "Docker Compose version: $COMPOSE_VERSION"
else
    print_error "Docker Compose is required but not installed"
    print_info "Install Docker Compose from: https://docs.docker.com/compose/install/"
    exit 1
fi

# Check Git
if ! check_command git; then
    print_error "Git is required but not installed"
    exit 1
fi

# Check available disk space
AVAILABLE_SPACE=$(df . | tail -1 | awk '{print $4}')
REQUIRED_SPACE=5242880  # 5GB in KB

if [ $AVAILABLE_SPACE -lt $REQUIRED_SPACE ]; then
    print_warning "Available disk space: $(($AVAILABLE_SPACE / 1048576))GB (less than 5GB recommended)"
else
    print_success "Sufficient disk space: $(($AVAILABLE_SPACE / 1048576))GB"
fi

# Step 2: Clone or update repository
print_header "Step 2: Repository Setup"

if [ ! -d ".git" ]; then
    print_info "Repository not found. Enter repository URL:"
    read -p "Repository URL: " REPO_URL
    
    if [ -z "$REPO_URL" ]; then
        print_error "Repository URL is required"
        exit 1
    fi
    
    print_info "Cloning repository..."
    git clone $REPO_URL .
    print_success "Repository cloned"
else
    print_info "Repository already exists"
    print_info "Pulling latest changes..."
    git pull origin main 2>/dev/null || print_warning "Could not pull updates"
fi

print_success "Repository ready"

# Step 3: Environment configuration
print_header "Step 3: Environment Configuration"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        print_success ".env file created from template"
        
        if [ "$INTERACTIVE" = true ]; then
            print_warning "Please review and update .env with your configuration"
            read -p "Press Enter to continue after editing .env..."
        fi
    else
        print_error ".env.example not found"
        exit 1
    fi
else
    print_info ".env file already exists"
fi

# Step 4: Build Docker images
print_header "Step 4: Building Docker Images"

print_info "This may take several minutes..."
docker-compose build --no-cache 2>&1 | grep -E "^Building|Successfully|^FROM|^RUN" || true

if [ $? -eq 0 ]; then
    print_success "Docker images built successfully"
else
    print_error "Failed to build Docker images"
    exit 1
fi

# Step 5: Start services
print_header "Step 5: Starting Services"

print_info "Starting all services..."
docker-compose up -d

if [ $? -eq 0 ]; then
    print_success "Services started"
else
    print_error "Failed to start services"
    exit 1
fi

# Wait for services to be ready
print_info "Waiting for services to become healthy..."
sleep 15

# Step 6: Verify services
print_header "Step 6: Verifying Services"

SERVICES=("redis" "api" "frontend" "dashboard")

for service in "${SERVICES[@]}"; do
    STATUS=$(docker-compose ps $service 2>/dev/null | grep -c "Up" || echo "0")
    
    if [ "$STATUS" -gt 0 ]; then
        print_success "$service is running"
    else
        print_error "$service is not running"
    fi
done

# Step 7: Initialize database
print_header "Step 7: Database Initialization"

print_info "Checking MongoDB connectivity and initializing indexes..."
docker-compose exec -T api python run_migrations.py 2>&1 | tail -5

if [ $? -eq 0 ]; then
    print_success "MongoDB connectivity verified and indexes initialized"
else
    print_warning "MongoDB index initialization may have issues"
fi

print_info "Seeding sample data..."
docker-compose exec -T api python seed_database.py 2>&1 | tail -5

if [ $? -eq 0 ]; then
    print_success "Database seeded with sample data"
else
    print_warning "Database seeding may have issues"
fi

# Step 8: Health checks
print_header "Step 8: Health Checks"

sleep 5

# Check API health
print_info "Checking API health..."
API_HEALTH=$(curl -s -w "%{http_code}" http://localhost:8000/health -o /dev/null)
if [ "$API_HEALTH" = "200" ]; then
    print_success "API is healthy (HTTP $API_HEALTH)"
else
    print_warning "API health check returned HTTP $API_HEALTH"
fi

# Check database connection
print_info "Checking database connection..."
DB_HEALTH=$(curl -s -w "%{http_code}" http://localhost:8000/api/v1/health/db -o /dev/null)
if [ "$DB_HEALTH" = "200" ]; then
    print_success "Database connection is healthy (HTTP $DB_HEALTH)"
else
    print_warning "Database health check returned HTTP $DB_HEALTH"
fi

# Step 9: Display access information
print_header "Deployment Complete!"

print_success "Your application is now running!"
echo ""
print_info "Access the application at:"
echo -e "  ${GREEN}API${NC}: http://localhost:8000"
echo -e "  ${GREEN}API Documentation${NC}: http://localhost:8000/docs"
echo -e "  ${GREEN}Dashboard${NC}: http://localhost:8501"
echo ""

print_info "Database access:"
echo -e "  Host: localhost"
echo -e "  Port: 3307"
echo -e "  Database: fraud_detection"
echo ""

print_info "Useful commands:"
echo -e "  View logs: ${YELLOW}docker-compose logs -f${NC}"
echo -e "  Stop services: ${YELLOW}docker-compose down${NC}"
echo -e "  Restart services: ${YELLOW}docker-compose restart${NC}"
echo ""

print_warning "IMPORTANT - PRODUCTION SETUP CHECKLIST:"
echo "  [ ] Update .env with strong, unique passwords"
echo "  [ ] Configure SSL/TLS certificates"
echo "  [ ] Set up automated database backups"
echo "  [ ] Configure monitoring and logging"
echo "  [ ] Run security audit"
echo "  [ ] Set up rate limiting"
echo ""

print_info "For detailed documentation, see:"
echo "  DEPLOYMENT_TO_ANOTHER_SYSTEM.md"
echo "  DEPLOYMENT_GUIDE.md"
echo "  OPERATIONS_RUNBOOK.md"
echo ""

print_success "Setup completed at $(date)"
