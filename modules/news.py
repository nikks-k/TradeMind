# import os
# import json
# import time
# import requests
# import feedparser
# from datetime import datetime, timezone


# OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# if not OPENROUTER_API_KEY:
#     raise RuntimeError("Не найден ключ OPENROUTER_API_KEY в переменных окружения.")

# HERE = os.path.dirname(os.path.abspath(__file__))
# NEWS_JSON_PATH = os.path.join(HERE, "news.json")

# print(HERE)
# print(NEWS_JSON_PATH)

# # --------------------------------------------------------------------
# # 1) Загрузка списка RSS-каналов
# # --------------------------------------------------------------------
# def load_news_sources(json_path: str) -> dict:
#     """
#     Загружает JSON вида:
#     {
#        "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss",
#        "cointelegraph": "https://cointelegraph.com/rss",
#        ...
#     }
#     """
#     with open(json_path, "r", encoding="utf-8") as f:
#         data = json.load(f)
#     return data

# # --------------------------------------------------------------------
# # 2) Парсинг RSS-ленты через feedparser
# # --------------------------------------------------------------------
# def fetch_feed_entries(source_name: str, url: str) -> list[dict]:
#     """
#     Читает RSS-ленту и возвращает список словарей вида:
#       {
#          "source": "coindesk",
#          "title": "Заголовок статьи",
#          "link": "https://ссылка-на-статью",
#          "published": "Wed, 02 Jun 2025 15:23:00 GMT",
#          "summary": "Краткий текст новости"
#       }
#     """
#     feed = feedparser.parse(url)
#     entries = []
#     for entry in feed.entries:
#         title     = entry.get("title", "").strip()
#         link      = entry.get("link", "").strip()
#         published = entry.get("published", entry.get("updated", "")).strip()
#         summary   = entry.get("summary", entry.get("description", "")).strip()
#         entries.append({
#             "source":    source_name,
#             "title":     title,
#             "link":      link,
#             "published": published,
#             "summary":   summary
#         })
#     return entries

# # sources = load_news_sources(NEWS_JSON_PATH)
# # if not sources:
# #     print("Список RSS-каналов пуст.")
# # for source_name, url in sources.items():
# #     try:
# #         entries = fetch_feed_entries(source_name, url)
# #         print(entries)
# #     except Exception as e:
# #         print(f"Ошибка при получении RSS из {source_name}: {e}")

# def call_llm(prompt: str,
#              model: str = "google/gemini-2.5-flash-preview-05-20:thinking"
#             ) -> str:
#     url = "https://openrouter.ai/api/v1/chat/completions"

#     system_message = {
#         "role": "user",
#         "content": [
#             {
#                 "type": "text",
#                 "text": (
#                     "Ты — аналитик, специализирующийся на криптовалютах и финансовых рынках. "
#                 )
#             }
#         ]
#     }
#     user_message = {
#         "role": "user",
#         "content": [
#             {
#                 "type": "text",
#                 "text": prompt
#             }
#         ]
#     }

#     payload = {
#         "model":    model,
#         "messages": [system_message, user_message],
#         "temperature":       0.0,
#     }

#     headers = {
#         "Authorization": f"Bearer {OPENROUTER_API_KEY}",
#         "Content-Type": "application/json"
#     }

import os
import json
import requests
import feedparser

