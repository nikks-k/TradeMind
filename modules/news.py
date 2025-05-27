import feedparser

RSS = "https://ria.ru/export/rss2/archive/index.xml"

def news_parse(url):
    feed = feedparser.parse(url)

    title = feed.feed.get('title', 'Без названия')
    link = feed.feed.get('link', '')
    print(f'Канал: {title}\nСайт: {link}\n')

    # Проходим по всем записям
    for entry in feed.entries:
        print('――――――――――――――――――')
        print(f'Заголовок: {entry.get("title", "Нет заголовка")}')
        print(f'Ссылка: {entry.get("link", "Нет ссылки")}')
        published = entry.get('published', entry.get('updated', 'Нет даты'))
        print(f'Дата: {published}')
        summary = entry.get('summary', entry.get('description', 'Нет описания'))
        print(f'Описание: {summary}\n')


if __name__ == '__main__':
    news_parse(RSS)
