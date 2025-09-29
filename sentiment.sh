#!/bin/bash
set -e  # Exit on error

echo "[$(date)] 🚀 Starting Bluesky sentiment analysis..."

# Install deps (only first run)
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q requests

# Run analysis
python3 fetch_and_analyze.py

# Ensure data dir exists
mkdir -p data

# Commit to GitHub (so Pages updates)
git config --global user.email "action@github.com"
git config --global user.name "Cron Job"
git add data/sentiment.json
git commit -m "Auto-update $(date)" || echo "No changes to commit"
git push

echo "[$(date)] ✅ Done!" >> sentiment.log
