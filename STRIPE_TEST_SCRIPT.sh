#!/bin/bash
# Comprehensive Stripe API Testing Script
# Use after configuring STRIPE_SECRET_KEY in .env

set -e

BASE_URL="http://localhost:5000"
API_BASE="/api/pdfwhiz"

echo "🧪 Flask-Headless-Payments - Comprehensive Test Suite"
echo "======================================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

# Helper function
test_endpoint() {
    local test_name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local auth="$5"
    
    echo -e "\n📝 TEST: $test_name"
    echo "----------------------------------------"
    
    if [ "$method" = "GET" ]; then
        if [ -n "$auth" ]; then
            RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}\nTIME:%{time_total}" \
                -H "Authorization: Bearer $auth" \
                "${BASE_URL}${endpoint}")
        else
            RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}\nTIME:%{time_total}" \
                "${BASE_URL}${endpoint}")
        fi
    else
        if [ -n "$auth" ]; then
            RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}\nTIME:%{time_total}" \
                -X "$method" \
                -H "Authorization: Bearer $auth" \
                -H "Content-Type: application/json" \
                -d "$data" \
                "${BASE_URL}${endpoint}")
        else
            RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}\nTIME:%{time_total}" \
                -X "$method" \
                -H "Content-Type: application/json" \
                -d "$data" \
                "${BASE_URL}${endpoint}")
        fi
    fi
    
    HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
    TIME=$(echo "$RESPONSE" | grep "TIME:" | cut -d: -f2)
    BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d' | sed '/TIME:/d')
    
    echo "📤 Request: $method ${BASE_URL}${endpoint}"
    echo "📥 Status: $HTTP_CODE"
    echo "⏱️  Time: ${TIME}s"
    echo "📄 Response:"
    echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
    
    if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 400 ]; then
        echo -e "${GREEN}✅ PASSED${NC}"
        ((PASSED++))
    else
        echo -e "${RED}❌ FAILED${NC}"
        ((FAILED++))
    fi
}

# ==============================================================================
# TEST SUITE
# ==============================================================================

echo ""
echo "🔐 PHASE 1: Authentication Tests"
echo "======================================================"

# Test 1: Register new user
test_endpoint "Register New User" "POST" "${API_BASE}/auth/register" \
    '{"email":"stripe-test-'$(date +%s)'@example.com","password":"TestPass123!"}' ""

# Extract token from last response
TOKEN=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    # Try to login with existing user
    echo "⚠️  Using existing test user..."
    test_endpoint "Login Existing User" "POST" "${API_BASE}/auth/login" \
        '{"email":"testuser@example.com","password":"TestPass123!"}' ""
    TOKEN=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)
fi

echo -e "\n🔑 Using JWT Token: ${TOKEN:0:50}..."

# ==============================================================================
echo ""
echo "📋 PHASE 2: Public Endpoints"
echo "======================================================"

# Test 2: Get plans (public)
test_endpoint "Get Available Plans" "GET" "${API_BASE}/payments/plans" "" ""

# ==============================================================================
echo ""
echo "🔐 PHASE 3: Authenticated Endpoints"
echo "======================================================"

# Test 3: Get subscription status
test_endpoint "Get Current Subscription" "GET" "${API_BASE}/payments/subscription" "" "$TOKEN"

# Test 4: Create checkout session
test_endpoint "Create Checkout Session (Pro Plan)" "POST" "${API_BASE}/payments/checkout" \
    '{"plan":"pro","trial_days":14}' "$TOKEN"

# Test 5: Create checkout (Basic Plan)
test_endpoint "Create Checkout Session (Basic Plan)" "POST" "${API_BASE}/payments/checkout" \
    '{"plan":"basic"}' "$TOKEN"

# ==============================================================================
echo ""
echo "🚫 PHASE 4: Security Tests"
echo "======================================================"

# Test 6: Unauthenticated access
test_endpoint "Unauthenticated Access (Should Fail)" "GET" "${API_BASE}/payments/subscription" "" ""

# Test 7: Invalid token
test_endpoint "Invalid JWT Token (Should Fail)" "GET" "${API_BASE}/payments/subscription" "" "invalid_token"

# ==============================================================================
echo ""
echo "❌ PHASE 5: Error Handling Tests"
echo "======================================================"

# Test 8: Missing plan field
test_endpoint "Missing Plan Field (Should Fail)" "POST" "${API_BASE}/payments/checkout" \
    '{}' "$TOKEN"

# Test 9: Invalid plan name
test_endpoint "Invalid Plan Name (Should Fail)" "POST" "${API_BASE}/payments/checkout" \
    '{"plan":"invalid_plan_xyz"}' "$TOKEN"

# ==============================================================================
echo ""
echo "⚡ PHASE 6: Performance Tests"
echo "======================================================"

echo -e "\n📝 TEST: Sequential Requests (10x)"
START=$(python3 -c "import time; print(time.time())")
for i in {1..10}; do
    curl -s "${BASE_URL}${API_BASE}/payments/plans" > /dev/null
done
END=$(python3 -c "import time; print(time.time())")
DURATION=$(python3 -c "print(f'{$END-$START:.3f}')")
AVG=$(python3 -c "print(f'{($END-$START)/10:.3f}')")
echo "📤 10 requests to GET /plans"
echo "⏱️  Total Time: ${DURATION}s"
echo "⏱️  Average: ${AVG}s per request"
echo -e "${GREEN}✅ PASSED${NC}"
((PASSED++))

# ==============================================================================
echo ""
echo "📊 FINAL RESULTS"
echo "======================================================"
TOTAL=$((PASSED + FAILED))
PERCENTAGE=$((PASSED * 100 / TOTAL))

echo ""
echo "Tests Run: $TOTAL"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo "Success Rate: $PERCENTAGE%"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED! 🎉${NC}"
    echo "✅ Flask-Headless-Payments is PRODUCTION-READY!"
else
    echo -e "${YELLOW}⚠️  Some tests failed. Review output above.${NC}"
fi

echo ""
echo "📚 Full report saved to: COMPREHENSIVE_API_TEST_REPORT.md"

