#!/bin/bash
set -e  # Exit on error

# Activate the venv created by the workflow
source venv/bin/activate

echo "[$(date)] 🚀 Starting Bluesky sentiment analysis..."

# Install dependencies if the venv directory does not exist
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q requests

# Run the sentiment analysis script
python3 fetch_and_analyze.py

# Ensure the data directory exists
mkdir -p data

# Git config and authentication for GitHub push
git config --global user.email "action@github.com"
git config --global user.name "GitHub Action"
git remote set-url origin https://x-access-token:${GITHUB_TOKEN}@github.com/kiara2-2/bluesky-sentiment-analysis.git

# Commit and push updates to the repo
git add data/sentiment.json
git commit -m "Auto-update $(date)" || echo "No changes to commit"
git push

echo "[$(date)] ✅ Done!" >> sentiment.log
