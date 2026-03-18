#!/bin/bash

# concurrent-test.sh - Simulate concurrent API requests for testing locking mechanisms

ENDPOINT=${1:-optimistic}
BASE_URL=${BASE_URL:-http://localhost:8080}
PRODUCT_ID=${PRODUCT_ID:-1}
QUANTITY=${QUANTITY:-5}
NUM_REQUESTS=${NUM_REQUESTS:-20}

if [[ "$ENDPOINT" != "pessimistic" && "$ENDPOINT" != "optimistic" ]]; then
  echo "Usage: $0 [pessimistic|optimistic]"
  echo ""
  echo "  pessimistic  - Test pessimistic locking endpoint"
  echo "  optimistic   - Test optimistic locking endpoint"
  exit 1
fi

URL="$BASE_URL/api/orders/$ENDPOINT"

echo "============================================"
echo " Concurrent Order Test — $ENDPOINT locking"
echo "============================================"
echo "  URL        : $URL"
echo "  Product ID : $PRODUCT_ID"
echo "  Quantity   : $QUANTITY per order"
echo "  Requests   : $NUM_REQUESTS concurrent"
echo "============================================"

# Reset inventory before test
echo ""
echo "🔄 Resetting inventory..."
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/products/reset")
if [ "$HTTP" -eq 200 ]; then
  echo "✅ Inventory reset successfully"
else
  echo "❌ Reset failed (HTTP $HTTP)" && exit 1
fi

echo ""
echo "📦 Initial product state:"
curl -s "$BASE_URL/api/products/$PRODUCT_ID" | python3 -m json.tool 2>/dev/null || curl -s "$BASE_URL/api/products/$PRODUCT_ID"

echo ""
echo "🚀 Firing $NUM_REQUESTS concurrent requests..."

TMPDIR_RESULTS=$(mktemp -d)
trap "rm -rf $TMPDIR_RESULTS" EXIT

PIDS=()
for i in $(seq 1 $NUM_REQUESTS); do
  curl -s \
    -o "$TMPDIR_RESULTS/resp_${i}.json" \
    -w "%{http_code}" \
    -X POST "$URL" \
    -H "Content-Type: application/json" \
    -d "{\"productId\": $PRODUCT_ID, \"quantity\": $QUANTITY, \"userId\": \"user-${ENDPOINT}-${i}\"}" \
    > "$TMPDIR_RESULTS/status_${i}.txt" &
  PIDS+=($!)
done

for pid in "${PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done

echo ""
echo "📊 Results:"
echo "-------------------------------------------"

SUCCESS=0
FAILED_STOCK=0
FAILED_CONFLICT=0
OTHER=0

for i in $(seq 1 $NUM_REQUESTS); do
  CODE=$(cat "$TMPDIR_RESULTS/status_${i}.txt" 2>/dev/null || echo "000")
  case "$CODE" in
    201) ((SUCCESS++)) ;;
    400) ((FAILED_STOCK++)) ;;
    409) ((FAILED_CONFLICT++)) ;;
    *)   ((OTHER++)) ;;
  esac
done

echo "  ✅ Successful (201)         : $SUCCESS"
echo "  📭 Out of stock (400)       : $FAILED_STOCK"
echo "  ⚔️  Conflict/retries (409)   : $FAILED_CONFLICT"
echo "  ❓ Other                    : $OTHER"
echo "  📬 Total sent               : $NUM_REQUESTS"

echo ""
echo "📦 Final product state:"
curl -s "$BASE_URL/api/products/$PRODUCT_ID" | python3 -m json.tool 2>/dev/null || curl -s "$BASE_URL/api/products/$PRODUCT_ID"

echo ""
echo "📈 Order stats:"
curl -s "$BASE_URL/api/orders/stats" | python3 -m json.tool 2>/dev/null || curl -s "$BASE_URL/api/orders/stats"

echo ""
echo "============================================"
echo " Test complete!"
echo "============================================"
