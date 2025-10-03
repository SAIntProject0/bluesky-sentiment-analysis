#!/bin/bash
set -e

echo "[$(date)] 🚀 Starting ReviewSky sentiment analysis..."

# Install deps
python3 -m venv venv
source venv/bin/activate
pip install -q requests

# Run analysis
python3 fetch_and_analyze.py

# No git config needed — GitHub Actions handles auth
git add data/sentiment.json
git commit -m "Update $(date)" && git push || echo "No changes"

echo "[$(date)] ✅ Done!"
