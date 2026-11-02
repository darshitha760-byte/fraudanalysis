# Financial Risk Analysis and Hybrid Fraud Detection System

A production-grade Python application for detecting financial fraud using a combination of rule-based detection and machine learning, with comprehensive risk scoring and analyst review workflows.

## Features

### Core Capabilities
- **Rule-Based Fraud Detection**: Configurable rules stored in database (high-value transactions, velocity checks, geographic anomalies, duplicates, etc.)
- **Machine Learning Detection**: Logistic Regression, Random Forest, and Isolation Forest models with proper evaluation metrics
- **Financial Risk Scoring**: Explainable 0-100 risk scores combining multiple signals
- **Real-Time Fraud Assessment**: Hybrid pipeline for immediate detection on transaction creation
- **Comprehensive Audit Logging**: Complete forensic trail of all system actions
- **Role-Based Access Control**: Admin and analyst roles with granular permissions

### User Interface
- **FastAPI Backend**: RESTful API with JWT authentication and OpenAPI documentation
- **Modern React Console**: Responsive risk operations workspace at http://localhost:3000; see [frontend setup and training](frontend/README.md)
- **Streamlit Dashboard**: Interactive web interface for analysts and administrators
- **Responsive Design**: Professional analytics theme with real-time dashboards
- **Transaction Explorer**: Search, filter, and export transaction data
- **Fraud Alerts**: Analyst review queue with decision tracking

### Data Support
- **Public Dataset**: Credit Card Fraud Detection from Kaggle (requires manual download)
- **Synthetic Data Generation**: Realistic transaction generation with controlled fraud scenarios
- **Batch Import**: CSV import with validation and deduplication
- **Multiple Payment Methods**: Cards, bank transfers, wallets, and more

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Language** | Python | 3.12+ |
| **Backend Framework** | FastAPI | 0.104+ |
| **Frontend** | Streamlit | 1.29+ |
| **Database** | MongoDB | MongoDB 6.0+ / Atlas |
| **Driver** | PyMongo | 4.x |
| **Authentication** | JWT + Argon2 | PyJWT 2.15+, Argon2 25.1+ |
| **Data Processing** | Pandas, NumPy | 2.1+, 1.26+ |
| **Machine Learning** | Scikit-learn, Imbalanced-learn | 1.3+, 0.11+ |
| **Visualization** | Plotly | 5.18+ |

## Project Structure

