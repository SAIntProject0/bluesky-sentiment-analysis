import os
import json
import requests
from datetime import datetime, timedelta
import time

# Your environment variables
BSKY_HANDLE = os.environ["BSKY_HANDLE"]
BSKY_PASS = os.environ["BSKY_APP_PASSWORD"]
HF_TOKEN = os.environ["HF_TOKEN"]

# Configuration
POPULAR_ACCOUNTS = [
    "jay.bsky.social", "bsky.app", "atproto.com", "paul.bsky.social", "alice.bsky.social"
]
SEARCH_KEYWORDS = ["#review", "#bookreview", "#moviereview", "#gamereviews"]
MAX_POSTS_PER_SOURCE = 15
BATCH_SIZE = 20
REQUEST_DELAY = 1

def login_to_bluesky():
    print("🔐 Logging into Bluesky...")
    resp = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={"identifier": BSKY_HANDLE, "password": BSKY_PASS},
    )
    print(f"🔍 Login status code: {resp.status_code}")
    try:
        sess = resp.json()
        if "accessJwt" not in sess:
            print("❌ Login failed:", sess)
            exit(1)
        return sess["accessJwt"]
    except:
        print("❌ Failed to parse login response")
        exit(1)

def fetch_posts_from_account(token, repo, limit=15):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        "https://bsky.social/xrpc/com.atproto.repo.listRecords",
        headers=headers,
        params={"repo": repo, "collection": "app.bsky.feed.post", "limit": limit},
        timeout=10
    )
    if resp.status_code == 200:
        records = resp.json().get("records", [])
        posts = []
        for record in records:
            text = record.get("value", {}).get("text", "")
            if 20 < len(text) < 500:
                posts.append({
                    "text": text,
                    "handle": repo,
                    "timestamp": record.get("value", {}).get("createdAt", datetime.utcnow().isoformat()),
                    "uri": record.get("uri", "")
                })
        return posts
    else:
        return []

def search_posts_by_keyword(token, keyword, limit=10):
    # Placeholder, adjust based on actual Bluesky search API
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        "https://bsky.social/xrpc/app.bsky.feed.searchPosts",
        headers=headers,
        params={"q": keyword, "limit": limit},
        timeout=10
    )
    if resp.status_code == 200:
        return resp.json().get("posts", [])
    return []

def categorize_post(text):
    t = text.lower()
    if any(w in t for w in ["movie", "film", "tv", "series", "show", "cinema"]):
        return "Movie/TV"
    elif any(w in t for w in ["book", "novel", "author", "read", "literature"]):
        return "Book"
    elif any(w in t for w in ["game", "gaming", "play", "xbox", "nintendo"]):
        return "Game"
    elif any(w in t for w in ["music", "song", "album", "artist", "band", "listen"]):
        return "Music"
    else:
        return "Other"

def analyze_sentiment_batch(texts, max_retries=3):
    for _ in range(max_retries):
        try:
            resp = requests.post(
                "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest",
                headers={"Authorization": f"Bearer {HF_TOKEN}"},
                json={"inputs": texts},
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()
            time.sleep(2)
        except:
            time.sleep(2)
    return [{"label": "LABEL_1", "score": 0.5}] * len(texts)

def collect_posts(token):
    print("📊 Collecting posts...")
    all_posts = []
    for account in POPULAR_ACCOUNTS:
        print(f"📥 {account}")
        all_posts.extend(fetch_posts_from_account(token, account, MAX_POSTS_PER_SOURCE))
        time.sleep(REQUEST_DELAY)
    for kw in SEARCH_KEYWORDS[:3]:
        print(f"🔍 {kw}")
        all_posts.extend(search_posts_by_keyword(token, kw, 5))
        time.sleep(REQUEST_DELAY)
    print(f"Collected {len(all_posts)} posts")
    return all_posts

def main():
    print("🚀 Starting analysis...")
    token = login_to_bluesky()
    new_posts = collect_posts(token)
    if not new_posts:
        print("No new posts.")
        return
    if os.path.exists("data/sentiment.json"):
        with open("data/sentiment.json", "r") as f:
            try:
                data = json.load(f)
            except:
                data = {}
    else:
        data = {}
    existing_posts = data.get("posts", [])
    existing_uris = set([p.get("uri", p["text"]) for p in existing_posts])
    unique_posts = [p for p in new_posts if p.get("uri", p["text"]) not in existing_uris]
    if not unique_posts:
        print("No new unique posts.")
        return
    label_map = {"LABEL_0": "Negative", "LABEL_1": "Neutral", "LABEL_2": "Positive"}
    processed = []
    for i, post in enumerate(unique_posts):
        result = analyze_sentiment_batch([post["text"]])[0][0]
        label = label_map.get(result.get("label", "LABEL_1"), "Neutral")
        score = result.get("score", 0.5)
        processed.append({
            "text": post["text"],
            "handle": post["handle"],
            "category": categorize_post(post["text"]),
            "label": label,
            "score": round(score, 3),
            "timestamp": post.get("timestamp", datetime.utcnow().isoformat()),
            "uri": post.get("uri", "")
        })
    all_posts = existing_posts + processed
    # Limit size
    all_posts = sorted(all_posts, key=lambda p: p.get("timestamp", ""), reverse=True)[:1000]
    # Count sentiment
    counts = {"Positive":0, "Neutral":0, "Negative":0}
    for p in all_posts:
        counts[p["label"]] += 1
    data_out = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "positive": counts["Positive"],
        "neutral": counts["Neutral"],
        "negative": counts["Negative"],
        "posts": all_posts
    }
    # Save
    os.makedirs("data", exist_ok=True)
    with open("data/sentiment.json", "w") as f:
        json.dump(data_out, f, indent=2)

if __name__ == "__main__":
    main()
