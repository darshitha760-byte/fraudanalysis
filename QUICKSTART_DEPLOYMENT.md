# Legacy Quick Start Deployment Guide — Superseded

> **Do not execute the historical instructions below.** Active runtime
> persistence uses an already provisioned MongoDB service configured by
> `MONGODB_URI` and `MONGODB_DATABASE`. PostgreSQL/MySQL/Alembic setup, SQL
> backups, and restore steps are obsolete. No transfer or deployment occurred.

Get the Fraud Detection Dashboard system running in 5 minutes (development) or 15 minutes (production).

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [5-Minute Development Setup](#5-minute-development-setup)
3. [15-Minute Production Setup](#15-minute-production-setup)
4. [Verification & Testing](#verification--testing)
5. [Stopping & Cleanup](#stopping--cleanup)
6. [Common Issues](#common-issues)

---

## Prerequisites

### Required Software
- **Docker**: Version 20.10+ (installation: https://docs.docker.com/get-docker/)
- **Docker Compose**: Version 1.29+ (included with Docker Desktop)
- **Git**: For cloning the repository
- **curl**: For testing API endpoints

### Minimum System Requirements
- **CPU**: 4 cores recommended
- **RAM**: 8 GB minimum (16 GB recommended for production)
- **Disk**: 20 GB free space (30 GB+ for production with backups)
- **OS**: Linux, macOS, or Windows (with WSL2 or Docker Desktop)

### Verify Installation

```bash
# Check Docker
docker --version
# Output: Docker version 20.10.x or higher

# Check Docker Compose
docker-compose --version
# Output: Docker Compose version 1.29.x or higher

# Check git
git --version
# Output: git version 2.x or higher

# Check curl
curl --version
# Output: curl 7.x or higher
```

---

## 5-Minute Development Setup

Perfect for local development and testing.

### Step 1: Clone Repository

```bash
# Clone the project
git clone <repository-url>
cd "Financial Risk Analysis and Hybrid Fraud Detection System"

# List project structure
ls -la
```

Expected files:
- `docker-compose.dashboard.yml` ✅
- `Dockerfile.dashboard` ✅
- `Dockerfile.api` ✅
- `.env.dashboard.template` ✅
- `nginx.conf` ✅

### Step 2: Configure Environment

```bash
# Copy template to actual environment file
cp .env.dashboard.template .env.dashboard

# View configuration (optional)
cat .env.dashboard

# Key settings in .env.dashboard:
# API_BASE_URL=http://api:8000
# STREAMLIT_SERVER_PORT=8501
# POSTGRES_PASSWORD=postgres
# REDIS_HOST=redis
```

### Step 3: Start All Services

```bash
# Start containers in detached mode
docker-compose -f docker-compose.dashboard.yml up -d

# Monitor startup (run in separate terminal)
docker-compose -f docker-compose.dashboard.yml logs -f

# Wait 30-60 seconds for services to be ready
# You'll see messages like:
# dashboard  | Welcome to Streamlit!
# api        | INFO:     Application startup complete
# db         | database system is ready to accept connections
```

### Step 4: Verify Services Running

```bash
# Check all containers are running
docker-compose -f docker-compose.dashboard.yml ps

# Expected output:
# NAME            STATUS          PORTS
# fraud-api       Up 2 minutes    8000/tcp
# fraud-dashboard Up 2 minutes    8501/tcp
# fraud-db        Up 2 minutes    5432/tcp
# fraud-redis     Up 2 minutes    6379/tcp
```

### Step 5: Access Application

Open in your browser:

- **Dashboard**: http://localhost:8501
- **API Documentation**: http://localhost:8000/docs
- **API ReDoc**: http://localhost:8000/redoc

---

## 15-Minute Production Setup

For production deployment on a remote server.

### Step 1: Prepare Server

```bash
# SSH into your production server
ssh user@production.example.com

# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker (Ubuntu/Debian example)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add current user to docker group (optional but recommended)
sudo usermod -aG docker $USER
newgrp docker

# Verify installation
docker --version
docker-compose --version
```

### Step 2: Clone & Configure

```bash
# Clone repository
cd /opt
sudo git clone <repository-url> fraud-detection
sudo chown -R $USER:$USER fraud-detection
cd fraud-detection

# Copy and customize environment for production
cp .env.dashboard.template .env.dashboard.prod

# Edit production configuration
# IMPORTANT: Update these values:
nano .env.dashboard.prod
```

**Critical production settings to update:**

```env
# .env.dashboard.prod
API_BASE_URL=https://your-domain.com/api
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_SERVER_ALLOW_RUN_ON_SAVE=false

# Security: Generate strong passwords
POSTGRES_PASSWORD=$(openssl rand -base64 32)
JWT_SECRET_KEY=$(openssl rand -base64 32)

# Performance
STREAMLIT_CLIENT_MAX_MESSAGE_SIZE=50
MAX_UPLOAD_SIZE=100

# Environment
ENVIRONMENT=production
DEBUG_MODE=false
```

### Step 3: Configure Nginx (HTTPS/SSL)

```bash
# Obtain SSL certificate (using Let's Encrypt)
sudo apt-get install certbot python3-certbot-nginx -y

# Generate certificate (replace domain)
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# Verify certificate location
ls -la /etc/letsencrypt/live/your-domain.com/
# Should see: cert.pem, chain.pem, fullchain.pem, privkey.pem

# Update nginx.conf with your domain and certificate paths
# Replace:
#   server_name fraud-detection.example.com;
#   ssl_certificate /path/to/cert.pem;
#   ssl_certificate_key /path/to/key.pem;
```

### Step 4: Set Up Secrets

```bash
# Create secure directory for secrets
mkdir -p ~/.docker/secrets
chmod 700 ~/.docker/secrets

# Store sensitive values (alternative to .env.prod)
echo "your-jwt-secret-key" > ~/.docker/secrets/jwt_key
chmod 600 ~/.docker/secrets/jwt_key

# For GitHub Actions deployments, add GitHub Secrets:
# Settings > Secrets > New repository secret
# - DEPLOY_HOST: production.example.com
# - DEPLOY_USER: deploy_user
# - DEPLOY_KEY: ssh private key
# - PROD_ENV_FILE: contents of .env.dashboard.prod
```

### Step 5: Start Production Stack

```bash
# Create volumes for data persistence
docker volume create postgres_data
docker volume create redis_data

# Start with production profile (includes Nginx)
docker-compose -f docker-compose.dashboard.yml \
  --env-file .env.dashboard.prod \
  --profile production \
  up -d

# Verify all services
docker-compose -f docker-compose.dashboard.yml ps

# Check logs for errors
docker-compose -f docker-compose.dashboard.yml logs -f
```

### Step 6: Enable Auto-Renewal (Certificates)

```bash
# Set up certbot auto-renewal
sudo certbot renew --dry-run  # Test renewal

# Add to crontab (automatic renewal every 60 days)
sudo crontab -e
# Add line:
# 0 3 * * * /usr/bin/certbot renew --quiet && docker-compose -f /opt/fraud-detection/docker-compose.dashboard.yml restart nginx
```

### Step 7: Configure Firewall

```bash
# Allow necessary ports
sudo ufw enable
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS

# Verify firewall rules
sudo ufw status
```

### Step 8: Verify Production Deployment

```bash
# Check services are healthy
docker-compose -f docker-compose.dashboard.yml exec dashboard \
  curl -f http://localhost:8501/_stcore/health || echo "Dashboard unhealthy"

docker-compose -f docker-compose.dashboard.yml exec api \
  curl -f http://localhost:8000/health || echo "API unhealthy"

# View database logs
docker-compose -f docker-compose.dashboard.yml logs db

# Verify Nginx is proxying correctly
curl -I https://your-domain.com/
# Should see: 200 OK, various headers
```

---

## Verification & Testing

### Health Checks

```bash
# Check all services health
docker-compose -f docker-compose.dashboard.yml ps --format="table {{.Names}}\t{{.Status}}"

# Detailed health check
for service in api dashboard db redis; do
    echo "=== Checking $service ==="
    docker-compose -f docker-compose.dashboard.yml ps $service
done
```

### API Testing

```bash
# Get API status
curl http://localhost:8000/health
# Expected: {"status": "ok", "timestamp": "2024-..."}

# List API endpoints (Swagger UI)
curl http://localhost:8000/docs

# Make test request (examples depend on your backend)
curl -X GET http://localhost:8000/api/transactions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

### Dashboard Testing

```bash
# Check if dashboard is accessible
curl http://localhost:8501/_stcore/health
# Expected: 200 OK

# Check if Streamlit is serving pages
curl http://localhost:8501 | grep -o "<title>.*</title>"
# Expected: <title>Fraud Detection Dashboard</title>

# Test WebSocket (used by Streamlit for real-time updates)
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
  http://localhost:8501/_stcore/stream
# Expected: 101 Switching Protocols
```

### Database Testing

```bash
# Connect to database
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "SELECT version();"

# Check tables exist
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "\dt"

# Check data (example)
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "SELECT COUNT(*) FROM transactions LIMIT 10;"
```

### Performance Metrics

```bash
# Docker resource usage
docker stats

# Specific service stats
docker stats fraud-dashboard fraud-api fraud-db

# Database performance
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db \
  -c "SELECT * FROM pg_stat_statements LIMIT 10;"

# Redis memory usage
docker-compose -f docker-compose.dashboard.yml exec redis \
  redis-cli info memory
```

---

## Stopping & Cleanup

### Stop Services (Keep Data)

```bash
# Stop all containers
docker-compose -f docker-compose.dashboard.yml stop

# Verify stopped
docker-compose -f docker-compose.dashboard.yml ps

# Restart services later
docker-compose -f docker-compose.dashboard.yml start
```

### Full Shutdown (Remove Containers)

```bash
# Stop and remove containers
docker-compose -f docker-compose.dashboard.yml down

# Remove containers AND volumes (DELETES DATA!)
docker-compose -f docker-compose.dashboard.yml down -v

# Remove images
docker-compose -f docker-compose.dashboard.yml down --rmi all
```

### Cleanup Resources

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Remove unused networks
docker network prune

# Free up disk space (CAREFUL: removes all unused Docker resources)
docker system prune -a --volumes
```

---

## Common Issues

### Issue 1: Ports Already in Use

**Symptom**: Error like `Address already in use`

```bash
# Find what's using the port
sudo lsof -i :8501  # Dashboard port
sudo lsof -i :8000  # API port
sudo lsof -i :5432  # Database port

# Kill the process
sudo kill -9 <PID>

# Or change ports in docker-compose.yml
# Change "8501:8501" to "8502:8501"
```

### Issue 2: Out of Memory

**Symptom**: Container crashes, `OOMKilled`

```bash
# Check memory usage
docker stats

# Increase system swap (temporary)
free -h

# Increase Docker memory limits in docker-compose.yml
services:
  dashboard:
    deploy:
      resources:
        limits:
          memory: 2G
```

### Issue 3: Database Connection Failed

**Symptom**: "Cannot connect to database"

```bash
# Check database container is running
docker-compose -f docker-compose.dashboard.yml ps db

# Check database logs
docker-compose -f docker-compose.dashboard.yml logs db

# Test connection manually
docker-compose -f docker-compose.dashboard.yml exec db \
  pg_isready -U postgres

# Verify environment variables
docker-compose -f docker-compose.dashboard.yml config | grep POSTGRES
```

### Issue 4: API Not Responding

**Symptom**: Dashboard can't connect to API

```bash
# Check API container
docker-compose -f docker-compose.dashboard.yml ps api

# Check API logs for errors
docker-compose -f docker-compose.dashboard.yml logs api

# Test API from dashboard container
docker-compose -f docker-compose.dashboard.yml exec dashboard \
  curl http://api:8000/health

# Verify network connectivity
docker network inspect $(docker-compose network ls | grep default | awk '{print $1}')
```

### Issue 5: Slow Performance

**Symptom**: Dashboard/API slow to respond

```bash
# Check resource usage
docker stats

# Check for database slow queries
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c \
  "SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 5;"

# Check Redis hit rate
docker-compose -f docker-compose.dashboard.yml exec redis \
  redis-cli info stats

# Review Nginx logs
docker-compose -f docker-compose.dashboard.yml logs nginx | grep "upstream timed out"
```

### Issue 6: SSL Certificate Issues

**Symptom**: Browser warning about SSL, `ERR_SSL_PROTOCOL_ERROR`

```bash
# Verify certificate exists and is valid
sudo openssl x509 -in /etc/letsencrypt/live/your-domain.com/cert.pem -text -noout

# Check certificate expiration
sudo openssl x509 -enddate -noout \
  -in /etc/letsencrypt/live/your-domain.com/cert.pem

# Test SSL configuration
curl -I https://your-domain.com/

# Renew certificate immediately
sudo certbot renew --force-renewal

# Restart Nginx to reload certificate
docker-compose -f docker-compose.dashboard.yml restart nginx
```

---

## Monitoring & Alerts

### Basic Monitoring

```bash
# Watch logs in real-time
docker-compose -f docker-compose.dashboard.yml logs -f

# Watch specific service
docker-compose -f docker-compose.dashboard.yml logs -f api

# Follow logs with filtering
docker-compose -f docker-compose.dashboard.yml logs -f --tail=100 | grep ERROR
```

### Set Up Email Alerts (Optional)

```bash
# Install health check monitoring script
cat > health-check.sh << 'EOF'
#!/bin/bash
API_HEALTH=$(curl -s http://localhost:8000/health)
if [ $? -ne 0 ]; then
  echo "API is down!" | mail -s "Alert: Fraud Detection API Down" admin@example.com
fi

DASHBOARD_HEALTH=$(curl -s http://localhost:8501/_stcore/health)
if [ $? -ne 0 ]; then
  echo "Dashboard is down!" | mail -s "Alert: Fraud Detection Dashboard Down" admin@example.com
fi
EOF

chmod +x health-check.sh

# Schedule monitoring (every 5 minutes)
(crontab -l 2>/dev/null; echo "*/5 * * * * /path/to/health-check.sh") | crontab -
```

---

## Next Steps

### After Successful Deployment

1. **Read DOCKER_DEPLOYMENT.md** for advanced configuration
2. **Run DEPLOYMENT_CHECKLIST.md** to verify everything
3. **Set up external monitoring** (Prometheus, DataDog, etc.)
4. **Configure automated backups**
5. **Schedule security updates**
6. **Create runbooks** for your team

### Production Checklist

- [ ] SSL certificate installed and auto-renewing
- [ ] Firewall configured (only ports 80, 443, 22 open)
- [ ] Database backups automated and tested
- [ ] Monitoring and alerting configured
- [ ] Logging centralized (ELK stack, CloudWatch, etc.)
- [ ] Team trained on operational procedures
- [ ] Disaster recovery plan documented
- [ ] Load testing completed
- [ ] Security audit passed
- [ ] Go-live approval received

---

## Support

- **Detailed guide**: See DOCKER_DEPLOYMENT.md
- **Verification checklist**: See DEPLOYMENT_CHECKLIST.md
- **Dashboard features**: See dashboard/README.md
- **Testing procedures**: See DASHBOARD_TESTING.md

---

## Quick Reference Commands

```bash
# View status
docker-compose -f docker-compose.dashboard.yml ps

# View all logs
docker-compose -f docker-compose.dashboard.yml logs

# Stop all
docker-compose -f docker-compose.dashboard.yml stop

# Restart specific service
docker-compose -f docker-compose.dashboard.yml restart api

# Update and redeploy
git pull
docker-compose -f docker-compose.dashboard.yml down
docker-compose -f docker-compose.dashboard.yml pull
docker-compose -f docker-compose.dashboard.yml up -d

# Backup database
docker-compose -f docker-compose.dashboard.yml exec -T db \
  pg_dump -U postgres fraud_db | gzip > backup-$(date +%Y%m%d).sql.gz

# Access database shell
docker-compose -f docker-compose.dashboard.yml exec db psql -U postgres -d fraud_db

# View Redis data
docker-compose -f docker-compose.dashboard.yml exec redis redis-cli

# Prune unused Docker resources
docker system prune -a
```

---

**Happy deploying!** 🚀