```
financial-risk-fraud-detection/
├── app/                          # Main application package
│   ├── main.py                   # FastAPI entry point
│   ├── core/                     # Core configuration and security
│   │   ├── config.py             # Settings management
│   │   ├── security.py           # JWT and password utilities
│   │   └── permissions.py        # Role-based access control
│   ├── db/                       # Database layer
│   │   ├── database.py           # MongoDB client, indexes, BSON conversion
│   │   └── base.py               # Base model class
│   ├── models/                   # Pydantic MongoDB document models
│   │   ├── user.py               # User and authentication
│   │   ├── customer.py           # Customer information
│   │   ├── transaction.py        # Financial transactions
│   │   ├── fraud_rule.py         # Configurable fraud rules
│   │   ├── fraud_alert.py        # Alerts and assessments
│   │   └── audit_log.py          # Audit trail
│   ├── schemas/                  # Pydantic request/response schemas
│   ├── api/                      # API route handlers
│   │   ├── auth.py               # Authentication endpoints
│   │   ├── transactions.py       # Transaction management
│   │   ├── fraud.py              # Fraud detection and alerts
│   │   ├── analytics.py          # Analytics and reporting
│   │   ├── users.py              # User management
│   │   └── audit.py              # Audit log endpoints
│   ├── services/                 # Business logic services
│   │   ├── audit_service.py      # Audit logging
│   │   ├── transaction_service.py # Transaction processing
│   │   ├── fraud_engine.py       # Rule-based detection
│   │   ├── risk_engine.py        # Risk scoring
│   │   └── ml_service.py         # ML model management
│   └── ml/                       # Machine learning pipeline
│       ├── preprocessing.py      # Feature engineering
│       ├── train.py              # Model training
│       ├── predict.py            # Predictions
│       └── evaluate.py           # Model evaluation
├── dashboard/                    # Streamlit frontend
│   ├── app.py                    # Dashboard entry point
│   ├── pages/                    # Dashboard pages
│   │   ├── 01_Login.py           # Authentication
│   │   ├── 02_Executive_Overview.py
│   │   ├── 03_Transaction_Explorer.py
│   │   ├── 04_Fraud_Alerts.py
│   │   ├── 05_Financial_Risk_Analytics.py
│   │   ├── 06_Rule_Management.py (admin only)
│   │   ├── 07_Model_Performance.py
│   │   ├── 08_User_Management.py  (admin only)
│   │   └── 09_Audit_Logs.py
│   └── components/               # Reusable components
│       ├── charts.py
│       ├── filters.py
│       └── auth_handler.py
├── scripts/                      # Utility scripts
│   ├── init_db.py                # Database initialization
│   ├── create_admin.py           # Create admin user
│   ├── generate_synthetic_data.py # Synthetic transaction generation
│   ├── import_public_dataset.py  # Kaggle dataset import
│   ├── seed_rules.py             # Default rule creation
│   └── train_model.py            # ML model training
├── tests/                        # Test suite
│   ├── test_auth.py              # Authentication tests
│   ├── test_transactions.py      # Transaction API tests
│   ├── test_fraud_rules.py       # Rule engine tests
│   ├── test_risk_scoring.py      # Risk scoring tests
│   ├── test_ml.py                # ML pipeline tests
│   └── test_audit.py             # Audit logging tests
├── data/                         # Data files
│   ├── raw/                      # Raw data (CSVs, datasets)
│   └── processed/                # Processed data
├── models/                       # Trained ML models
├── reports/                      # Analysis reports
├── migrations/                   # Legacy SQL migration files (not used by runtime)
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment template
├── .gitignore                    # Git ignore rules
├── run.py                        # Application launcher
├── README.md                     # This file
└── ARCHITECTURE.md               # Architecture documentation

```

## Quick Start

### Prerequisites
- Python 3.12 or later
- An already-provisioned MongoDB deployment (not created by this application)
- pip (Python package manager)

### Installation

1. **Clone or download the project**
```bash
cd Financial\ Risk\ Analysis\ and\ Hybrid\ Fraud\ Detection\ System
```

2. **Create a virtual environment (optional but recommended)**
```bash
python -m venv venv
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your settings
```

5. **Initialize MongoDB indexes**
```bash
python scripts/init_db.py
```

6. **Create admin user**
```bash
python scripts/create_admin.py
```

7. **Seed default fraud rules**
```bash
python scripts/seed_rules.py
```

### Running the Application

**Terminal 1: Start FastAPI backend**
```bash
python run.py
# Or: uvicorn app.main:app --reload
```
Backend will be available at: `http://127.0.0.1:8000`

**Terminal 2: Start Streamlit dashboard**
```bash
streamlit run dashboard/app.py
```
Dashboard will be available at: `http://localhost:8501`

### API Documentation

Once the backend is running, visit:
- **OpenAPI (Swagger)**: `http://127.0.0.1:8000/api/docs`
- **ReDoc**: `http://127.0.0.1:8000/api/redoc`

## Key Endpoints

### Authentication
- `POST /auth/login` - User login
- `GET /auth/me` - Get current user
- `POST /auth/logout` - Logout

### Transactions
- `GET /transactions` - List transactions with filtering
- `POST /transactions` - Create transaction
- `POST /transactions/import` - Batch CSV import
- `GET /transactions/{transaction_id}` - Get transaction details
- `POST /transactions/{transaction_id}/assess` - Trigger fraud assessment

### Fraud Detection
- `GET /fraud/alerts` - List fraud alerts
- `GET /fraud/alerts/{alert_id}` - Alert details
- `POST /fraud/alerts/{alert_id}/review` - Analyst review

