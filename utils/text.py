import textwrap

def squeeze_text(text: str, max_tokens: int = 800) -> str:
    """
    Обрезаем статью, чтобы она гарантированно влезла в контекст LLM.
    1 токен ≈ 0.75 слова. Берём первые 70 % слов.
    """
    max_words = int(max_tokens / 0.75)
    words = text.split()
    if len(words) <= max_words:
        return text
    cutoff = int(max_words * 0.7)
    snippet = " ".join(words[:cutoff])
    return textwrap.shorten(snippet, width=max_tokens * 4, placeholder=" …")
