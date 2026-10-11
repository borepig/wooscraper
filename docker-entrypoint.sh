#!/bin/sh
# serve  — web UI on port 5000 (the default)
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

exec python -c "import os; from app import app; app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=False, use_reloader=False)"
