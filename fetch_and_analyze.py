import os
import json
import requests
from datetime import datetime

BSKY_HANDLE = os.environ["BSKY_HANDLE"]
BSKY_PASS = os.environ["BSKY_APP_PASSWORD"]
HF_TOKEN = os.environ["HF_TOKEN"]

# Login
resp = requests.post(
    "https://bsky.social/xrpc/com.atproto.server.createSession",
    json={"identifier": BSKY_HANDLE, "password": BSKY_PASS},
)
print("🔍 Login HTTP status:", resp.status_code)

try:
    sess = resp.json()
    print("🔍 Login response JSON:", sess)
except ValueError:
    print("❌ Failed to parse JSON. Response text:", resp.text)
    exit(1)

if "accessJwt" not in sess:
    print("❌ ‘accessJwt’ missing. Full response:", sess)
    exit(1)

token = sess["accessJwt"]
print(f"✅ Logged in as {BSKY_HANDLE}")

# Get posts from 1 popular account
headers = {"Authorization": f"Bearer {token}"}
posts_resp = requests.get(
    "https://bsky.social/xrpc/com.atproto.repo.listRecords",
    headers=headers,
    params={"repo": "jay.bsky.social", "collection": "app.bsky.feed.post", "limit": 10},
)
texts = [r["value"]["text"] for r in posts_resp.json()["records"] if "text" in r["value"] and len(r["value"]["text"]) > 10][:8]

# Analyze with HuggingFace sentiment model
hf_resp = requests.post(
    "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest",
    headers={"Authorization": f"Bearer {HF_TOKEN}"},
    json={"inputs": texts},
).json()

# Process new results
label_map = {"LABEL_0": "Negative", "LABEL_1": "Neutral", "LABEL_2": "Positive"}
results = []
for i, text in enumerate(texts):
    pred = hf_resp[i][0]
    label = label_map[pred["label"]]
    results.append({
        "text": text[:100] + "..." if len(text) > 100 else text,
        "handle": "jay.bsky.social",
        "label": label,
        "score": round(pred["score"], 3),
    })

# Load existing data if present to preserve old results
existing_data = {}
if os.path.exists("data/sentiment.json"):
    with open("data/sentiment.json", "r") as f:
        try:
            existing_data = json.load(f)
        except json.JSONDecodeError:
            existing_data = {}

existing_posts = existing_data.get("posts", [])
existing_texts = set(p["text"] for p in existing_posts)

# Append only new posts
for post in results:
    if post["text"] not in existing_texts:
        existing_posts.append(post)

# Recalculate counts over combined data
counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
for post in existing_posts:
    counts[post["label"]] += 1

# Prepare combined data to save
updated_data = {
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "positive": counts["Positive"],
    "neutral": counts["Neutral"],
    "negative": counts["Negative"],
    "posts": existing_posts,
}

# Ensure data/ directory exists
os.makedirs("data", exist_ok=True)

# Save combined data
with open("data/sentiment.json", "w") as f:
    json.dump(updated_data, f, indent=2)

print("✅ Analysis complete. Data saved.")
