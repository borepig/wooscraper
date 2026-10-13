#!/bin/sh
# serve  — web UI on port 5000 (HTTP) and 5443 (HTTPS)
# batch   — scrape folders passed after the command, writing files onto the share
set -eu
cd /app

if [ "${1:-serve}" = "batch" ]; then
  shift
  exec python batch.py "$@"
fi

if [ "${1:-serve}" = "serve" ]; then
  shift
fi

exec python serve.py