# ----------------------------------------------------------------------
# 1. Чтение API-ключа (обязательно). SITE_URL и SITE_NAME — опционально.
# ----------------------------------------------------------------------
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise RuntimeError("Не задана переменная окружения OPENROUTER_API_KEY")
# ----------------------------------------------------------------------
# 2. Загрузка фидов из JSON-объекта { source_name: feed_url, … }
# ----------------------------------------------------------------------
def load_feed_config(json_path):
    """
    Загружает файл feeds.json, печатает его содержимое и возвращает словарь { source_name: feed_url }.
    """
    print(f"[DEBUG] Попытка загрузить feeds из файла: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    print(f"[DEBUG] Содержимое конфигурации (feeds.json):")
    print(json.dumps(config, ensure_ascii=False, indent=2))
    if not isinstance(config, dict):
        raise ValueError("Ожидался JSON-объект {source_name: feed_url, …} в feeds.json")
    return config

# ----------------------------------------------------------------------
# 3. Парсинг RSS-фида через feedparser (с подстраховкой User-Agent)
# ----------------------------------------------------------------------
def fetch_feed(feed_url):
    """
    Пытается спарсить RSS-фид через feedparser.parse.
    Если parsed.bozo=True или parsed.entries пуст, делает запрос через requests + User-Agent и парсит заново.
    Возвращает объект FeedParserDict.
    """
    print(f"[DEBUG] => Запрос к RSS-фиду: {feed_url}")
    parsed = feedparser.parse(feed_url)
    print(f"[DEBUG]    feedparser.parse: bozo={parsed.bozo}, entries={len(parsed.entries)}")
    if parsed.bozo or len(parsed.entries) == 0:
        print(f"[DEBUG]    Попытка скачать фид через requests с User-Agent")
        try:
            resp = requests.get(feed_url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
            print(f"[DEBUG]    После requests: bozo={parsed.bozo}, entries={len(parsed.entries)}")
        except Exception as e:
            print(f"[DEBUG]    Ошибка при requests: {e}")
    return parsed

# ----------------------------------------------------------------------
# 4. Извлечение списка новостей (с выводом деталей каждого элемента)
# ----------------------------------------------------------------------
def extract_items(parsed_feed, source_name):
    """
    Для каждого entry в parsed_feed.entries:
      1) Печатает ключи entry и содержимое полей content/summary_detail/description (первые 200 символов).
      2) По приоритету берёт summary из content → summary_detail → summary → description.
      3) Печатает первые 100 символов итогового summary.
    Возвращает список { "title", "summary", "link", "published" }.
    """
    items = []
    print(f"[DEBUG]   Извлечение элементов из parsed_feed для источника '{source_name}'")
    for idx, entry in enumerate(parsed_feed.entries, start=1):
        print(f"[DEBUG]    ENTRY #{idx} ключи: {list(entry.keys())}")

        # 1. Если есть content, покажем его начало
        if "content" in entry and entry["content"]:
            first_content = entry["content"][0].get("value", "")
            preview = first_content[:200] + "..." if len(first_content) > 200 else first_content
            print(f"[DEBUG]       content (первые 200 символов): {preview!r}")

        # 2. Если есть summary_detail, покажем его начало
        if "summary_detail" in entry:
            sd = entry["summary_detail"].get("value", "")
            preview = sd[:200] + "..." if len(sd) > 200 else sd
            print(f"[DEBUG]       summary_detail (первые 200 символов): {preview!r}")

        # 3. Если есть description, покажем его начало
        if "description" in entry:
            desc = entry["description"]
            preview = desc[:200] + "..." if len(desc) > 200 else desc
            print(f"[DEBUG]       description (первые 200 символов): {preview!r}")

        # Сейчас определим итоговое raw_summary по приоритетному правилу:
        raw_summary = ""
        if "content" in entry and entry["content"]:
            raw_summary = entry["content"][0].get("value", "")
        elif "summary_detail" in entry and entry["summary_detail"].get("value"):
            raw_summary = entry["summary_detail"].get("value")
        else:
            # Либо summary, либо description, либо пустая строка
            raw_summary = entry.get("summary", entry.get("description", ""))

        summary = raw_summary.strip()
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        published = entry.get("published", "").strip()

        item = {
            "title": title,
            "summary": summary,
            "link": link,
            "published": published
        }
        items.append(item)

        short_summary = (summary[:100] + "...") if len(summary) > 100 else summary
        print(f"[DEBUG]    Итоговая summary для ENTRY #{idx} (первые 100 символов): {short_summary!r}\n")

    print(f"[DEBUG]   Всего извлечено новостей: {len(items)}\n")
    return items
# ----------------------------------------------------------------------
# 5. Формирование HTTP-заголовков для OpenRouter
# ----------------------------------------------------------------------
def build_headers():
    """
    Формирует словарь заголовков:
    - Authorization: Bearer <ключ>
    - Content-Type: application/json
    - HTTP-Referer (если SITE_URL задан)
    - X-Title     (если SITE_NAME задан)
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    return headers

# ----------------------------------------------------------------------
# 6. Запрос к модели LLM (google/gemini-2.5-flash-preview-05-20:thinking)
# ----------------------------------------------------------------------
def call_llm_analyze(text):
    """
    Делает POST-запрос к OpenRouter, передавая prompt в формате:
    {
      "model": "google/gemini-2.5-flash-preview-05-20:thinking",
      "messages":[ { "role":"user", "content":[ {"type":"text","text": text} ] } ]
    }
    Возвращает строку — content ответа модели.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = build_headers()

    payload = {
        "model": "google/gemini-2.5-flash-preview-05-20:thinking",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": text
                    }
                ]
            }
        ]
    }

    # Печатаем первые 100 символов заголовков для наглядности
    print(f"[DEBUG]    HTTP-заголовки для OpenRouter: {headers}")
    # Печатаем первые 100 символов payload["messages"][0]["content"][0]["text"]
    short_payload = text[:100] + "..." if len(text) > 100 else text
    print(f"[DEBUG]    Отправляем промпт первой 100 символов: {short_payload!r}\n")

    response = requests.post(url=url, headers=headers, data=json.dumps(payload))
    try:
        response.raise_for_status()
    except Exception as e:
        print(f"[DEBUG]    Ошибка HTTP при запросе к OpenRouter: {e}")
        raise

    resp_json = response.json()
    choices = resp_json.get("choices", [])
    if not choices:
        return "Ошибка: модель вернула пустой список choices."

    content = choices[0].get("message", {}).get("content", "").strip()
    # Выводим первые 200 символов ответа для проверки
    short_content = (content[:200] + "...") if len(content) > 200 else content
    print(f"[DEBUG]    Ответ LLM (первые 200 символов): {short_content!r}\n")
    return content

