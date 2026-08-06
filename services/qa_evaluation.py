import json
import os

from dotenv import load_dotenv
from openai import OpenAI
from psycopg2.extras import Json

from services.preprocessing import ticket_preprocessing
from services.search import search_all_issues
from zendesk.loader import fetch_single_zendesk_ticket

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

CANONICAL_TOPICS = (
    "senet_id=SENET ID, senet_id_application=SENET ID APPLICATION, senet_id_web_portal=SENET ID WEB PORTAL, "
    "venue_map=VENUE MAP, booking=BOOKING, controllers_senet_console_app=CONTROLLERS AND SENET CONSOLE APP, "
    "cashdesk=CASHDESK, checkbox_integration=CHECKBOX INTEGRATION, shop_and_shop_shell=SHOP AND SHOP SHELL, "
    "content=CONTENT, game_update=GAME UPDATE, senet_boot=SENET BOOT, diskless_cache=DISKLESS CACHE, "
    "dashboard_and_statistics=DASHBOARD AND STATISTICS, zones_rates_passes=ZONES RATES AND PASSES, "
    "loyalty_program=LOYALTY PROGRAM, users=USERS, news=NEWS, shell_settings=SHELL SETTINGS, "
    "gaming_pc_issues=GAMING PC ISSUES, local_windows_accounts=LOCAL WINDOWS ACCOUNTS, "
    "games_and_apps=GAMES AND APPS, client_interface=CLIENT INTERFACE, senet_subscription=SENET SUBSCRIPTION, "
    "access_and_security=ACCESS AND SECURITY, billing_and_gaming_sessions=BILLING AND GAMING SESSIONS, "
    "admin_panel=ADMIN PANEL, sms_integration=SMS INTEGRATION, "
    "online_payment_system_integration=ONLINE PAYMENT SYSTEM INTEGRATION, tasks=TASKS, suggestions=SUGGESTIONS, "
    "other=OTHER, unclear_issue=UNCLEAR ISSUE, no_clear_customer_issue=NO CLEAR CUSTOMER ISSUE"
)


class QAEvaluationError(Exception):
    """Помилка на етапі отримання тікета, препроцесингу чи виклику LLM."""


def _build_prompt(preprocessing_info: dict, knowledge_base_context: str) -> str:
    sla = preprocessing_info["sla_metrics"]

    return f"""
        You are a QA evaluator for a customer support team. In ONE pass, evaluate the support agent's performance in the ticket below across two dimensions, and classify the ticket topic.

        WEIGHTING:
        - Content accuracy vs KB: 75% of overall score
        - Communication quality: 25% of overall score

        === 1. CONTENT EVALUATION (vs KB) ===
        Compare the agent's answers with the KB INSTRUCTIONS.
        Rules:
        1. If the agent's answer links an article, treat that article's steps as part of the agent's reply — but verify the linked article actually resolves the customer's specific issue. An irrelevant or tangential link is a failure: record it in "incorrect_points" and lower the result/score.
        2. If the customer expresses frustration or mentions already-failed attempts, the agent must acknowledge and address those specific points. Generic steps the customer already tried lower the score.
        3. KB INSTRUCTIONS are the primary source of truth. Also apply fundamentally correct general technical knowledge to spot logical gaps or inaccurate advice — but never contradict the KB.
        4. If KB INSTRUCTIONS are empty or irrelevant to the question, set "kb_source" to null and evaluate using general knowledge only; note this in "qa_comment".

        content_result: "correct" | "partially_correct" | "incorrect"
        content_score: 1-5

        === 2. COMMUNICATION EVALUATION ===
        Evaluate ONLY the agent's messages (customer messages are context only).
        - Tone & clarity (60% of this dimension): friendly, professional, calm, clear next steps; not cold, dismissive, or confusing. Natural tone is enough - do not require exaggerated empathy.
        - Language quality (40% of this dimension): grammar, spelling, wording, readability. Ignore minor typos that don't affect understanding; penalize only issues that create ambiguity or sound careless.
        Do NOT evaluate troubleshooting quality or resolution here - that is covered by content evaluation.

        communication_score: 1-5
        If communication is good, say so briefly - do not invent issues.

        === 3. TOPIC CLASSIFICATION ===
        Select exactly ONE canonical topic from this list (id=LABEL). Never create new topics:
        {CANONICAL_TOPICS}

        Selection rules:
        - senet_id_application = SENET ID app; senet_id_web_portal = web portal/browser; senet_id = only if unclear which.
        - checkbox_integration = Checkbox setup, fiscalization, receipts.
        - gaming_pc_issues = PC/workstation/hardware; local_windows_accounts = only Windows local accounts.
        - games_and_apps = launching/using specific games or apps; game_update = only game update issues.
        - other = no listed topic fits; unclear_issue = issue unclear; no_clear_customer_issue = no real issue.

        === 4. SLA & RESPONSIVENESS (calculated, use as facts) ===
        First response time: {sla['first_response_time_sec']}s
        Handling time: {sla['handling_time_sec']}s
        Longest agent gap: {sla['longest_agent_gap_sec']}s

        === BREVITY RULES (mandatory) ===
        - Each item in correct_points / missing_points / incorrect_points: one short sentence, max 15 words.
        - Max 3 items per array. Empty array if nothing to report.
        - qa_comment: max 2 sentences. recommendation: max 2 sentences, actionable.
        - No repetition between arrays and qa_comment.

        === SCORING ===
        overall_score = round(0.75 * content_score + 0.25 * communication_score, 1)  // scale 1-5

        === OUTPUT ===
        Return ONLY valid JSON, no markdown, no extra text:
        {{
        "result": "correct|partially_correct|incorrect",
        "content_quality_score": 1-5,
        "communication_score": 1-5,
        "overall_score": 1.0-5.0,
        "kb_source": {{"title": "...", "url": "..."}},
        "correct_points": [],
        "missing_points": [],
        "incorrect_points": [],
        "communication_issues": [],
        "qa_comment": "",
        "recommendation": "",
        "topic": {{
            "raw_issue_topic": "",
            "canonical_topic_id": "",
            "canonical_topic": "",
            "topic_confidence": "High|Medium|Low"
        }}
        }}

        KB INSTRUCTIONS:
        {knowledge_base_context}

        # TICKET TRANSCRIPT:
        {preprocessing_info["transcript"]}
    """