### Rules
- `GET /rules` - List fraud rules
- `POST /rules` - Create rule (admin)
- `PATCH /rules/{rule_id}` - Update rule (admin)

### Analytics
- `GET /analytics/overview` - Overview dashboard metrics
- `GET /analytics/risk-trends` - Risk trends over time
- `GET /analytics/model-performance` - ML model metrics

### Audit
- `GET /audit-logs` - Audit trail

## Configuration

### Environment Variables

Key settings in `.env`:

```bash
# Local development; for cloud deployment use the Atlas URI from a secret manager.
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=fraud_detection_db
```
<!-- Retired SQL-era example below is ignored by the application.
# The legacy DATABASE_URL line below is obsolete and ignored by the application.
DATABASE_URL=mysql+pymysql://fraud_user:password@localhost:3306/fraud_detection_db

-->
```bash
# JWT
SECRET_KEY=<generate-a-random-secret-of-at-least-32-characters>
JWT_EXPIRATION_HOURS=24

# FastAPI
FASTAPI_HOST=127.0.0.1
FASTAPI_PORT=8000
DEBUG=True
ENVIRONMENT=development

# Streamlit
STREAMLIT_SERVER_PORT=8501
API_BASE_URL=http://127.0.0.1:8000

# ML
ENABLE_ML_DETECTION=True
ML_MODEL_THRESHOLD=0.5
```

## Database Schema

### Core Collections

- **users**: User accounts with roles and authentication
- **customers**: Customer/account holder information
- **transactions**: Financial transactions with status and metadata
- **fraud_rules**: Configurable detection rules
- **fraud_assessments**: Risk scores and detection results
- **triggered_rules**: Rules triggered per transaction
- **fraud_alerts**: High-risk alerts for analyst review
- **audit_logs**: Complete action audit trail

The application runtime uses MongoDB through PyMongo; SQLAlchemy is isolated to
the optional, review-gated legacy data importer in `requirements-importer.txt`.
The importer defaults to dry-run and must not be run with `--apply` without a
separate explicit data-transfer approval.
Importer failures report a safe `stage` and `reason` (for example,
`stage=source_connection; reason=mysql_authentication_failed`) without printing
driver exception messages, credentials, or record contents. Correct the reported
connection or schema issue and repeat the dry-run; do not use `--apply` to bypass it.
Missing-table failures list only expected application tables as
`present_application_tables` and `missing_application_tables`. Verify the source
database selected by `MYSQL_IMPORT_URL`; do not create empty tables or skip missing
tables to bypass integrity checks.

The importer has two explicit source profiles: strict modern **plural** tables
(all ten collections required), and the recognized eight-table **singular**
legacy schema (`user`, `customer`, `fraud_rule`, `transaction_record`,
`fraud_assessment`, `triggered_rule`, `fraud_alert`, `audit_log`). Mixed profiles
are blocked. The singular profile explicitly reports absent `investigation_cases`
and `case_notes`; it never fabricates cases or silently skips a missing legacy
table or record.

Review an INFORMATION_SCHEMA metadata CSV **offline**, without settings, source
credentials, database connections or record reads:

```powershell
python scripts\import_mysql_to_mongodb.py --schema-csv C:\Users\SUSHANTH\Desktop\results1.csv
```

Only the metadata header `TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_KEY`
is accepted (maximum 1,000 metadata rows). A legacy report exits **1 (blocked)**,
not success. Counts are explicitly unavailable for metadata-only review. If
`MYSQL_IMPORT_URL` is supplied locally for a separately approved source review,
the legacy path uses schema inspection and aggregate-only SQL for source counts,
null mandatory values, conflicting identities/external keys, missing references,
and ambiguous assessment joins. It does not fetch records or contact MongoDB.
Do not paste credentials or record exports into chat.

