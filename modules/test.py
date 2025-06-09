import json
import feedparser

def load_feed_config(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config

def fetch_feed(feed_url):
    parsed = feedparser.parse(feed_url)
    print(f"[TEST] Parsed {feed_url}: bozo={parsed.bozo}, entries={len(parsed.entries)}")
    return parsed

def extract_items(parsed_feed):
    return [
        {
            "title": e.get("title", "").strip(),
            "summary": e.get("summary", e.get("description", "")).strip(),
            "link": e.get("link", "").strip(),
            "published": e.get("published", "").strip()
        }
        for e in parsed_feed.entries
    ]

if __name__ == "__main__":
    feeds = load_feed_config("modules/news.json")
    print("[TEST] Feeds loaded:", feeds)
    for name, url in feeds.items():
        parsed = fetch_feed(url)
        items = extract_items(parsed)
        print(f"[TEST] Источник {name} → записей: {len(items)}")
        if items:
            print("   Первые две записи:")
            for it in items[:2]:
                print("     *", it["title"], "|", it["published"])
