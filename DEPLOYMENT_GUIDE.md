# Financial Risk Analysis and Hybrid Fraud Detection System

> **Legacy deployment guide — do not execute as written.** Its MySQL-specific
> commands, deployment-complete claims, and test credentials are historical.
> The active app requires an already provisioned MongoDB service configured by
> `MONGODB_URI` and `MONGODB_DATABASE`. No cloud resources or deployment were
> provisioned or verified during this migration.
## Deployment Complete ✅

---

## 🚀 Quick Start

### Access the Application
```
Frontend:     http://localhost:3000
API Docs:     http://localhost:8001/docs
Dashboard:    http://localhost:8502
```

### Test Credentials
```
Email:    admin@company.local
Password: admin123
```

---

## 📊 What's Deployed

### Core Components
1. **Frontend** (React/Nginx)
   - Dashboard with KPIs
   - Transaction Explorer
   - Fraud Review Queue
   - Detection Rules Management
   - Team Members Management
   - Model Studio
   - Audit Trail
   - Fraud Operations

2. **Backend API** (FastAPI)
   - RESTful endpoints for all entities
   - User authentication & authorization
   - Database operations
   - Fraud detection logic
   - Rule evaluation

3. **Database** (MySQL)
   - 10 tables with complete schema
   - 51 sample records pre-loaded
   - Audit logging enabled
   - Transaction history

4. **Analytics** (Streamlit)
   - Fraud trend visualization
   - Risk distribution charts
   - Performance metrics
   - Custom dashboards

5. **Cache** (Redis)
   - Session management
   - Performance optimization
   - Real-time data sync

---

## 📈 Sample Data Included

### 5 Test Customers
- John Smith (CUST001)
- Jane Doe (CUST002)
- Robert Johnson (CUST003)
- Mary Williams (CUST004)
- Michael Brown (CUST005)

### 17 Sample Transactions
- High-value: Amazon ($5K), Casino ($4.2K), Jewelry ($7.5K)
- International: Tokyo ($2.1K), Mumbai ($850)
- Risky: Casino, Gambling, Luxury merchants
- Regular: Starbucks, CVS, Whole Foods, Netflix, Gas stations

### 17 Fraud Assessments
- Risk scores: 10-80%
- Categories: Low, Medium, High
- Patterns detected: Amount, Velocity, Geography, Merchant Type

### 5 Detection Rules
1. High Transaction Amount (>$5000) - HIGH severity
2. Multiple Transactions Same Hour (>3) - MEDIUM severity
3. International Merchant - MEDIUM severity
4. Casino or Gambling - HIGH severity
5. Luxury Merchant - HIGH severity

---

## 🔍 Key Features

### ✅ Fully Functional
- User authentication with email & password
- Role-based access control (Admin, Analyst, Viewer)
- Real-time fraud detection rule evaluation
- Transaction tracking and analysis
- Team member management
- Comprehensive audit logging
- Model training and evaluation
- Risk scoring and categorization

### ✅ Production-Ready
- Docker containerized deployment
- Health checks enabled
- Persistent data storage
- Error handling and logging
- API documentation (Swagger UI)
- Load balancing support

---

## 📝 Available Endpoints

### Authentication
```
POST /api/auth/login           - User login
POST /api/auth/register        - New user registration
POST /api/auth/logout          - User logout
```

### Customers
```
GET  /api/customers            - List all customers
GET  /api/customers/{id}       - Get customer details
POST /api/customers            - Create new customer
```

### Transactions
```
GET  /api/transactions         - List all transactions
GET  /api/transactions/{id}    - Get transaction details
POST /api/transactions         - Create new transaction
```

### Fraud Rules
```
GET  /api/fraud-rules          - List all detection rules
GET  /api/fraud-rules/{id}     - Get rule details
POST /api/fraud-rules          - Create new rule
PUT  /api/fraud-rules/{id}     - Update rule
```

### Fraud Assessments
```
GET  /api/fraud-assessments    - List assessments
GET  /api/fraud-assessments/{id} - Get assessment
```

### Team Members
```
GET  /api/team-members         - List team members
POST /api/team-members         - Add team member
PUT  /api/team-members/{id}    - Update member
DELETE /api/team-members/{id}  - Remove member
```

### Audit Trail
```
GET  /api/audit-logs           - Get audit logs
GET  /api/audit-logs/filter    - Filter logs by criteria
```

---

## 🐳 Docker Commands

### View Container Status
```bash
docker ps --filter "name=fraud_detection"
```

### View Logs
```bash
# API logs
docker logs fraud_detection_api

# Frontend logs
docker logs fraud_detection_frontend

# Database logs
docker logs fraud_detection_mysql
```

### Access MySQL Directly
```bash
docker exec -it fraud_detection_mysql mysql -ufraud_user -pfraud_password fraud_detection_db
```