The reusable profile/mapping in `scripts/mysql_schema_profiles.py` prepares
non-importable review candidates: preserve integer `id` and integer references;
use nonempty customer `external_id`, otherwise `legacy-customer-{id}`; generate
`legacy-transaction_record-{id}` for the missing external transaction identifier;
use source `rule_code` for rule identifiers. Assessment references require exactly
one source assessment per transaction; alert customer references require a unique
transaction and customer. Ambiguity blocks mapping. Customer names use both
existing nonblank name parts only; missing names block, and user full names are
never invented. Capitalized roles have an explicit `Admin/Analyst/Viewer` mapping,
not a general coercion.

All source fields remain in `legacy_metadata.source_fields`; exact timestamp text
is additionally retained in `legacy_metadata.source_timestamps` to preserve
microseconds/offsets beyond BSON date precision. Decimal values are never converted
through float. Legacy source timezone, score scale, severity and rule-weight
definitions are **unverified**: no normalization or score/category/severity
conversion is permitted. Transaction status/payment method, user full name,
rule/operator/threshold behavior, ML fields, alert status/review/assignment
meaning, audit category/target/status, and customer risk defaults also require
verified mappings. Neither model defaults nor invented assessments fill gaps.

**Legacy live apply remains disabled until full preflight is implemented and approved**, even with `--apply`
and matching `--confirm-target`. Reports list schema/mapping blockers and affected
source counts where available; target conflicts, Decimal precision and timestamp
validation are explicitly not checked during count-only review. Resolve field
definitions and obtain a separately reviewed, validated mapping before any data
transfer. The modern plural append-only path retains its dry-run default and
requires both `--apply` and an exact `--confirm-target` matching
`MONGODB_DATABASE`; offline `--schema-csv` cannot be combined with either flag.

#### Resolving legacy definitions explicitly

Historical source review found the singular schema in
`8532e82:scripts/create_schema.py`. Its `severity_level DEFAULT 1` and
`risk_weight DEFAULT 1.0` establish only defaults, **not** numeric severity meaning
or a score conversion. At the same revision, `app/models/fraud_rule.py` and
`app/services/risk_engine.py` operate on **plural** models. Their 0–100 scores and
LOW/MEDIUM/HIGH categories establish target behavior but cannot certify the older
singular records. No scoped historical session-timezone convention or evaluator
for `severity_level` was found. Those are genuinely missing definitions, not
values recoverable from the DECIMAL column declaration.

`--mapping-config <local-reviewed.json>` now supplies explicit, **nonsecret** JSON
decisions alongside offline metadata review or separately authorized count-only
source review. No mapping values are shipped or guessed. The JSON requires
`"version": 1`, `"profile": "legacy_singular_v1"`, `"reviewed": true`, and `"fields"`
(an object keyed by `source_table.target_field`). Each entry requires `"kind"`,
the exact `"source"` field, and a nonblank `"evidence"` reference to your reviewed
definition. Unsupported keys, duplicate keys, executable operations, unreviewed
files and files over 64 KiB are rejected. Evidence/configuration contents are never
printed; the canonical SHA-256 identifies the exact review.

Supported target/source pairs:

| Target key | Source | Operation |
|---|---|---|
| `fraud_rule.severity` | `severity_level` | enum |
| `fraud_rule.risk_weight` | `risk_weight` | decimal |
| `fraud_assessment.risk_score` | `risk_score` | decimal |
| `fraud_assessment.risk_category` | `risk_level` | enum |
| `fraud_assessment.ml_score` | `ml_prediction` | decimal or archive |
| `fraud_assessment.ml_confidence` | `ml_confidence` | archive |
| `triggered_rule.triggered_value` | `triggered_value` | archive |
| `fraud_alert.risk_score` | `risk_score` | decimal or archive |
| `fraud_alert.alert_status` | `alert_status` | enum |
| `fraud_alert.review_decision` | `review_decision` | enum or archive |
| `fraud_alert.assigned_to` | `assigned_to` | archive (never a reviewer) |
| `audit_log.action_category` | `action` | enum |
| `audit_log.target_type` | `target_entity` | enum |
| `audit_log.target_id` | `target_id` | archive (no guessed entity-reference cast) |