def evaluate_ticket_qa(ticket_id: int, agent_ids: list[int]) -> tuple[dict, dict, str]:
    """Fetch -> preprocess (+ LLM issue extraction) -> KB search. Може впасти на будь-якому з цих кроків."""
    try:
        comments = fetch_single_zendesk_ticket(ticket_id)["comments"]
        preprocessing_info = ticket_preprocessing(comments, agent_ids)
        ticket_problem_chunks = search_all_issues(preprocessing_info["issues"])
    except Exception as e:
        raise QAEvaluationError(f"Preprocessing/search failed for ticket {ticket_id}: {e}") from e

    knowledge_base_context = "\n\n".join(
        f"[{c['title']}]\n{c['content']}" for c in ticket_problem_chunks
    )
    prompt = _build_prompt(preprocessing_info, knowledge_base_context)

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
    except Exception as e:
        raise QAEvaluationError(f"LLM call failed for ticket {ticket_id}: {e}") from e

    evaluation = json.loads(response.choices[0].message.content)
    return (evaluation, preprocessing_info["sla_metrics"], OPENAI_MODEL)


def save_qa_evaluation(conn, ticket_id: int, evaluation: dict, sla_metrics: dict, llm_model: str) -> None:
    """UPSERT — переоцінка тікета просто перезаписує попередній результат."""
    topic = evaluation.get("topic") or {}
    kb_source = evaluation.get("kb_source") or {}

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO qa_evaluations (
                ticket_id, result, content_quality_score, communication_score, overall_score,
                kb_source_title, kb_source_url,
                correct_points, missing_points, incorrect_points, communication_issues,
                qa_comment, recommendation,
                raw_issue_topic, canonical_topic_id, canonical_topic, topic_confidence,
                first_response_time_sec, handling_time_sec, longest_agent_gap_sec,
                llm_model
            ) VALUES (
                %(ticket_id)s, %(result)s, %(content_quality_score)s, %(communication_score)s, %(overall_score)s,
                %(kb_source_title)s, %(kb_source_url)s,
                %(correct_points)s, %(missing_points)s, %(incorrect_points)s, %(communication_issues)s,
                %(qa_comment)s, %(recommendation)s,
                %(raw_issue_topic)s, %(canonical_topic_id)s, %(canonical_topic)s, %(topic_confidence)s,
                %(first_response_time_sec)s, %(handling_time_sec)s, %(longest_agent_gap_sec)s,
                %(llm_model)s
            )
            ON CONFLICT (ticket_id) DO UPDATE SET
                result = EXCLUDED.result,
                content_quality_score = EXCLUDED.content_quality_score,
                communication_score = EXCLUDED.communication_score,
                overall_score = EXCLUDED.overall_score,
                kb_source_title = EXCLUDED.kb_source_title,
                kb_source_url = EXCLUDED.kb_source_url,
                correct_points = EXCLUDED.correct_points,
                missing_points = EXCLUDED.missing_points,
                incorrect_points = EXCLUDED.incorrect_points,
                communication_issues = EXCLUDED.communication_issues,
                qa_comment = EXCLUDED.qa_comment,
                recommendation = EXCLUDED.recommendation,
                raw_issue_topic = EXCLUDED.raw_issue_topic,
                canonical_topic_id = EXCLUDED.canonical_topic_id,
                canonical_topic = EXCLUDED.canonical_topic,
                topic_confidence = EXCLUDED.topic_confidence,
                first_response_time_sec = EXCLUDED.first_response_time_sec,
                handling_time_sec = EXCLUDED.handling_time_sec,
                longest_agent_gap_sec = EXCLUDED.longest_agent_gap_sec,
                llm_model = EXCLUDED.llm_model
            """,
            {
                "ticket_id": ticket_id,
                "result": evaluation["result"],
                "content_quality_score": evaluation["content_quality_score"],
                "communication_score": evaluation["communication_score"],
                "overall_score": evaluation["overall_score"],
                "kb_source_title": kb_source.get("title"),
                "kb_source_url": kb_source.get("url"),
                "correct_points": Json(evaluation.get("correct_points", [])),
                "missing_points": Json(evaluation.get("missing_points", [])),
                "incorrect_points": Json(evaluation.get("incorrect_points", [])),
                "communication_issues": Json(evaluation.get("communication_issues", [])),
                "qa_comment": evaluation.get("qa_comment"),
                "recommendation": evaluation.get("recommendation"),
                "raw_issue_topic": topic.get("raw_issue_topic"),
                "canonical_topic_id": topic.get("canonical_topic_id"),
                "canonical_topic": topic.get("canonical_topic"),
                "topic_confidence": topic.get("topic_confidence"),
                "first_response_time_sec": sla_metrics.get("first_response_time_sec"),
                "handling_time_sec": sla_metrics.get("handling_time_sec"),
                "longest_agent_gap_sec": sla_metrics.get("longest_agent_gap_sec"),
                "llm_model": llm_model,
            },
        )
    conn.commit()


def get_qa_evaluation(conn, ticket_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ticket_id, result, content_quality_score, communication_score, overall_score,
                kb_source_title, kb_source_url,
                correct_points, missing_points, incorrect_points, communication_issues,
                qa_comment, recommendation,
                raw_issue_topic, canonical_topic_id, canonical_topic, topic_confidence,
                first_response_time_sec, handling_time_sec, longest_agent_gap_sec,
                llm_model, created_at, updated_at
            FROM qa_evaluations
            WHERE ticket_id = %s
            """,
            (ticket_id,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "ticket_id": row[0],
        "result": row[1],
        "content_quality_score": row[2],
        "communication_score": row[3],
        "overall_score": float(row[4]),
        "kb_source": {"title": row[5], "url": row[6]} if row[5] or row[6] else None,
        "correct_points": row[7],
        "missing_points": row[8],
        "incorrect_points": row[9],
        "communication_issues": row[10],
        "qa_comment": row[11],
        "recommendation": row[12],
        "topic": {
            "raw_issue_topic": row[13],
            "canonical_topic_id": row[14],
            "canonical_topic": row[15],
            "topic_confidence": row[16],
        },
        "sla_metrics": {
            "first_response_time_sec": row[17],
            "handling_time_sec": row[18],
            "longest_agent_gap_sec": row[19],
        },
        "llm_model": row[20],
        "created_at": row[21].isoformat() if row[21] else None,
        "updated_at": row[22].isoformat() if row[22] else None,
    }