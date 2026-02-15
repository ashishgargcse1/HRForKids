#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"
COOKIE="/tmp/chorequest-cookie.txt"

echo "[1] Health check"
curl -sS "$BASE_URL/health" | grep -q '"ok":true\|"ok": true'

echo "[2] Login with default admin"
curl -sS -c "$COOKIE" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  "$BASE_URL/api/login" >/tmp/chq_login.json

grep -q '"role":"ADMIN"\|"role": "ADMIN"' /tmp/chq_login.json

echo "[3] /api/me"
curl -sS -b "$COOKIE" "$BASE_URL/api/me" >/tmp/chq_me.json
grep -q '"username":"admin"\|"username": "admin"' /tmp/chq_me.json

echo "[4] Create parent and child"
curl -sS -b "$COOKIE" -H 'Content-Type: application/json' \
  -d '{"username":"parent1","display_name":"Parent One","role":"PARENT","password":"parent123","avatar":"🧑"}' \
  "$BASE_URL/api/users" >/tmp/chq_parent.json
curl -sS -b "$COOKIE" -H 'Content-Type: application/json' \
  -d '{"username":"child1","display_name":"Child One","role":"CHILD","password":"child123","avatar":"🧒"}' \
  "$BASE_URL/api/users" >/tmp/chq_child.json

grep -q '"role":"PARENT"\|"role": "PARENT"' /tmp/chq_parent.json
grep -q '"role":"CHILD"\|"role": "CHILD"' /tmp/chq_child.json

echo "Self-check passed."
