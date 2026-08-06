import os

import openai
from dotenv import load_dotenv

from services.chunker import chunk_text

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")


def embed(text: str) -> list[float]:
    response = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=1024,
    )
    return response.data[0].embedding


def index_articles(articles: list[dict], source: str, conn):
    with conn.cursor() as cur:
        for article in articles:
            cur.execute(
                "DELETE FROM kb_chunks WHERE article_id = %s",
                (str(article["id"]),)
            )

            chunks = chunk_text(article["body"])
            print(f"INDEX: [{source}] '{article['title']}' => {len(chunks)} chunks")

            for index, chunk in enumerate(chunks):
                vector = embed(chunk)
                cur.execute("""
                    INSERT INTO kb_chunks
                        (article_id, title, url, source, chunk_index, content, embedding, section)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                    str(article["id"]),
                    article["title"],
                    article.get("url", ""),
                    source,
                    index,
                    chunk,
                    vector,
                    article["section"]
                ))
    conn.commit()