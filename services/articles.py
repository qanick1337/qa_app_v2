from itertools import groupby
from services.chunker import DEFAULT_OVERLAP

def assemble_content(chunks_in_order: list[str], overlap: int = DEFAULT_OVERLAP) -> str:
    words: list[str] = []
    for index, chunk in enumerate(chunks_in_order):
        chunk_words = chunk.split()
        words.extend(chunk_words if index == 0 else chunk_words[overlap:])
    return " ".join(words)

def list_all_articles(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT article_id, title, url, source, section, content
            FROM kb_chunks
            ORDER BY source, article_id, chunk_index
        """)
        rows = cur.fetchall()

    articles = []
    for (article_id, title, url, source, section), group in groupby(
        rows, key=lambda row: (row[0], row[1], row[2], row[3], row[4])
    ):
        chunks = [row[5] for row in group]

        articles.append({
            "article_id": article_id,
            "title": title,
            "url": url,
            "source": source,
            "section": section,
            "content": assemble_content(chunks),
        })

    return articles