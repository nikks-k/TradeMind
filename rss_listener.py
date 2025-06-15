# rss_listener.py
# ──────────────────────────────────────────────────────────────────────────
# Служба-слушатель: 1) читает RSS-ленты, 2) сохраняет статьи в Postgres,
# 3) вызывает LLM ровно ОДИН раз на каждую новую статью и кладёт результат
#    (asset/sentiment/confidence) в news_llm_cache.
#
import asyncio, uuid, json, re, logging, time, random, feedparser, requests, os
from datetime import datetime
from bs4 import BeautifulSoup
from readability import Document
from sqlalchemy import select
from database import AsyncSession, engine, Base
from models    import RssPost, NewsLLMCache
from utils.text import squeeze_text
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────── LLM ВЫЗОВ ──────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL   = "google/gemini-2.5-flash-preview-05-20"
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

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
    logging.debug("LLM REQUEST PAYLOAD: %s",
                  json.dumps(payload, ensure_ascii=False))

    delay = 2.0
    for _ in range(retries):
        try:
            r = requests.post(BASE_URL, headers=headers,
                              json=payload, timeout=30)
            if r.status_code == 429:
                raise requests.HTTPError("429", response=r)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except requests.HTTPError as exc:
            if not (exc.response and exc.response.status_code == 429):
                raise
            time.sleep(delay * random.uniform(0.8, 1.2))
            delay *= 2
    return '[{"asset":"general","sentiment":"neutral","confidence":0.0,"reason":"rate_limited"}]'

# ─────────────────────── ПАРАМЕТРЫ СЛУШАТЕЛЯ ──────────────────────────────
RSS_URLS        = [
    "https://decrypt.co/feed",
    "https://www.theblock.co/rss.xml",
    "https://blockworks.co/feed",
    "https://bitcoinmagazine.com/.rss/full",
]
MAX_FEED_ITEMS  = 20          # статей из каждой ленты за проход
FETCH_INTERVAL  = 300         # секунд между проходами (5 мин)
MAX_TOKENS_LLM  = 800         # squeeze_text режет до этого предела


# ─────────────────────── ФУНКЦИИ РАБОТЫ С БД ──────────────────────────────
async def init_db() -> None:
    """Создаём таблицы, если их ещё нет (один раз при старте)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ─────────────────────── ГЛАВНЫЙ ЦИКЛ СЛУШАТЕЛЯ ───────────────────────────
async def listener_loop() -> None:
    await init_db()
    while True:
        await fetch_all_feeds()
        await asyncio.sleep(FETCH_INTERVAL)

async def fetch_all_feeds():
    tasks = [process_feed(url) for url in RSS_URLS]
    await asyncio.gather(*tasks)

async def process_feed(feed_url: str):
    async with AsyncSession() as session:
        parsed = feedparser.parse(feed_url)

        for entry in parsed.entries[:MAX_FEED_ITEMS]:
            uid = uuid.uuid5(uuid.NAMESPACE_URL, entry.link)

            async with session.begin():                 # одна транзакция / статья
                if await session.get(RssPost, uid):
                    continue

                post = await save_post(uid, feed_url, entry, session)
                await classify_and_cache(post, session)

# ─────────────────────── СОХРАНЯЕМ СТАТЬЮ В РSS_POSTS ─────────────────────
async def save_post(uid, feed_url, entry, session) -> RssPost:

    title = entry.title
    raw_summary = entry.get("summary", "")
    clean_summary = BeautifulSoup(raw_summary, "html.parser").get_text(strip=True)

    # Пытаемся достать полный текст статьи
    full_text = clean_summary
    try:
        resp = requests.get(entry.link, headers={"User-Agent": "Mozilla/5.0"},
                            timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(Document(resp.text).summary(), "html.parser")
        paras = [p.get_text(strip=True) for p in soup.find_all("p")
                 if len(p.get_text(strip=True)) > 50]
        if paras:
            full_text = "\n".join(paras)
    except Exception as ex:
        logger.debug("Fetch article failed %s: %s", entry.link, ex)

    post = RssPost(
        post_id   = uid,
        feed_url  = feed_url,
        title     = title,
        link      = entry.link,
        content   = full_text,
        published = datetime(*entry.published_parsed[:6])
                   if entry.get("published_parsed") else datetime.utcnow()
    )
    session.add(post)
    await session.flush()
    return post


# ─────────────────────── КЛАССИФИКАЦИЯ LLM + КЭШ ──────────────────────────
async def classify_and_cache(post: RssPost, session) -> None:
    user_text = f"{post.title}\n\n" + squeeze_text(post.content, MAX_TOKENS_LLM)
    raw = _call_llm(user_text)

    try:
        parsed = json.loads(re.search(r"\[.*\]", raw, re.S).group(0))
    except Exception:
        parsed = [{"asset": "general", "sentiment": "neutral",
                   "confidence": 0.0, "reason": "parse_error"}]
    
    for item in parsed:
        s = item.get("sentiment", "").lower()
        if s == "positive":
            item["sentiment"] = "bullish"
        elif s == "negative":
            item["sentiment"] = "bearish"

    best = max(parsed, key=lambda x: x.get("confidence", 0.5))

    cache_row = NewsLLMCache(
        post_id    = post.post_id,
        asset      = best.get("asset", "general"),
        sentiment  = best.get("sentiment", "neutral"),
        confidence = float(best.get("confidence", 0.5)),
        reason     = best.get("reason", "")[:300],
        summary_md = user_text,
        llm_raw    = best,
    )

    session.add(cache_row)
    await session.flush()      
    logger.info("LLM cached: %s → %s %.2f",
                cache_row.asset, cache_row.sentiment, cache_row.confidence)
# ─────────────────────── ТОЧКА ВХОДА ───────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(listener_loop())
