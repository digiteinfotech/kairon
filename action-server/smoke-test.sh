#!/usr/bin/env sh
# Smoke test for a running action server (compose service kairon-action-server or a local run).
# Usage: action-server/smoke-test.sh [base-url]   (default http://localhost:5055)
# Checks /healthcheck, request-id echo, and that /webhook answers a Rasa SDK request for an action with no
# config the way the Python server does (200 {"events":[],"responses":[]}), proving the consumer route is served.
set -eu

BASE="${1:-http://localhost:5055}"
fail() { echo "FAIL: $*" >&2; exit 1; }

health=$(curl -fsS -D - -H 'X-Kairon-Request-ID: smoke-1' "$BASE/healthcheck") || fail "healthcheck unreachable"
echo "$health" | grep -qi '^x-kairon-request-id: smoke-1' || fail "X-Kairon-Request-ID not echoed"
echo "$health" | grep -q 'health check ok' || fail "healthcheck body unexpected"

tmp=$(mktemp)
code=$(curl -sS -o "$tmp" -w '%{http_code}' -X POST "$BASE/webhook" \
  -H 'Content-Type: application/json' \
  -d '{"next_action":"smoke_test_unknown_action","sender_id":"smoke","tracker":{"sender_id":"smoke","slots":{"bot":"smoke"},"latest_message":{},"events":[]},"domain":{}}')
body=$(cat "$tmp"); rm -f "$tmp"
[ "$code" = "200" ] || fail "/webhook returned $code: $body"
echo "$body" | grep -q '"events"' || fail "/webhook body unexpected: $body"

echo "OK: $BASE healthcheck and /webhook respond"
