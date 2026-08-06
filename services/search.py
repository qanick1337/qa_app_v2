from concurrent.futures import ThreadPoolExecutor

from services.db import get_connection
from services.indexer import embed


def search_kb(query: str, top_k: int = 3, threshold: float = 0.45, section: str = None) -> list[dict]:
    try:
        query_vector = embed(query)
    except Exception as e:
        print("Error while embedding", e)
        raise

    connection = get_connection()

    with connection.cursor() as cur:
        if section:
            cur.execute("""
                SELECT title, url, content, source,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM kb_chunks
                WHERE section = %s AND 1 - (embedding <=> %s::vector) > %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (query_vector, section, query_vector, threshold, query_vector, top_k))
        else:
            cur.execute("""
                SELECT title, url, content, source,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM kb_chunks
                WHERE 1 - (embedding <=> %s::vector) > %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (query_vector, query_vector, threshold, query_vector, top_k))
        rows = cur.fetchall()
    connection.close()

    return [
        {
            "title": row[0],
            "url": row[1],
            "content": row[2],
            "source": row[3],
            "similarity": round(row[4], 4),
        }
        for row in rows
    ]


def search_all_issues(search_queries: list[dict], top_k_per_issue: int = 3) -> list[dict]:
    all_chunks = []
    seen_article_ids = set()

    with ThreadPoolExecutor(max_workers=len(search_queries)) as executor:
        results = executor.map(
            lambda query: search_kb(query["search_query"], top_k=top_k_per_issue),
            search_queries,
        )
        for chunks in results:
            for chunk in chunks:
                key = (chunk["title"], chunk.get("url"))
                if key not in seen_article_ids:
                    seen_article_ids.add(key)
                    all_chunks.append(chunk)

    return all_chunks