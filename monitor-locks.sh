#!/bin/bash

# monitor-locks.sh - Monitor active PostgreSQL locks in real time

DB_CONTAINER=${DB_CONTAINER:-inventory_db}
DB_USER=${DB_USER:-inventory_user}
DB_NAME=${DB_NAME:-inventory_db}
INTERVAL=${INTERVAL:-2}

echo "============================================"
echo " Database Lock Monitor"
echo "============================================"
echo "  Container : $DB_CONTAINER"
echo "  Database  : $DB_NAME"
echo "  Refresh   : every ${INTERVAL}s"
echo "  Press Ctrl+C to stop"
echo "============================================"

if ! docker ps --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
  echo "❌ Container '$DB_CONTAINER' is not running."
  echo "   Run: docker-compose up -d"
  exit 1
fi

while true; do
  echo ""
  echo "🔒 Active Locks @ $(date '+%H:%M:%S')"
  echo "──────────────────────────────────────────"

  docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -x -c "
    SELECT
      pl.pid,
      pl.granted,
      pl.locktype,
      pl.mode,
      pl.relation::regclass AS table_name,
      psa.query,
      psa.state,
      psa.wait_event_type,
      psa.wait_event
    FROM pg_locks pl
    JOIN pg_stat_activity psa ON pl.pid = psa.pid
    WHERE pl.relation::regclass::text IN ('products','orders')
    ORDER BY pl.granted DESC, pl.pid;
  " 2>/dev/null || echo "  (no locks on products/orders tables)"

  echo ""
  echo "🚧 Blocked Queries:"
  echo "──────────────────────────────────────────"

  docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "
    SELECT
      blocked_locks.pid            AS blocked_pid,
      blocked_activity.usename     AS blocked_user,
      blocking_locks.pid           AS blocking_pid,
      blocking_activity.usename    AS blocking_user,
      left(blocked_activity.query, 60)  AS blocked_query,
      left(blocking_activity.query, 60) AS blocking_query
    FROM pg_catalog.pg_locks blocked_locks
    JOIN pg_catalog.pg_stat_activity blocked_activity
      ON blocked_activity.pid = blocked_locks.pid
    JOIN pg_catalog.pg_locks blocking_locks
      ON  blocking_locks.locktype      = blocked_locks.locktype
      AND blocking_locks.relation      IS NOT DISTINCT FROM blocked_locks.relation
      AND blocking_locks.page          IS NOT DISTINCT FROM blocked_locks.page
      AND blocking_locks.tuple         IS NOT DISTINCT FROM blocked_locks.tuple
      AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
      AND blocking_locks.pid          != blocked_locks.pid
    JOIN pg_catalog.pg_stat_activity blocking_activity
      ON blocking_activity.pid = blocking_locks.pid
    WHERE NOT blocked_locks.granted;
  " 2>/dev/null || echo "  (no blocked queries)"

  sleep "$INTERVAL"
done
