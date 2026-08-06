import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from fastapi import Depends

from services.auth import verify_token

from services.db import get_connection
from services.indexer import index_articles
from services.qa_evaluation import (
    QAEvaluationError,
    evaluate_ticket_qa,
    get_qa_evaluation,
    save_qa_evaluation,
)
from zendesk.loader import (
    fetch_single_zendesk_article,
    fetch_zendesk_article_section,
    fetch_zendesk_section_name,
    internal_sections_id,
    public_section_id,
)

load_dotenv()

app = FastAPI(title="SUPPORT RAG API")

DEFAULT_AGENT_IDS = [
    int(x) for x in os.getenv("AGENT_ZENDESK_IDS", "").split(",") if x.strip()
]


class QAEvaluationRequest(BaseModel):
    agent_ids: list[int] | None = None


@app.get("/")
def root():
    return {"status": "ok"}


# @app.get("/articles/{article_id}")
# def get_article(article_id: int):
#     connection = get_connection()
#     try:
#         with connection.cursor() as cur:
#             cur.execute(
#                 "SELECT id, article_id, title, url, source, content, section FROM kb_chunks WHERE article_id = %s",
#                 (str(article_id),)
#             )
#             rows = cur.fetchall()

#         if not rows:
#             raise HTTPException(status_code=404, detail="Chunks not found for this article")

#         return [
#             {
#                 "id": row[0], "article_id": row[1], "title": row[2],
#                 "url": row[3], "source": row[4], "content": row[5], "section": row[6],
#             }
#             for row in rows
#         ]
#     finally:
#         connection.close()


# @app.get("/articles/")
# def get_articles():
#     connection = get_connection()
#     try:
#         with connection.cursor() as cur:
#             cur.execute("""
#                 SELECT
#                     MIN(id) as id, article_id, title, url,
#                     MAX(source) AS source,
#                     STRING_AGG(content, E'\n\n' ORDER BY id) AS full_content,
#                     STRING_AGG(DISTINCT section, ', ') AS section
#                 FROM kb_chunks
#                 GROUP BY article_id, title, url;
#             """)
#             rows = cur.fetchall()

#         if not rows:
#             raise HTTPException(status_code=404, detail="Chunks not found for all articles")

#         return [
#             {
#                 "id": row[0], "article_id": row[1], "title": row[2],
#                 "url": row[3], "source": row[4], "content": row[5], "section": row[6],
#             }
#             for row in rows
#         ]
#     finally:
#         connection.close()


# @app.post("/zendesk/index/all")
# def index_all_zendesk_sections():
#     connection = get_connection()
#     details = []
#     try:
#         all_sections = {**internal_sections_id, **public_section_id}
#         for name, section_id in all_sections.items():
#             articles = fetch_zendesk_article_section(section_id)
#             index_articles(articles, source="zendesk", conn=connection)
#             details.append({
#                 "section": name,
#                 "section_id": section_id,
#                 "articles_indexed": len(articles),
#             })
#     finally:
#         connection.close()

#     return {
#         "sections_indexed": len(details),
#         "articles_indexed": sum(d["articles_indexed"] for d in details),
#         "details": details,
#     }


# @app.post("/zendesk/index/section/{section_id}")
# def index_zendesk_section(section_id: int):
#     articles = fetch_zendesk_article_section(section_id)
#     if not articles:
#         raise HTTPException(status_code=404, detail=f"No articles found for section {section_id}")

#     connection = get_connection()
#     try:
#         index_articles(articles, source="zendesk", conn=connection)
#     finally:
#         connection.close()

#     return {"section_id": section_id, "articles_indexed": len(articles)}


@app.post("/zendesk/index/article/{article_id}", dependencies=[Depends(verify_token)])
def index_zendesk_article(article_id: int):
    article = fetch_single_zendesk_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article {article_id} not found")

    article["section"] = fetch_zendesk_section_name(article["section_id"])

    connection = get_connection()
    try:
        index_articles([article], source="zendesk", conn=connection)
    finally:
        connection.close()

    return {"article_id": article_id, "title": article["title"], "indexed": True}


@app.post("/qa-evaluations/{ticket_id}", dependencies=[Depends(verify_token)])
def create_qa_evaluation(ticket_id: int, payload: QAEvaluationRequest = QAEvaluationRequest()):
    agent_ids = payload.agent_ids or DEFAULT_AGENT_IDS
    if not agent_ids:
        raise HTTPException(
            status_code=400,
            detail="agent_ids was not provided and AGENT_ZENDESK_IDS is not set in .env",
        )

    try:
        evaluation, sla_metrics, llm_model = evaluate_ticket_qa(ticket_id, agent_ids)
    except QAEvaluationError as e:
        raise HTTPException(status_code=502, detail=str(e))

    connection = get_connection()
    try:
        save_qa_evaluation(connection, ticket_id, evaluation, sla_metrics, llm_model)
    finally:
        connection.close()

    return {"ticket_id": ticket_id, "llm_model": llm_model, **evaluation}


@app.get("/qa-evaluations/{ticket_id}", dependencies=[Depends(verify_token)])
def read_qa_evaluation(ticket_id: int):
    connection = get_connection()
    try:
        evaluation = get_qa_evaluation(connection, ticket_id)
    finally:
        connection.close()

    if not evaluation:
        raise HTTPException(status_code=404, detail=f"No QA evaluation found for ticket {ticket_id}")

    return evaluation