For `"kind": "enum"`, provide `"values"` mapping **exact** source strings (numeric
severity keys as JSON strings) to reviewed target values. Severity supports
low/medium/high/critical; assessment category LOW/MEDIUM/HIGH; alert status
pending/under_review/resolved/dismissed; review decisions
approved/rejected/needs_review/dismissed/escalated. Unmapped source values block;
case folding and numeric severity heuristics are not performed.

For `"kind": "decimal"`, explicitly provide **decimal strings**, not JSON numbers,
for `"source_min"`, `"source_max"`, `"target_min"`, `"target_max"`, `"multiplier"`
and `"offset"`. The reviewed transformation is `source * multiplier + offset`.
No clamping, float conversion or silent rounding is permitted. Source values must
be finite Decimal within the reviewed source range; results must be exactly
Decimal128-representable and in the reviewed target range (0–100 for scores, 0–1
for ML scores, nonnegative rule weight). Candidate assessment category mappings
must also agree with the target engine's exact boundaries (LOW ≤30, MEDIUM ≤70,
otherwise HIGH); inconsistencies block rather than recomputing a source category.
Candidate validation checks preserved source Decimals as well as mapped values,
then the target model without serializing its generated defaults. Metadata review does not prove that
actual rows satisfy these ranges. Count-only review counts invalid enum/range
values; per-record precision/model and target-conflict checks still require a
separately approved live-import workflow.

`"kind": "archive"` explicitly keeps a supported optional/unrepresentable field
only in legacy metadata. It does **not** reinterpret or expose an unknown score,
confidence, reviewer or entity reference to the application. Required assessment
scores cannot be archived into a valid live assessment. `"null_policy": "archive"`
is accepted only for supported optional fields; mandatory nulls still block.
This policy resolves irrelevant optional-field semantics without inventing data.

Optional `"timezone"` requires `"session_offset"` (a verified numeric offset such
as `+HH:MM`/`-HH:MM`, not SYSTEM, a guessed locale or a zone abbreviation) and
`"evidence"`. During authorized source review, the importer queries only
`@@session.time_zone`, `@@global.time_zone`, `@@system_time_zone`. The **session**
offset must exactly match the review before MySQL TIMESTAMP values can be
normalized. Global/system settings alone do not prove the source offset.
Target timestamp conversion retains original microseconds/offset text in metadata.
Offline review explicitly cannot verify server/session metadata.

Resolved configuration fields no longer produce unconditional semantic blockers.
Known-empty source tables likewise do not block for unused semantics; metadata-only
review never assumes a table is empty. Ambiguous joins still block: configuration
cannot select the newest assessment or create an assessment/customer.

Remaining decisions that cannot be answered by this metadata:
- Enrich actual user full names and missing customer name parts, or choose a
  **separate archival-only** workflow; no email-as-name or fake person mapping.
- Supply actual transaction status/payment method, customer risk profile, alert
  severity and audit status from an authoritative enrichment source, or archive
  rather than invent completed/success/low values.
- Confirm each legacy rule code/type/operator/threshold implements the current
  hard-coded R01–R10 evaluator; mapping severity/weight alone cannot prove this.
- Define source score/severity/ML semantics and review mappings, or explicitly
  archive the supported optional fields. Required assessment score/category still
  need verified definitions.
- Resolve duplicated/orphaned joins in an authoritative source or provide a
  separately approved identity-level resolution; never pick a record heuristically.

Safe **count-only** queries for a user-authorized source terminal (do not share
row exports/credentials):

```sql
SELECT @@session.time_zone, @@global.time_zone, @@system_time_zone;
SELECT COUNT(*) AS missing_user_full_names FROM `user`;
SELECT COUNT(*) AS missing_customer_names FROM customer
WHERE first_name IS NULL OR TRIM(first_name) = ''
   OR last_name IS NULL OR TRIM(last_name) = '';
SELECT MIN(risk_score) AS observed_min, MAX(risk_score) AS observed_max,
       SUM(risk_score IS NULL) AS missing_scores FROM fraud_assessment;
SELECT COUNT(*) AS ambiguous_alerts
FROM fraud_alert a JOIN (
  SELECT transaction_id FROM fraud_assessment GROUP BY transaction_id HAVING COUNT(*) > 1
) x ON x.transaction_id = a.transaction_id;
```

