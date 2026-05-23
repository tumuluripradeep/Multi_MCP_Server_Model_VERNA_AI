#!/bin/sh
# Canonical production entry: supervisord runs `python /app/main.py` (Verna orchestrator)
# plus nginx on :8080. Do not replace this with `streamlit run` alone — clients are started by main.py.
set -e
cd /app || exit 1
echo "Verna: starting supervisord → python main.py + nginx (ingress 8080 → Streamlit / API)"
exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
