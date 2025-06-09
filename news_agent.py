import os, re, json, time, random, feedparser, requests
from typing import Dict, Generator
from bs4 import BeautifulSoup
from readability import Document

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL    = "mistralai/mistral-7b-instruct-v0.2"

RSS_URLS = [
    # "https://coindesk.com/arc/outboundfeeds/rss/",
    # "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://www.theblock.co/rss.xml"
]

MAX_NEWS = 1              # ← частота LLM-вызовов

# ───────────────── helpers ───────────────────────
# def fetch_news() -> Generator[str, None, None]:
#     for url in RSS_URLS:
#         parsed = feedparser.parse(url)
#         print(f"\n--- Parsing feed: {url} ---")
#         for e in parsed.entries[:10]:
#             print("Title:  ", e.title)
#             print("Summary:", e.summary, "\n")
#             yield f"{e.title} — {e.summary}"

# ───────────────── парсинг новостей ───────────────────────
def fetch_news() -> Generator[str, None, None]:
    for url in RSS_URLS:
        parsed = feedparser.parse(url)
        print(f"\n--- Parsing feed: {url} ---")
        for entry in parsed.entries[:MAX_NEWS]:
            title = entry.title
            print("Title:  ", title)

            # 1) Оригинальное summary
            raw_summary = entry.get("summary", "")
            clean_summary = BeautifulSoup(raw_summary, "html.parser").get_text(strip=True)
            print("Summary:", clean_summary, "\n")

            # 2) Попытка получить полный текст статьи
            full_text = clean_summary
            try:
                resp = requests.get(entry.link, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                resp.raise_for_status()  # если 403/404 → HTTPError
                doc = Document(resp.text)
                main_html = doc.summary()
                soup = BeautifulSoup(main_html, "html.parser")
                paras = soup.find_all("p")

                # 3) Фильтрация шумовых параграфов
                filtered = []
                for p in paras:
                    t = p.get_text(strip=True)
                    if len(t) < 50: continue
                    if re.match(r"^[\s\d\$\.\,]+$", t): continue
                    filtered.append(t)

                if filtered:
                    full_text = "\n".join(filtered)

            except requests.HTTPError as he:
                logging.warning("HTTP error %s fetching %s — using summary", he, entry.link)
            except Exception as ex:
                logging.warning("Error fetching/parsing %s — using summary\n%s", entry.link, ex)

            # 4) Сниппет для проверки
            snippet = full_text[:200] + ("…" if len(full_text) > 200 else "")
            print("Content snippet:\n", snippet, "\n")

            yield f"{title}\n\n{full_text}"

def _call_llm(text: str, retries: int = 5) -> str:
    
    SYSTEM = (
    "Ты крипто-аналитик. На вход тебе даётся новость. "
    "Верни JSON-массив вида "
    "[{"
    '"asset":"BTC|ETH|SOL|DOGE|...|general",'
    '"sentiment":"bullish|bearish|neutral",'
    '"confidence":0.0-1.0,'
    '"reason":"краткое пояснение"'
    "}, …]. "
    "Если новость никак не влияет, верни пустой массив."
    )

    payload = {
        "model": MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": text},
        ],
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "crypto-multi-agent-mvp",
    }
    logging.debug("LLM REQUEST PAYLOAD: %s", json.dumps(payload, ensure_ascii=False))
    
    delay = 2.0
    for _ in range(retries):
        try:
            r = requests.post(BASE_URL, headers=headers, json=payload, timeout=30)
            if r.status_code == 429:
                raise requests.HTTPError("429", response=r)
            r.raise_for_status()
            logging.debug("LLM RESPONSE TEXT: %s", r.text)
            logging.debug("LLM CONTENT: %s", r.json()["choices"][0]["message"]["content"])
            return r.json()["choices"][0]["message"]["content"]
        except requests.HTTPError as e:
            if not (e.response and e.response.status_code == 429):
                raise
            time.sleep(delay * random.uniform(0.8, 1.2))
            delay *= 2
    return '{"asset":"general","sentiment":"neutral","raw":"rate_limited"}'

def _robust_json(raw: str) -> Dict:
    m = re.search(r"\{.*?\}", raw, flags=re.S)
    if not m:
        return {"asset": "general", "sentiment": "neutral", "raw": raw[:200]}
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"asset": "general", "sentiment": "neutral", "raw": raw[:200]}
    if "asset" not in obj or "sentiment" not in obj:
        obj = {"asset": "general", "sentiment": "neutral", "raw": obj}
    return obj

def classify_article(text: str) -> Dict:
    return _robust_json(_call_llm(text).strip())

def news_signals():
    for i, article in enumerate(fetch_news()):
        if i >= MAX_NEWS:
            break
        yield classify_article(article)

if __name__ == "__main__":
    for signal in news_signals():
        print("Signal:", signal)
