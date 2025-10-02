import os
import json
import requests
from datetime import datetime, timedelta
import time
import random

BSKY_HANDLE = os.environ["BSKY_HANDLE"]
BSKY_PASS = os.environ["BSKY_APP_PASSWORD"]
HF_TOKEN = os.environ["HF_TOKEN"]

# Configuration for balanced data fetching
POPULAR_ACCOUNTS = [
    "jay.bsky.social",
    "bsky.app", 
    "atproto.com",
    "paul.bsky.social",
    "alice.bsky.social"
]

SEARCH_KEYWORDS = [
    "#review", "#bookreview", "#moviereview", "#gamereviews",
    "#recommendation", "#opinion", "#thoughts"
]

MAX_POSTS_PER_SOURCE = 15  # Balanced to avoid overwhelming APIs
BATCH_SIZE = 20  # HuggingFace API batch processing limit
REQUEST_DELAY = 1.0  # Rate limiting delay between requests

def login_to_bluesky():
    """Login to Bluesky and return access token"""
    print("🔐 Logging into Bluesky...")
    resp = requests.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={"identifier": BSKY_HANDLE, "password": BSKY_PASS},
    )
    print(f"🔍 Login HTTP status: {resp.status_code}")
    
    try:
        sess = resp.json()
        if "accessJwt" not in sess:
            print("❌ Login failed:", sess)
            exit(1)
        print(f"✅ Logged in as {sess.get('handle', BSKY_HANDLE)}")
        return sess["accessJwt"]
    except ValueError:
        print("❌ Failed to parse login response:", resp.text)
        exit(1)

def fetch_posts_from_account(token, repo, limit=15):
    """Fetch posts from a specific account"""
    headers = {"Authorization": f"Bearer {token}"}
    try:
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
                if len(text) > 20 and len(text) < 500:  # Filter reasonable post lengths
                    posts.append({
                        "text": text,
                        "handle": repo,
                        "timestamp": record.get("value", {}).get("createdAt", datetime.utcnow().isoformat()),
                        "uri": record.get("uri", "")
                    })
            return posts
        else:
            print(f"⚠️ Failed to fetch from {repo}: {resp.status_code}")
            return []
    except Exception as e:
        print(f"⚠️ Error fetching from {repo}: {e}")
        return []

def search_posts_by_keyword(token, keyword, limit=10):
    """Search posts by keyword (if search API available)"""
    # Note: Bluesky's search API might have different endpoints
    # This is a placeholder - adjust based on actual Bluesky search API
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # Using feed search as fallback approach
        resp = requests.get(
            "https://bsky.social/xrpc/app.bsky.feed.searchPosts",
            headers=headers,
            params={"q": keyword, "limit": limit},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get("posts", [])
    except Exception as e:
        print(f"⚠️ Search for '{keyword}' failed: {e}")
    return []

def categorize_post(text):
    """Categorize posts based on content keywords"""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ["movie", "film", "tv", "series", "show", "cinema"]):
        return "Movie/TV"
    elif any(word in text_lower for word in ["book", "novel", "author", "read", "literature"]):
        return "Book"
    elif any(word in text_lower for word in ["game", "gaming", "play", "xbox", "playstation", "nintendo"]):
        return "Game"
    elif any(word in text_lower for word in ["music", "song", "album", "artist", "band", "listen"]):
        return "Music"
    else:
        return "Other"

def analyze_sentiment_batch(texts, max_retries=3):
    """Analyze sentiment for a batch of texts using HuggingFace"""
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest",
                headers={"Authorization": f"Bearer {HF_TOKEN}"},
                json={"inputs": texts},
                timeout=30
            )
            
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 503:
                print(f"🔄 Model loading, attempt {attempt + 1}/{max_retries}...")
                time.sleep(10)  # Wait for model to load
            else:
                print(f"⚠️ Sentiment API error: {resp.status_code}")
                time.sleep(2)
                
        except Exception as e:
            print(f"⚠️ Sentiment analysis error: {e}")
            time.sleep(2)
    
    # Return neutral sentiment as fallback
    return [{"label": "LABEL_1", "score": 0.5}] * len(texts)