Observed ranges establish **data bounds only**, not business scale definitions.
No queries above are executed by offline review. `--apply` on the legacy path also
requires `--mapping-config` and `--confirm-mapping <exact SHA-256>` plus the existing
target confirmation, then remains blocked for unperformed live preflight. A matching
hash is not approval for record reads, target access or transfer.

#### Separate raw legacy archive (chosen resolution)

Use `--archive` to keep historical data **outside the live application's database
and models**. Unknown scores, missing names/statuses and ambiguous relationships
do not need operational interpretations in this archive. All eight singular
source tables are reviewed; original integer identities/references are retained.
No assessments/cases, names, statuses or business scales are synthesized. The
live application has no archive integration and must not receive archive credentials.

Start with this **offline metadata-only** command, which reads no records and
connects to neither database:

```powershell
python scripts\import_mysql_to_mongodb.py --archive --schema-csv C:\Users\SUSHANTH\Desktop\results1.csv
```

Success here means only recognized metadata, **not** validated archive contents
or approval to transfer. The report explicitly says counts/digest are unavailable.
No data transfer has been performed as part of preparing this feature.

Only after separately approving source-record review, set `MYSQL_IMPORT_URL` in
your local terminal (never paste it into chat), then run:

```powershell
python scripts\import_mysql_to_mongodb.py --archive --archive-database legacy_archive --batch-size 250
```

This default **dry-run** uses bounded keyset batches within a repeatable-read,
read-only MySQL transaction. It reviews original records locally in memory, emits
only table counts, a credential-sanitized content SHA-256, omission counts and
estimated BSON bytes. It does not access MongoDB, create export files or write any
target documents. Thus target conflicts and actual archive capacity are not yet
checked. Counts are printed in this exact order:
`user,customer,fraud_rule,transaction_record,fraud_assessment,triggered_rule,fraud_alert,audit_log`.

Archive documents go to these **singular** collections in a dedicated database,
not `users`, `customers` or other live collections. The archive database must differ
from `MONGODB_DATABASE` (case-insensitive comparison) and cannot be admin/config/local.
Original values are nested under `source_fields` with source table/identity,
archive format and per-document content hashes. Exact Decimals use Decimal128 where
representable, otherwise an explicitly tagged exact decimal string. Datetime/date/
time values are tagged original ISO text, retaining microseconds and explicit
offsets; naive values are marked timezone **unknown**, never falsely assigned UTC.
Raw values are labelled unverified/non-operational. There is no live schema/index/
sequence initialization or operational risk evaluation.

**Credential material is excluded**, including `user.password_hash` and recognized
password/token/key/connection fields recursively in structured audit data.
Recognizable embedded credential strings are redacted. Omission counts are
reported; hashes are computed only after credential removal. This is intentionally
**not a credential-preserving/lossless backup**. Contact details and free text
remain potentially sensitive: approve only the intended synthetic fields and
inspect/sanitize the source locally before transfer. A key/string filter cannot
guarantee detection of arbitrary unlabelled secrets; do not upload any source with
such material.

For a later, separately approved upload, set `MONGODB_ARCHIVE_URI` privately in the
local terminal using an archive-only writer credential. `MONGODB_URI` is not used
for archive upload. Supply the exact prior dry-run digest and comma-separated
count string (replace the placeholders):

```powershell
python scripts\import_mysql_to_mongodb.py --archive --archive-database legacy_archive --apply --confirm-target legacy_archive --confirm-archive-digest "<reviewed SHA-256>" --confirm-archive-counts "<reviewed count string>"
```

