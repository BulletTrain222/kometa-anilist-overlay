#!/bin/bash
set -e

echo "🕒 AniList overlay updater starting..."
echo "⏱️  Run interval: every ${RUN_INTERVAL_HOURS} hour(s)"

while true; do
    echo "🚀 Running overlay update at $(date)"
    python3 /app/plex_anilist_overlay.py
    echo "✅ Finished run at $(date)"
    echo "🕓 Sleeping for ${RUN_INTERVAL_HOURS} hour(s)..."
    sleep $((RUN_INTERVAL_HOURS * 3600))
done
