import os
import json
import requests
from datetime import datetime, timedelta, timezone

# Use this instead of datetime.utcnow()
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

def get_post_id(post):
    return post.get("uri") or post.get("text", "")[:100]

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
                    "timestamp": record.get("value", {}).get("createdAt", datetime.now(timezone.utc).isoformat()),
                    "uri": record.get("uri", "")
                })
        return posts
    else:
        return []

def search_posts_by_keyword(token, keyword, limit=10):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        "https://bsky.social/xrpc/app.bsky.feed.searchPosts",
        headers=headers,
        params={"q": keyword, "limit": limit},
        timeout=10
    )
    if resp.status_code == 200:
        feed = resp.json().get("feed", [])
        posts = []
        for item in feed:
            post_obj = item.get("post", {})
            record = post_obj.get("record", {})
            text = record.get("text", "").strip()
            uri = post_obj.get("uri", "")
            author = post_obj.get("author", {})
            handle = author.get("handle", "unknown.bsky.social")
            created_at = record.get("createdAt", datetime.utcnow().isoformat())
            
            if 20 < len(text) < 500:
                posts.append({
                    "text": text,
                    "handle": handle,
                    "timestamp": created_at,
                    "uri": uri
                })
        return posts
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
    existing_uris = set(get_post_id(p) for p in existing_posts)
    unique_posts = [p for p in new_posts if get_post_id(p) not in existing_uris]

    if not unique_posts:
        print("No new unique posts.")
        return

    label_map = {"negative": "Negative", "neutral": "Neutral", "positive": "Positive"}

    processed = []
    for i, post in enumerate(unique_posts):
        # Ensure post has "text"
        if "text" not in post:
            print(f"⚠️ Skipping post without text: {post.get('uri', 'no uri')}")
            continue
        results = analyze_sentiment_batch([post["text"]])
        # HF returns: [[{label, score}]] for batch of 1
        if isinstance(results, list) and len(results) > 0:
            if isinstance(results[0], list) and len(results[0]) > 0:
                pred = results[0][0]  # ← This is the dict
            else:
                pred = results[0]
        else:
            pred = {"label": "neutral", "score": 0.5}
        
        label = label_map.get(pred.get("label", "neutral"), "Neutral")
        score = pred.get("score", 0.5)
        processed.append({
            "text": post["text"],
            "handle": post.get("handle", "unknown.bsky.social"),
            "category": categorize_post(post["text"]),
            "label": label,
            "score": round(score, 3),
            "timestamp": post.get("timestamp", datetime.utcnow().isoformat()),
            "uri": post.get("uri", "")
        })

    all_posts = existing_posts + processed
    all_posts = sorted(all_posts, key=lambda p: p.get("timestamp", ""), reverse=True)[:1000]

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

    os.makedirs("data", exist_ok=True)
    with open("data/sentiment.json", "w") as f:
        json.dump(data_out, f, indent=2)

if __name__ == "__main__":
    main()
