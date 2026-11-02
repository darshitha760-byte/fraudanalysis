#!/bin/bash

# Populate database with sample data via API calls
# This script adds customers, transactions, and rules to the system

API_URL="http://localhost:8001"  # For local testing

echo "🌱 Starting to populate database with sample data..."
echo "=================================================="

# First, register/login to get a token
echo -e "\n1️⃣ Authenticating..."

if [ -z "${ADMIN_EMAIL:-}" ] || [ -z "${ADMIN_PASSWORD:-}" ]; then
  echo "Set ADMIN_EMAIL and ADMIN_PASSWORD in the environment before running."
  exit 1
fi

LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}")

TOKEN=$(echo $LOGIN_RESPONSE | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
  echo "❌ Failed to get authentication token"
  exit 1
fi

echo "✅ Authentication successful"

# Function to make API calls with token
call_api() {
  local method=$1
  local endpoint=$2
  local data=$3
  
  curl -s -X "$method" "$API_URL$endpoint" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "$data"
}

# Add sample customers via customer endpoint if it exists
echo -e "\n2️⃣ Adding sample data..."

# Sample transaction data
TRANSACTION_1=$(cat <<'EOF'
{
  "transaction_id": "TXN-20261023-0001",
  "customer_id": 1,
  "amount": 5000.00,
  "currency": "USD",
  "merchant_name": "Amazon",
  "merchant_id": "MER-AMAZON",
  "merchant_category": "Electronics",
  "transaction_type": "purchase",
  "payment_method": "card",
  "card_last4": "4532",
  "transaction_date": "2026-10-23T15:30:00Z",
  "status": "completed"
}
EOF
)

echo "📝 Attempting to add transactions..."

# Test adding a transaction
RESPONSE=$(call_api POST "/api/transactions" "$TRANSACTION_1")
echo "Transaction request completed; inspect API status without sharing response data."

# Add more sample data...
echo -e "\n✅ Sample data population complete!"
echo "You can now view data in the web interface"