This is **not** permission to run the command now. Apply recomputes counts/digest
before target access and again during target preflight. Mismatches block; missing
proofs block. It checks every identity against the archive, refuses conflicting
content/unexpected collections, and performs append-only ordered inserts using
source numeric `_id`. Identical documents are skipped on rerun; no overwrites,
updates, drops, deletes or live database writes occur. Partial failures remain
explicit and can be reviewed/rerun without overwriting existing records. Source
should be frozen/read-only during the review and subsequent apply so its approved
digest remains stable.

The default `--archive-max-bytes` budget is 400 MiB. Dry-run reports BSON bytes only;
apply checks database data/index bytes plus twice pending BSON bytes for headroom.
This is an estimate, **not an Atlas quota guarantee**: manually check remaining
deployment-wide quota, other databases, indexes, storage/compression and plan
limits before upload; lower the budget when appropriate.

“Read-only archive” describes the intended subsequent viewing workflow and the
application separation, **not provisioned database permission enforcement**.
No Atlas permissions/users are created here. For later viewing, provision a
separate Atlas credential with `read` only on the archive database; keep the
temporary uploader credential separately scoped and revoke it after verification.
Do not give the live application archive read/write access or reuse its credential.

### Relationships
```
User → AuditLog (actor)
Customer → Transaction
Customer → FraudAlert
Transaction → FraudAssessment
Transaction → TriggeredRule
Transaction → FraudAlert
FraudRule → TriggeredRule
FraudAssessment → TriggeredRule
FraudAssessment → FraudAlert
```

## Fraud Detection Rules

### Implemented Rules

| ID | Name | Description | Severity |
|----|----|---|----------|
| R01 | High-Value Transaction | Amount exceeds configurable threshold | High |
| R02 | Transaction Velocity | Multiple transactions in time window | Medium |
| R03 | Unusual Amount | Deviation from customer baseline | High |
| R04 | Repeated Failures | Failed transactions pattern | Medium |
| R05 | Geographic Anomaly | Impossible travel scenarios | Critical |
| R06 | Duplicate Transaction | Potential duplicate based on amount/merchant/time | High |
| R07 | High Velocity | Many transactions in short interval | High |
| R08 | Unusual Hours | Transaction at abnormal time | Low |
| R09 | New Device/Merchant | First interaction with device or merchant | Medium |
| R10 | Distribution Deviation | Unusual pattern in customer data | Medium |

### Rule Engine Features
- Database-driven configuration (no code changes needed)
- Threshold customization per rule
- Enable/disable controls
- Severity levels and risk weights
- Detailed trigger explanations
- Graceful handling of missing fields

## Machine Learning Pipeline

### Supported Models
1. **Logistic Regression** - Baseline linear model
2. **Random Forest** - Nonlinear ensemble model
3. **Isolation Forest** - Unsupervised anomaly detection (optional)

### Evaluation Metrics
- Precision, Recall, F1-Score
- ROC-AUC, PR-AUC
- Confusion Matrix
- False Positive Rate

### Data Handling
- Chronological train/test split
- Class weight balancing
- Feature normalization
- Prevention of data leakage

### Model Evaluation
```bash
python scripts/train_model.py
```

## Security Features

### Authentication & Authorization
- JWT-based token authentication with expiration
- Argon2 password hashing (memory-hard, GPU-resistant)
- Role-based access control (Admin, Analyst, Viewer)
- Granular permission checks

### Data Protection
- MongoDB query construction with validated request models
- Request validation with Pydantic
- File upload size limits
- Safe CSV export against formula injection
- No logging of sensitive data (passwords, tokens, PII)

### Audit Trail
- Comprehensive logging of all actions
- Actor identification and request context
- Immutable audit log (append-only)
- Chained event tracking via request IDs

### Best Practices
- Environment-based secrets (never hardcoded)
- HTTPS enforcement in production
- CORS configuration
- Rate limiting ready (deploy-level)
- Secure password reset workflow (implement per deployment)

## Testing

### Run Tests
```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=html  # With coverage
```