# ----------------------------------------------------------------------
# 7. Формирование промпта и анализ одной новости через LLM (с печатью)
# ----------------------------------------------------------------------
def analyze_news_item(item, idx, source_name):
    """
    Формируем многострочный промпт для одной новости и отправляем в LLM.
    item: { "title", "summary", "link", "published" }
    idx: номер новости в списке, source_name: имя источника.
    """
    title = item["title"]
    published = item.get("published", "")
    link = item.get("link", "")
    summary = item.get("summary", "")

    prompt_lines = [
        f"Заголовок: {title}",
        f"Дата публикации: {published}" if published else "Дата публикации: неизвестна",
        f"Ссылка: {link}" if link else "",
        "Краткое содержание новости:",
        summary,
        "",
        "Пожалуйста, подробно проанализируй эту новость и приведи свои размышления о том,",
        "какое влияние она может оказать на крипторынок.",
        "Скажи, важна ли эта информация при принятии решения о покупке или продаже криптовалюты,",
        "и для каких конкретных монет она может быть наиболее значимой.",
        "Приводи аргументы и обоснования своих выводов."
    ]
    prompt_text = "\n".join([line for line in prompt_lines if line])

    print(f"[DEBUG] Анализ новости #{idx} из '{source_name}': {title!r}")
    # Здесь мы не будем печатать весь prompt целиком (он может быть очень длинным),
    # но видим первые 100 символов внутри call_llm_analyze.
    return call_llm_analyze(prompt_text)

# ----------------------------------------------------------------------
# 8. Основной цикл: обработка всех источников и сбор результатов
# ----------------------------------------------------------------------
def process_all_feeds(config_path):
    """
    Читает feeds.json { source_name: feed_url, … }.
    Для каждого источника:
      - загружает parsed_feed = fetch_feed(feed_url)
      - items = extract_items(parsed_feed, source_name)
      - для каждого элемента вызывает analyze_news_item(item)
    Возвращает словарь:
      { source_name: [ { item, analysis }, … ], … }
    """
    feeds_dict = load_feed_config(config_path)
    print(f"[DEBUG] Загружены источники: {list(feeds_dict.keys())}\n")
    all_results = {}

    for source_name, feed_url in feeds_dict.items():
        print(f"[DEBUG] ===== Обработка источника: {source_name} =====")
        parsed_feed = fetch_feed(feed_url)
        items = extract_items(parsed_feed, source_name)

        analyses = []
        for idx, item in enumerate(items, start=1):
            try:
                analysis = analyze_news_item(item, idx, source_name)
            except Exception as e:
                analysis = f"Ошибка при анализе: {e}"
                print(f"[DEBUG]    Перехвачена ошибка: {e}")
            analyses.append({
                "item": item,
                "analysis": analysis
            })
        all_results[source_name] = analyses
        print(f"[DEBUG] === Завершено для '{source_name}'. Обработано новостей: {len(analyses)} ===\n")

    print(f"[DEBUG] Конечная структура all_results: ключи источников = {list(all_results.keys())}")
    total_news = sum(len(v) for v in all_results.values())
    print(f"[DEBUG] Общее число обработанных новостей: {total_news}\n")
    return all_results

# ----------------------------------------------------------------------
# 9. Точка входа: запускаем process_all_feeds и записываем в JSON
# ----------------------------------------------------------------------
if __name__ == "__main__":
    CONFIG_PATH = "modules/news.json"     # Убедитесь, что этот файл лежит рядом со скриптом
    OUTPUT_PATH = "modules/results_2.json"   # Сюда запишутся результаты

    results = process_all_feeds(CONFIG_PATH)

    # Печатаем первые 300 символов полного results для контроля
    full_results_str = json.dumps(results, ensure_ascii=False, indent=2)
    preview = (full_results_str[:300] + "...\n]") if len(full_results_str) > 300 else full_results_str
    print(f"[DEBUG] Предварительный просмотр all_results (первые 300 символов):\n{preview}\n")

    # Записываем окончательные результаты в файл
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fout:
        json.dump(results, fout, ensure_ascii=False, indent=2)

    print(f"Готово: результаты сохранены в {OUTPUT_PATH}")
