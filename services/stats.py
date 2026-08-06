from services.db import get_connection


def get_topic_stats(date_from: str | None = None, date_to: str | None = None) -> dict:
    connection = get_connection()
    try:
        with connection.cursor() as cur:
            query = """
                SELECT canonical_topic_id, canonical_topic, COUNT(*) AS ticket_count
                FROM qa_evaluations
                WHERE 1=1
            """

            params = []
            
            if date_from:
                query += " AND created_at::date >= %s"
                params.append(date_from)
            if date_to:
                query += " AND created_at::date <= %s"
                params.append(date_to)

            query += " GROUP BY canonical_topic_id, canonical_topic ORDER BY ticket_count DESC"

            cur.execute(query, params)
            rows = cur.fetchall()
    finally:
        connection.close()

    total = sum(row[2] for row in rows)

    return {
        "total_evaluations": total,
        "topics": [
            {
                "canonical_topic_id": row[0],
                "canonical_topic": row[1],
                "ticket_count": row[2],
                "percentage": round(row[2] / total * 100, 1) if total else 0.0,
            }
            for row in rows
        ],
    }