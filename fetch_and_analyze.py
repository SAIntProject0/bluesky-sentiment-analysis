import os, json, requests
from datetime import datetime

BSKY_HANDLE = os.environ["BSKY_HANDLE"]
BSKY_PASS = os.environ["BSKY_APP_PASSWORD"]
HF_TOKEN = os.environ["HF_TOKEN"]

# Login
sess = requests.post("https://bsky.social/xrpc/com.atproto.server.createSession", json={
    "identifier": BSKY_HANDLE,
    "password": BSKY_PASS,
}).json()
token = sess["accessJwt"]

# Get posts from 1 popular account
headers = {"Authorization": f"Bearer {token}"}
posts_resp = requests.get(
    "https://bsky.social/xrpc/com.atproto.repo.listRecords",
    headers=headers,
    params={"repo": "jay.bsky.social", "collection": "app.bsky.feed.post", "limit": 10}
)
texts = [r["value"]["text"] for r in posts_resp.json()["records"] if "text" in r["value"] and len(r["value"]["text"]) > 10][:8]

# Analyze
hf_resp = requests.post(
    "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest",
    headers={"Authorization": f"Bearer {HF_TOKEN}"},
    json={"inputs": texts}
).json()

# Process
label_map = {"LABEL_0": "Negative", "LABEL_1": "Neutral", "LABEL_2": "Positive"}
results = []
counts = {"Positive": 0, "Neutral": 0, "Negative": 0}

for i, text in enumerate(texts):
    pred = hf_resp[i][0]
    label = label_map[pred["label"]]
    counts[label] += 1
    results.append({
        "text": text[:100] + "..." if len(text) > 100 else text,
        "handle": "jay.bsky.social",
        "label": label,
        "score": round(pred["score"], 3)
    })

# Save
with open("data/sentiment.json", "w") as f:
    json.dump({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "positive": counts["Positive"],
        "neutral": counts["Neutral"],
        "negative": counts["Negative"],
        "posts": results
    }, f, indent=2)

print("✅ Analysis complete. Data saved.")