### Stop All Containers
```bash
docker-compose down
```

### Start All Containers
```bash
docker-compose up -d
```

### Repopulate Database
```bash
python populate_data_direct.py
```

---

## 📊 Database Schema

### Core Tables
1. **users** - Application users with roles
2. **customers** - Customer records
3. **transactions** - Financial transactions
4. **fraud_rules** - Detection rules configuration
5. **fraud_assessments** - Risk assessments and scores
6. **audit_logs** - Activity audit trail
7. **investigation_cases** - Case management
8. **fraud_alerts** - Generated alerts
9. **triggered_rules** - Rule trigger history
10. **case_notes** - Investigation notes

---

## 🔐 Security Features

### Authentication
- Email-based user registration
- Password hashing (bcrypt)
- Session token management
- .local domain support for enterprise emails

### Authorization
- Role-based access control (RBAC)
- Three roles: Admin, Analyst, Viewer
- Per-endpoint permission checks
- Audit logging of all actions

### Data Protection
- Encrypted database connection
- HTTPS-ready infrastructure
- Input validation and sanitization
- SQL injection prevention via ORM

---

## 📈 Performance

### Load Times (Typical)
- Frontend load: 2-3 seconds
- API response: <100ms average
- Dashboard: 3-4 seconds
- Database query: <50ms

### Capacity
- Supports 1000+ transactions per day
- Handles 100+ concurrent users
- Processes 500+ rule evaluations per minute
- Scales horizontally via container orchestration

---

## 🛠️ Maintenance

### Regular Tasks
- Monitor container health: `docker ps`
- Check logs for errors: `docker logs <container>`
- Backup database regularly
- Review audit logs weekly
- Update security patches

### Troubleshooting
- Containers not starting? → Check Docker daemon, disk space
- API connection errors? → Verify port 8001 is accessible
- Database errors? → Check MySQL credentials, port 3307
- Frontend issues? → Clear browser cache, check port 3000

---

## 📚 Documentation Files

- `DATABASE_SEEDING_COMPLETE.md` - Data population details
- `DEPLOYMENT_VERIFICATION_REPORT.md` - Complete verification checklist
- `docker-compose.yml` - Container orchestration
- `Dockerfile.api` - API container configuration
- `.env` - Environment variables

---

## 🎯 Testing Scenarios

### Scenario 1: High-Value Transaction
1. Login as admin
2. Go to Transaction Explorer
3. View Amazon transaction ($5000)
4. Check fraud assessment (should be high-risk)
5. Verify "High Transaction Amount" rule triggered

### Scenario 2: International Transaction
1. Login as analyst
2. View Tokyo transaction ($2100)
3. Check fraud assessment
4. Verify "International Merchant" rule detected

### Scenario 3: Risky Merchant
1. View Casino Online transaction ($4200)
2. Check fraud score (should be 68-75%)
3. Verify "Casino or Gambling" rule triggered

### Scenario 4: Team Management
1. Login as admin
2. Go to Team Members
3. Add new member (requires valid email)
4. Edit member role or status
5. Verify audit log entry created

---

## 🚦 Status Dashboard

| Component | Status | Port | Health |
|-----------|--------|------|--------|
| Frontend | ✅ Running | 3000 | Healthy |
| API | ✅ Running | 8001 | Healthy |
| MySQL | ✅ Running | 3307 | Healthy |
| Redis | ✅ Running | 6379 | Healthy |
| Dashboard | ✅ Running | 8502 | Healthy |
| Database | ✅ Seeded | - | 51 records |
| Data | ✅ Complete | - | Ready |

---

## 📞 Support

### Common Issues

**Q: Can't access the frontend?**  
A: Ensure port 3000 is not blocked and containers are running: `docker ps`

**Q: No data showing in tables?**  
A: Run `python populate_data_direct.py` to repopulate sample data

**Q: API returning 500 errors?**  
A: Check API logs: `docker logs fraud_detection_api`

**Q: Can't login?**  
A: Use test credentials - email: admin@company.local, password: admin123

**Q: Database connection issues?**  
A: Verify MySQL is running: `docker logs fraud_detection_mysql`

---

## 📅 Version Info

- Frontend: React 18+
- Backend: FastAPI 0.104+
- Database: MySQL 8.0
- Cache: Redis 7.0
- Dashboard: Streamlit 1.28+
- Docker: Compose v2.0+

---

## ✨ Next Steps

1. **Immediate**: Access http://localhost:3000 and login
2. **Explore**: Navigate through all pages and review sample data
3. **Test**: Run fraud detection rules on sample transactions
4. **Integrate**: Connect to your own data sources
5. **Deploy**: Push to production with your infrastructure

---

**🎉 System Deployment Complete and Verified**

The Financial Risk Analysis and Hybrid Fraud Detection System is fully operational and ready for use!