def collect_posts(token):
    """Collect posts from multiple sources"""
    print("📊 Collecting posts from multiple sources...")
    all_posts = []
    
    # Fetch from popular accounts
    for account in POPULAR_ACCOUNTS:
        print(f"📥 Fetching from {account}...")
        posts = fetch_posts_from_account(token, account, MAX_POSTS_PER_SOURCE)
        all_posts.extend(posts)
        time.sleep(REQUEST_DELAY)  # Rate limiting
    
    # Search by keywords (if available)
    for keyword in SEARCH_KEYWORDS[:3]:  # Limit keyword searches
        print(f"🔍 Searching for {keyword}...")
        posts = search_posts_by_keyword(token, keyword, 5)
        all_posts.extend(posts)
        time.sleep(REQUEST_DELAY)
    
    print(f"📋 Collected {len(all_posts)} posts total")
    return all_posts

def process_and_analyze():
    """Main processing function"""
    print("🚀 Starting large-scale sentiment analysis...")
    
    # Login
    token = login_to_bluesky()
    
    # Collect posts
    new_posts = collect_posts(token)
    
    if not new_posts:
        print("❌ No posts collected")
        return
    
    # Load existing data
    existing_data = {}
    if os.path.exists("data/sentiment.json"):
        with open("data/sentiment.json", "r") as f:
            try:
                existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = {}
    
    existing_posts = existing_data.get("posts", [])
    existing_uris = set(p.get("uri", p["text"]) for p in existing_posts)
    
    # Filter new posts (avoid duplicates)
    unique_posts = []
    for post in new_posts:
        identifier = post.get("uri", post["text"])
        if identifier not in existing_uris:
            unique_posts.append(post)
    
    if not unique_posts:
        print("ℹ️ No new posts to analyze")
        return
    
    print(f"🔬 Analyzing {len(unique_posts)} new posts...")
    
    # Process posts in batches for sentiment analysis
    processed_posts = []
    label_map = {"LABEL_0": "Negative", "LABEL_1": "Neutral", "LABEL_2": "Positive"}
    
    for i in range(0, len(unique_posts), BATCH_SIZE):
        batch = unique_posts[i:i + BATCH_SIZE]
        texts = [post["text"] for post in batch]
        
        print(f"📊 Analyzing batch {i//BATCH_SIZE + 1}/{(len(unique_posts)-1)//BATCH_SIZE + 1}...")
        sentiment_results = analyze_sentiment_batch(texts)
        
        for j, post in enumerate(batch):
            if j < len(sentiment_results):
                result = sentiment_results[j]
                if isinstance(result, list) and len(result) > 0:
                    result = result[0]  # Take top prediction
                
                label = label_map.get(result.get("label", "LABEL_1"), "Neutral")
                score = result.get("score", 0.5)
                
                processed_posts.append({
                    "text": post["text"][:200] + "..." if len(post["text"]) > 200 else post["text"],
                    "handle": post["handle"],
                    "category": categorize_post(post["text"]),
                    "label": label,
                    "score": round(score, 3),
                    "timestamp": post.get("timestamp", datetime.utcnow().isoformat() + "Z"),
                    "uri": post.get("uri", "")
                })
        
        time.sleep(1)  # Rate limiting between batches
    
    # Combine with existing data
    all_posts = existing_posts + processed_posts
    
    # Keep only recent posts (last 1000 to manage size)
    all_posts = sorted(all_posts, key=lambda x: x.get("timestamp", ""), reverse=True)[:1000]
    
    # Calculate sentiment counts dynamically with lowercase keys to match dashboard
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
    category_counts = {}
    
    for post in all_posts:
        sentiment_counts[post["label"].lower()] += 1
        category = post.get("category", "Other")
        category_counts[category] = category_counts.get(category, 0) + 1
    
    # Prepare final data structure
    final_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_posts": len(all_posts),
        "new_posts_added": len(processed_posts),
        "sentiment": sentiment_counts,
        "categories": category_counts,
        "posts": all_posts
    }
    
    # Save data
    os.makedirs("data", exist_ok=True)
    with open("data/sentiment.json", "w") as f:
        json.dump(final_data, f, indent=2)
    
    print("✅ Analysis complete!")
    print(f"📈 Total posts: {len(all_posts)} (added {len(processed_posts)} new)")
    print(f"😊 Positive: {sentiment_counts['positive']}")
    print(f"😐 Neutral: {sentiment_counts['neutral']}")
    print(f"😞 Negative: {sentiment_counts['negative']}")

if __name__ == "__main__":
    process_and_analyze()
