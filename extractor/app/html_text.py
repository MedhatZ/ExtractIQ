from bs4 import BeautifulSoup

REMOVED_TAGS = ("script", "style", "noscript", "svg", "iframe", "header", "footer", "nav")


def html_to_text(raw: str, content_type: str) -> str:
    if content_type.startswith("text/plain"):
        return " ".join(raw.split())

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(REMOVED_TAGS):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    body = soup.get_text(separator="\n", strip=True)
    parts = [part for part in (title, body) if part]
    return "\n".join(parts)