### Test Coverage
- Authentication and token validation
- Password verification
- Transaction creation and import
- Fraud rule evaluation
- Risk scoring logic
- ML model training and prediction
- Alert generation
- Audit logging
- Database constraints

## Data Import

### Synthetic Data Generation
```bash
python scripts/generate_synthetic_data.py --count 50000
```

### Public Dataset Import
1. Download from: https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud
2. Place `creditcard.csv` in `data/raw/`
3. Run:
```bash
python scripts/import_public_dataset.py
```

## Logging

Logs are written to:
- Console (development)
- `logs/app.log` (configured in settings)

Log levels: DEBUG, INFO, WARNING, ERROR

## Production Deployment

### Critical Changes Required
1. **Set DEBUG=False** in environment
2. **Use strong SECRET_KEY** (minimum 32 characters, cryptographically random)
3. **Use HTTPS** with valid SSL certificates
4. **Database User**: Ensure minimal permissions (SELECT/INSERT/UPDATE only)
5. **Secrets Management**: Use AWS Secrets Manager, Azure KeyVault, or HashiCorp Vault
6. **Rate Limiting**: Deploy behind reverse proxy with rate limiting
7. **Monitoring**: Implement application monitoring (APM)
8. **Backups**: Regular encrypted database backups
9. **Audit**: External audit log archive
10. **API Gateway**: Consider API gateway for rate limiting and DDoS protection

### Deployment Options
- **Docker**: Container-based deployment
- **AWS**: ECS, RDS for MySQL, CloudFront for CDN
- **Azure**: App Service, Azure Database for MySQL, Azure Front Door
- **On-Premises**: K8s cluster with external MySQL database

## Limitations & Future Improvements

### Known Limitations
- Single-model inference (ensemble predictions as future work)
- In-memory model storage (migrate to shared storage for scaling)
- Basic rate limiting (implement Redis-based throttling)
- No multi-tenancy support
- Transaction immutability relies on database (consider blockchain for critical audits)
- ML models trained on historical data only (no online learning)

### Future Enhancements
1. Real-time model retraining pipeline
2. Multi-model ensemble predictions
3. Feature store integration
4. Distributed fraud detection (Kafka streaming)
5. Advanced explainability (SHAP, LIME)
6. Behavioral biometrics
7. Network analysis for fraud rings
8. Mobile app for on-the-go analyst reviews
9. Integration with external risk services
10. Automated fraud recovery workflows

## Troubleshooting

### MongoDB Connection Issues
```bash
# Set MONGODB_URI through your environment or secret manager.
# Set MONGODB_DATABASE to the intended database name.
# Startup fails explicitly when the URI is missing or MongoDB cannot be reached.
# Verify firewall rules
```

### Import Errors
```bash
# Ensure all dependencies installed
pip install -r requirements.txt

# Check Python path
echo $PYTHONPATH
# Add project root if needed: set PYTHONPATH=%cd%
```

### Dashboard Connection Issues
```bash
# Verify FastAPI is running on configured port
# Check CORS settings in .env
# Clear browser cache
# Test API directly: curl http://127.0.0.1:8000/health
```

### Model Training Failures
```bash
# Check data/raw/creditcard.csv exists
# Verify data format matches Kaggle dataset
# Check scikit-learn version compatibility
```

## Contributing

Contributions welcome! Areas for contribution:
- Additional fraud rules
- UI/UX improvements
- Performance optimization
- Additional test coverage
- Documentation improvements
- Integration examples

## License

This project is provided as-is for educational and portfolio purposes.

## Support

For issues, questions, or suggestions:
1. Check the troubleshooting section above
2. Review the API documentation at `/api/docs`
3. Check audit logs for debugging
4. Consult the architecture document

## Acknowledgments

- Credit Card Fraud Detection dataset from Kaggle (MLG-ULB)
- FastAPI framework and documentation
- Streamlit for rapid dashboard development
- PyMongo and MongoDB document storage

---

**Version**: 1.0.0  
**Last Updated**: October 2026  
**Status**: Phase 1-3 Completed, Phases 4-10 Pending
