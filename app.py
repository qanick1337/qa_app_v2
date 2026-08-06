import os
import httpx

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from fastapi import Depends

from services.auth import verify_token

from services.articles import list_all_articles
from services.db import get_connection
from services.indexer import index_articles
from services.zendesk_tickets import list_tickets
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

from confluence.loader import (
    fetch_confluence_page,
    fetch_confluence_page_title,
    fetch_confluence_page_as_folder,
    fetch_confluence_folder
)

from services.stats import get_topic_stats

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


@app.get("/articles", dependencies=[Depends(verify_token)])
def all_articles():
    connection = get_connection()
    try:
        return list_all_articles(connection)
    finally:
        connection.close()


@app.get("/zendesk/articles/{article_id}", dependencies=[Depends(verify_token)])
def zendesk_article(article_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT id, article_id, title, url, source, content, section FROM kb_chunks WHERE article_id = %s AND source = 'zendesk' ",
                (str(article_id),)
            )
            rows = cur.fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="Chunks not found for this article")

        return [
            {
                "id": row[0], "article_id": row[1], "title": row[2],
                "url": row[3], "source": row[4], "content": row[5], "section": row[6],
            }
            for row in rows
        ]
    finally:
        connection.close()

@app.get("/confluence/articles/{article_id}", dependencies=[Depends(verify_token)])
def confluence_article(article_id: int):
    connection = get_connection()
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT id, article_id, title, url, source, content, section FROM kb_chunks WHERE article_id = %s AND source = 'confluence' ",
                (str(article_id),)
            )
            rows = cur.fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="Chunks not found for this article")

        return [
            {
                "id": row[0], "article_id": row[1], "title": row[2],
                "url": row[3], "source": row[4], "content": row[5], "section": row[6],
            }
            for row in rows
        ]
    finally:
        connection.close()




@app.post("/zendesk/index/section/{section_id}", dependencies=[Depends(verify_token)])
def index_zendesk_section(section_id: int):
    articles = fetch_zendesk_article_section(section_id)
    if not articles:
        raise HTTPException(status_code=404, detail=f"No articles found for section {section_id}")

    connection = get_connection()
    try:
        index_articles(articles, source="zendesk", conn=connection)
    finally:
        connection.close()

    return {"section_id": section_id, "articles_indexed": len(articles)}

@app.post("/zendesk/index/article/{article_id}", dependencies=[Depends(verify_token)])
def index_zendesk_article(article_id: int):
    article = fetch_single_zendesk_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Zendesk article {article_id} not found")

    article["section"] = fetch_zendesk_section_name(article["section_id"])

    connection = get_connection()
    try:
        index_articles([article], source="zendesk", conn=connection)
    finally:
        connection.close()

    return {"article_id": article_id, "title": article["title"], "indexed": True}


@app.post("/confluence/index/page/{page_id}", dependencies=[Depends(verify_token)])
def index_confluence_article(page_id: int):
    article = fetch_confluence_page(page_id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Confluence page {page_id} not found")


    connection = get_connection()
    try:
        index_articles([article], source="confluence", conn=connection)
    finally:
        connection.close()

    return {"article_id": page_id, "title": article["title"], "indexed": True}

@app.post("/confluence/index/folder/{folder_id}", dependencies=[Depends(verify_token)])
def index_confluence_folder(folder_id: int):
    articles = fetch_confluence_folder(folder_id)
    if not articles:
        raise HTTPException(status_code=404, detail=f"Confluence folder {folder_id} not found")


    connection = get_connection()
    try:
        index_articles(articles, source="confluence", conn=connection)
    finally:
        connection.close()

    return {"folder_id": folder_id, "articles_indexed": len(articles)}

@app.post("/confluence/index/page_as_folder/{page_id}", dependencies=[Depends(verify_token)])
def index_confluence_article_as_folder(page_id: int):
    articles = fetch_confluence_page_as_folder(page_id)
    if not articles:
        raise HTTPException(status_code=404, detail=f"Confluence page {page_id} not found")


    connection = get_connection()
    try:
        index_articles(articles, source="confluence", conn=connection)
    finally:
        connection.close()

    return {"article_id": page_id, "title": fetch_confluence_page_title(page_id), "indexed": True}

@app.post("/qa-evaluations/{ticket_id}", dependencies=[Depends(verify_token)])
def create_qa_evaluation(ticket_id: int, payload: QAEvaluationRequest = QAEvaluationRequest()):
    agent_ids = payload.agent_ids or DEFAULT_AGENT_IDS
    if not agent_ids:
        raise HTTPException(
            status_code=400,
            detail="agent_ids was not provided and AGENT_ZENDESK_IDS is not set in .env",
        )

    try:
        (evaluation, sla_metrics, llm_model) = evaluate_ticket_qa(ticket_id, agent_ids)
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

@app.get("/tickets", dependencies=[Depends(verify_token)])
def get_tickets(
    created_after: str | None = None,   # "2026-01-01"
    created_before: str | None = None,  # "2026-01-31"
    agent_ids: str | None = None,       # "364579400459,14641313455772"
    agent_tag: str | None = None,       # "ivan_petrenko"
    tags: str | None = None,            # "vip,escalated"
    page: int = 1,
):
    parsed_agent_ids = (
        [int(x) for x in agent_ids.split(",") if x.strip()] if agent_ids else None
    )
    parsed_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    try:
        return list_tickets(
            created_after=created_after,
            created_before=created_before,
            agent_ids=parsed_agent_ids,
            agent_tag=agent_tag,
            tags=parsed_tags,
            page=page,
            page_size=25,
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Zendesk error: {e.response.text}")


@app.get("/stats/topics", dependencies=[Depends(verify_token)])
def stats_by_topic(date_from: str | None = None, date_to: str | None = None):
    return get_topic_stats(date_from, date_to)