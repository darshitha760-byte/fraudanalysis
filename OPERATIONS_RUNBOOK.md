# Legacy Operations Runbook — SQL Procedures Retired

> **Do not execute the historical SQL/PostgreSQL commands below.** The active
> application uses MongoDB through PyMongo with `MONGODB_URI` and
> `MONGODB_DATABASE`. Use the MongoDB provider's approved backup, restore,
> monitoring, and access-control procedures for the target deployment. No
> MongoDB maintenance, backup, restore, or data transfer was run in this task.
> `python run_migrations.py initialize` only checks connectivity and ensures
> indexes; it does not perform SQL schema migration or transfer records.

Common operational procedures, troubleshooting steps, and maintenance tasks for the Fraud Detection Dashboard system.

---

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Backup & Recovery](#backup--recovery)
3. [Scaling & Performance](#scaling--performance)
4. [Security & Updates](#security--updates)
5. [Incident Response](#incident-response)
6. [Logs & Monitoring](#logs--monitoring)
7. [Database Administration](#database-administration)
8. [Troubleshooting](#troubleshooting)

---

## Daily Operations

### Morning Health Check

**Frequency**: Once per day (morning)
**Time**: ~5 minutes
**Owner**: DevOps / On-call Engineer

```bash
#!/bin/bash
# health-check.sh

echo "=== Daily Health Check ==="
echo "Time: $(date)"

# Check containers status
echo -e "\n1. Container Status:"
docker-compose -f docker-compose.dashboard.yml ps --format "table {{.Names}}\t{{.Status}}"

# Check CPU and Memory
echo -e "\n2. Resource Usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Check API health
echo -e "\n3. API Health:"
curl -s http://localhost:8000/health | jq '.' || echo "API DOWN"

# Check Dashboard health
echo -e "\n4. Dashboard Health:"
curl -s http://localhost:8501/_stcore/health && echo "OK" || echo "DASHBOARD DOWN"

# Check Database
echo -e "\n5. Database Status:"
docker-compose -f docker-compose.dashboard.yml exec db pg_isready -U postgres && echo "OK" || echo "DB DOWN"

# Check Redis
echo -e "\n6. Redis Status:"
docker-compose -f docker-compose.dashboard.yml exec redis redis-cli ping || echo "REDIS DOWN"

# Check Disk Space
echo -e "\n7. Disk Space:"
df -h | grep -E "^/dev/|^Filesystem|/$"

# Check Recent Errors
echo -e "\n8. Recent Errors (last 100 lines):"
docker-compose -f docker-compose.dashboard.yml logs --tail=100 | grep -i error || echo "No errors found"

echo -e "\n=== Health Check Complete ==="
```

**Run it daily**:
```bash
# Add to crontab
crontab -e
# Add: 0 8 * * * /path/to/health-check.sh >> /var/log/health-check.log 2>&1
```

### Monitor Key Metrics

**Frequency**: Every 4 hours
**Time**: ~3 minutes
**Owner**: DevOps / Monitoring Team

```bash
#!/bin/bash
# monitor-metrics.sh

echo "=== System Metrics ==="

# Database connections
echo "Database Connections:"
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c \
  "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;"

# Slow queries
echo -e "\nTop 5 Slow Queries:"
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c \
  "SELECT query, calls, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 5;"

# Redis memory
echo -e "\nRedis Memory Usage:"
docker-compose -f docker-compose.dashboard.yml exec redis \
  redis-cli info memory | grep -E "used_memory|peak_memory|maxmemory"

# Disk usage
echo -e "\nPostgreSQL Disk Usage:"
du -sh /var/lib/docker/volumes/postgres_data
```

---

## Backup & Recovery

### Automated Daily Backup

**Frequency**: Once per day (02:00 AM)
**Retention**: 7 days
**Owner**: DevOps / DBA

```bash
#!/bin/bash
# backup-database.sh

BACKUP_DIR="/var/backups/fraud-detection"
DATABASE_NAME="fraud_db"
RETENTION_DAYS=7

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
BACKUP_FILE="$BACKUP_DIR/fraud_db_$(date +%Y%m%d_%H%M%S).sql.gz"
echo "Backing up database to: $BACKUP_FILE"

docker-compose -f docker-compose.dashboard.yml exec -T db \
  pg_dump -U postgres $DATABASE_NAME | gzip > $BACKUP_FILE

if [ $? -eq 0 ]; then
  echo "✓ Database backup successful"
  
  # Backup volumes
  VOLUME_BACKUP="$BACKUP_DIR/volumes_$(date +%Y%m%d_%H%M%S).tar.gz"
  docker run --rm -v postgres_data:/data -v $(pwd):/backup \
    alpine tar czf /backup/$(basename $VOLUME_BACKUP) /data
  echo "✓ Volume backup successful"
  
  # Cleanup old backups
  find $BACKUP_DIR -name "fraud_db_*.sql.gz" -mtime +$RETENTION_DAYS -delete
  find $BACKUP_DIR -name "volumes_*.tar.gz" -mtime +$RETENTION_DAYS -delete
  
  echo "✓ Old backups cleaned up"
  
  # Send notification
  echo "Database backup completed successfully" | \
    mail -s "Backup Success: $(date)" admin@example.com
else
  echo "✗ Database backup FAILED"
  echo "Database backup FAILED at $(date)" | \
    mail -s "ALERT: Backup Failed" admin@example.com
  exit 1
fi
```

**Setup automated backup**:
```bash
# Add to crontab
crontab -e
# Add: 0 2 * * * /path/to/backup-database.sh >> /var/log/backup.log 2>&1
```

### Point-in-Time Recovery

**Use case**: Need to recover data from specific point in time
**Time**: ~15 minutes
**Owner**: DBA

```bash
# 1. Stop application (prevent new writes)
docker-compose -f docker-compose.dashboard.yml stop api dashboard

# 2. List available backups
ls -lh /var/backups/fraud-detection/fraud_db_*.sql.gz

# 3. Restore from specific backup
BACKUP_FILE="/var/backups/fraud-detection/fraud_db_20240115_020000.sql.gz"
cat $BACKUP_FILE | gunzip | docker-compose -f docker-compose.dashboard.yml exec -T db \
  psql -U postgres fraud_db

# 4. Verify restore
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "SELECT COUNT(*) FROM transactions;"

# 5. Start application
docker-compose -f docker-compose.dashboard.yml start api dashboard

# 6. Monitor logs
docker-compose -f docker-compose.dashboard.yml logs -f
```

### Disaster Recovery Test

**Frequency**: Monthly
**Time**: ~30 minutes
**Owner**: DevOps Lead

```bash
#!/bin/bash
# disaster-recovery-test.sh

echo "=== Disaster Recovery Drill ==="
echo "Date: $(date)"
echo "Tester: $USER"

# 1. Create test backup
echo "Step 1: Creating test backup..."
BACKUP_FILE="/tmp/dr-test-$(date +%s).sql.gz"
docker-compose -f docker-compose.dashboard.yml exec -T db \
  pg_dump -U postgres fraud_db | gzip > $BACKUP_FILE
echo "✓ Backup created: $BACKUP_FILE"

# 2. Create test database
echo "Step 2: Creating test database..."
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -c "CREATE DATABASE fraud_db_test;"
echo "✓ Test database created"

# 3. Restore backup to test database
echo "Step 3: Restoring backup to test database..."
cat $BACKUP_FILE | gunzip | docker-compose -f docker-compose.dashboard.yml exec -T db \
  psql -U postgres fraud_db_test
echo "✓ Backup restored"

# 4. Verify data integrity
echo "Step 4: Verifying data integrity..."
COUNT_PROD=$(docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -t -c "SELECT COUNT(*) FROM transactions;")
COUNT_TEST=$(docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db_test -t -c "SELECT COUNT(*) FROM transactions;")

if [ "$COUNT_PROD" == "$COUNT_TEST" ]; then
  echo "✓ Data integrity verified (records: $COUNT_PROD)"
else
  echo "✗ Data mismatch! Prod: $COUNT_PROD, Test: $COUNT_TEST"
fi

# 5. Cleanup
echo "Step 5: Cleaning up..."
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -c "DROP DATABASE fraud_db_test;"
rm -f $BACKUP_FILE
echo "✓ Cleanup complete"

echo -e "\n=== Disaster Recovery Drill Complete ==="
```

---

## Scaling & Performance

### Monitor Slow Queries

**Frequency**: Daily for first month, then weekly
**Time**: ~5 minutes
**Owner**: DBA / Performance Engineer

```bash
#!/bin/bash
# slow-query-report.sh

echo "=== Slow Query Report ==="
echo "Generated: $(date)"

docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db << EOF
SELECT 
  query,
  calls,
  mean_time::numeric(10,2) as avg_ms,
  max_time::numeric(10,2) as max_ms,
  total_time::numeric(10,2) as total_ms
FROM pg_stat_statements
WHERE mean_time > 100  -- queries averaging > 100ms
ORDER BY mean_time DESC
LIMIT 20;
EOF
```

### Increase Resources

```bash
# Update docker-compose.yml with higher limits:

services:
  dashboard:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G

  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G

  db:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 4G

# Apply changes
docker-compose -f docker-compose.dashboard.yml down
docker-compose -f docker-compose.dashboard.yml up -d

# Verify
docker stats
```

### Database Optimization

```bash
# Run VACUUM (reclaim space)
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "VACUUM ANALYZE;"

# Update statistics
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "ANALYZE;"

# Check index health
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c \
  "SELECT tablename, indexname, idx_scan FROM pg_stat_user_indexes ORDER BY idx_scan ASC;"
```

---

## Security & Updates

### Security Patch Tuesday

**Frequency**: First Tuesday of each month
**Time**: ~2 hours (including testing)
**Owner**: DevOps / Security Team

```bash
#!/bin/bash
# security-update.sh

echo "=== Security Update Procedure ==="
echo "Date: $(date)"

# 1. Backup database
echo "Step 1: Backing up database..."
docker-compose -f docker-compose.dashboard.yml exec -T db \
  pg_dump -U postgres fraud_db | gzip > /tmp/pre-patch-backup.sql.gz
echo "✓ Backup complete"

# 2. Update base images
echo "Step 2: Updating base images..."
docker-compose -f docker-compose.dashboard.yml pull
echo "✓ Images updated"

# 3. Rebuild containers
echo "Step 3: Rebuilding containers..."
docker-compose -f docker-compose.dashboard.yml build --no-cache
echo "✓ Build complete"

# 4. Restart services (with monitoring)
echo "Step 4: Restarting services..."
docker-compose -f docker-compose.dashboard.yml down
docker-compose -f docker-compose.dashboard.yml up -d

# 5. Run health checks
echo "Step 5: Running health checks..."
sleep 30  # Wait for services to start
curl http://localhost:8000/health || exit 1
curl http://localhost:8501/_stcore/health || exit 1
echo "✓ Health checks passed"

# 6. Run smoke tests
echo "Step 6: Running smoke tests..."
./tests/smoke/run-tests.sh || exit 1
echo "✓ Smoke tests passed"

echo -e "\n=== Security Update Complete ==="
```

### Rotate Secrets

**Frequency**: Every 90 days
**Time**: ~1 hour
**Owner**: Security Lead

```bash
#!/bin/bash
# rotate-secrets.sh

echo "=== Secret Rotation Procedure ==="
echo "Old secrets will be deactivated in 24 hours"

# 1. Generate new secrets
NEW_JWT_KEY=$(openssl rand -base64 32)
NEW_DB_PASSWORD=$(openssl rand -base64 32)
NEW_REDIS_PASSWORD=$(openssl rand -base64 32)

# 2. Update .env.dashboard.prod
cp .env.dashboard.prod .env.dashboard.prod.backup
sed -i "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$NEW_JWT_KEY/" .env.dashboard.prod
sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$NEW_DB_PASSWORD/" .env.dashboard.prod
sed -i "s/REDIS_PASSWORD=.*/REDIS_PASSWORD=$NEW_REDIS_PASSWORD/" .env.dashboard.prod

# 3. Update GitHub secrets
gh secret set JWT_SECRET_KEY -b "$NEW_JWT_KEY"
gh secret set POSTGRES_PASSWORD -b "$NEW_DB_PASSWORD"
gh secret set REDIS_PASSWORD -b "$NEW_REDIS_PASSWORD"

# 4. Store old secrets (for 24-hour grace period)
cat > /tmp/old-secrets-backup.txt << EOF
Date: $(date)
Old JWT Key: (stored securely)
Old DB Password: (stored securely)
Old Redis Password: (stored securely)
Scheduled Deletion: $(date -d "+24 hours")
EOF

# 5. Restart services with new secrets
docker-compose -f docker-compose.dashboard.yml down
docker-compose -f docker-compose.dashboard.yml up -d

# 6. Verify
sleep 30
curl http://localhost:8000/health || echo "Health check failed!"

echo "✓ Secrets rotated successfully"
```

---

## Incident Response

### Service Down Alert

**Severity**: CRITICAL
**Response Time**: < 5 minutes
**Owner**: On-call Engineer

```bash
#!/bin/bash
# incident-response.sh

SERVICE=$1  # api, dashboard, db, redis
INCIDENT_ID=$(date +%s)

echo "=== INCIDENT #$INCIDENT_ID ==="
echo "Service: $SERVICE"
echo "Detected: $(date)"
echo "Time to respond: $(date)"

# Immediate actions
echo -e "\n1. Checking service status..."
docker-compose -f docker-compose.dashboard.yml ps $SERVICE

echo -e "\n2. Checking logs (last 50 lines)..."
docker-compose -f docker-compose.dashboard.yml logs --tail=50 $SERVICE

echo -e "\n3. Checking resource usage..."
docker stats --no-stream $SERVICE

# Attempt restart
echo -e "\n4. Attempting restart..."
docker-compose -f docker-compose.dashboard.yml restart $SERVICE

# Wait and verify
sleep 10
docker-compose -f docker-compose.dashboard.yml ps $SERVICE

if [ "$(docker-compose -f docker-compose.dashboard.yml ps -q $SERVICE)" ]; then
  echo -e "\n✓ Service recovered"
  STATUS="RESOLVED"
  DURATION=$(($(date +%s) - $INCIDENT_ID))
else
  echo -e "\n✗ Service failed to recover - escalating to Level 2 support"
  STATUS="ESCALATED"
  # Send alert
  echo "Service $SERVICE failed to recover. Manual intervention required." | \
    mail -s "CRITICAL: Incident #$INCIDENT_ID - $SERVICE Down" oncall@example.com
fi

# Log incident
cat >> /var/log/incidents.log << EOF
Incident #$INCIDENT_ID
Service: $SERVICE
Status: $STATUS
Duration: $DURATION seconds
Timestamp: $(date)
Responder: $USER
EOF
```

### Database Corruption

**Severity**: CRITICAL
**Response Time**: < 15 minutes
**Owner**: DBA / Senior Engineer

```bash
# 1. Immediately stop writes
docker-compose -f docker-compose.dashboard.yml stop api dashboard

# 2. Check database status
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "SELECT pg_database.datname, \
  pg_size_pretty(pg_database_size(pg_database.datname)) FROM pg_database;"

# 3. Run database integrity check
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "REINDEX DATABASE fraud_db;"

# 4. If recovery unsuccessful, restore from backup
echo "Restoring from latest backup..."
LATEST_BACKUP=$(ls -t /var/backups/fraud-detection/fraud_db_*.sql.gz | head -1)
cat $LATEST_BACKUP | gunzip | docker-compose -f docker-compose.dashboard.yml exec -T db \
  psql -U postgres fraud_db

# 5. Verify and restart
docker-compose -f docker-compose.dashboard.yml start api dashboard
```

---

## Logs & Monitoring

### View Logs

```bash
# All services
docker-compose -f docker-compose.dashboard.yml logs

# Specific service
docker-compose -f docker-compose.dashboard.yml logs dashboard

# Follow logs (real-time)
docker-compose -f docker-compose.dashboard.yml logs -f api

# Last 100 lines
docker-compose -f docker-compose.dashboard.yml logs --tail=100

# With timestamps
docker-compose -f docker-compose.dashboard.yml logs -t

# Specific time range
docker-compose -f docker-compose.dashboard.yml logs --since 2024-01-15 --until 2024-01-16

# Filter for errors
docker-compose -f docker-compose.dashboard.yml logs | grep -i error

# Export logs
docker-compose -f docker-compose.dashboard.yml logs > logs-$(date +%Y%m%d).txt
```

### Export Logs to ELK Stack

```yaml
# Add to docker-compose.yml
services:
  filebeat:
    image: docker.elastic.co/beats/filebeat:8.0.0
    volumes:
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./filebeat.yml:/usr/share/filebeat/filebeat.yml
    environment:
      - ELASTICSEARCH_HOSTS=["elasticsearch:9200"]
    depends_on:
      - elasticsearch
```

---

## Database Administration

### User Management

```bash
# Create new database user
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -c "CREATE USER analyst WITH PASSWORD 'secure_password';"

# Grant permissions
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst;"

# List users
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -c "\du"

# Drop user
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -c "DROP USER analyst;"
```

### Table Maintenance

```bash
# Analyze all tables
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "ANALYZE;"

# Vacuum full (slow but thorough)
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "VACUUM FULL;"

# Reindex all
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c "REINDEX DATABASE fraud_db;"

# Check table sizes
docker-compose -f docker-compose.dashboard.yml exec db \
  psql -U postgres -d fraud_db -c \
  "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose -f docker-compose.dashboard.yml logs <service>

# Check configuration
docker-compose -f docker-compose.dashboard.yml config

# Validate syntax
docker-compose -f docker-compose.dashboard.yml config --quiet

# Rebuild image
docker-compose -f docker-compose.dashboard.yml build --no-cache <service>

# Start with verbose logging
docker-compose -f docker-compose.dashboard.yml up <service>
```

### Network Connectivity Issues

```bash
# Test DNS resolution
docker-compose -f docker-compose.dashboard.yml exec dashboard \
  nslookup api

# Test connectivity
docker-compose -f docker-compose.dashboard.yml exec dashboard \
  ping api

# Check network configuration
docker network inspect $(docker-compose network ls | grep default | awk '{print $1}')

# Restart networking
docker-compose -f docker-compose.dashboard.yml down
docker network rm $(docker network ls | grep default | awk '{print $2}')
docker-compose -f docker-compose.dashboard.yml up -d
```

### High Memory Usage

```bash
# Check memory stats
docker stats

# Identify process using memory
docker-compose -f docker-compose.dashboard.yml exec api ps aux --sort=-%mem | head

# Reduce memory footprint
# - Clear Redis: docker-compose exec redis redis-cli FLUSHALL
# - Reduce Streamlit cache: streamlit cache clear
# - Analyze and optimize slow queries

# Increase container memory limit (in docker-compose.yml)
deploy:
  resources:
    limits:
      memory: 4G
```

---

## Maintenance Calendar

| Task | Frequency | Duration | Owner |
|------|-----------|----------|-------|
| Daily health check | Daily | 5 min | DevOps |
| Monitor metrics | Every 4h | 3 min | Monitoring |
| Database backup | Daily | 10 min | Automated |
| Security updates | Monthly | 2 hours | DevOps |
| Secret rotation | Quarterly | 1 hour | Security |
| DR test | Monthly | 30 min | DevOps Lead |
| Database optimization | Weekly | 15 min | DBA |
| Log rotation | Weekly | 5 min | Automated |
| Compliance audit | Quarterly | 2 hours | Security |
| Capacity planning | Monthly | 30 min | DevOps Lead |

---

## Escalation Path

**Level 1**: On-call Engineer (current responder)
**Level 2**: DevOps Lead (if Level 1 cannot resolve in 15 min)
**Level 3**: Engineering Manager (if Level 2 cannot resolve in 30 min)
**Level 4**: CTO (if Level 3 cannot resolve in 1 hour)

**Contact Info**:
- On-call: +1-555-0100 or oncall@example.com
- DevOps Lead: +1-555-0101 or devops@example.com
- Emergency: +1-555-0999 or emergency@example.com

---

**Last Updated**: 2024-01-15
**Next Review**: 2024-02-15
**Maintained By**: DevOps Team
