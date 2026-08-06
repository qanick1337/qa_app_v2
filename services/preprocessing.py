import json
import re
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

IMAGE_MARKDOWN_PATTERN = re.compile(r"!\[.*?\]\(https?://[^\)]+\)")


def strip_image_markup(text: str) -> str:
    if not text:
        return ""
    return IMAGE_MARKDOWN_PATTERN.sub("", text).strip()


def build_transcript(comments: list[dict], agent_ids: list[int]) -> list[dict]:
    sorted_comments = sorted(comments, key=lambda c: c["created_at"])

    transcript = []
    for comment in sorted_comments:
        if comment["author_id"] in agent_ids:
            role = "agent_public" if comment["public"] else "agent_internal"
        else:
            role = "customer"

        transcript.append({
            "id": comment["id"],
            "author_id": comment["author_id"],
            "role": role,
            "text": strip_image_markup(comment.get("body", "")),
            "created_at": comment["created_at"],
            "public": comment["public"],
        })

    return transcript


def parse_timestamp(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def compute_sla_metrics(comments: list[dict], agent_ids: list[int], first_response_sla_sec: int = 840, gap_sla_sec: int = 3600) -> dict:
    public = sorted(
        (comment for comment in comments if comment["public"]),
        key=lambda c: c["created_at"],
    )

    if not public:
        return {
            "first_response_time_sec": None,
            "handling_time_sec": None,
            "longest_agent_gap_sec": 0,
            "avg_agent_gap_sec": 0,
            "longest_customer_gap_sec": 0,
            "avg_customer_gap_sec": 0,
            "total_agent_replies": 0,
            "total_customer_messages": 0,
        }

    events = [
        {
            "ts": parse_timestamp(comment["created_at"]),
            "role": "agent" if comment["author_id"] in agent_ids else "customer",
        }
        for comment in public
    ]

    first_customer_ts = next((e["ts"] for e in events if e["role"] == "customer"), None)
    first_agent_ts = next((e["ts"] for e in events if e["role"] == "agent"), None)

    first_response_time = None
    if first_customer_ts and first_agent_ts and first_agent_ts >= first_customer_ts:
        first_response_time = (first_agent_ts - first_customer_ts).total_seconds()

    agent_gaps = []
    customer_gaps = []
    for prev, curr in zip(events, events[1:]):
        gap = (curr["ts"] - prev["ts"]).total_seconds()
        if prev["role"] == "customer" and curr["role"] == "agent":
            agent_gaps.append(gap)
        elif prev["role"] == "agent" and curr["role"] == "customer":
            customer_gaps.append(gap)

    handling_time = (events[-1]["ts"] - events[0]["ts"]).total_seconds()

    return {
        "first_response_time_sec": first_response_time,
        "first_response_breached": first_response_time is not None and first_response_time > first_response_sla_sec,
        "handling_time_sec": handling_time,
        "longest_agent_gap_sec": max(agent_gaps, default=0),
        "avg_agent_gap_sec": round(sum(agent_gaps) / len(agent_gaps), 1) if agent_gaps else 0,
        "agent_gap_breached": max(agent_gaps, default=0) > gap_sla_sec,
        "longest_customer_gap_sec": max(customer_gaps, default=0),
        "avg_customer_gap_sec": round(sum(customer_gaps) / len(customer_gaps), 1) if customer_gaps else 0,
        "total_agent_replies": sum(1 for e in events if e["role"] == "agent"),
        "total_customer_messages": sum(1 for e in events if e["role"] == "customer"),
    }


def summarize_ticket_problem_via_llm(transcript: list[dict]) -> list[dict]:
    if not transcript:
        return []

    lines = []
    for message in transcript:
        if not message["text"]:
            continue

        role_label = {
            "customer": "CUSTOMER",
            "agent_public": "AGENT",
            "agent_internal": "AGENT (internal note)",
        }[message["role"]]
        lines.append(f"[{role_label}] {message['text']}")

    transcript_for_llm = "\n".join(lines)

    client = OpenAI(api_key=__import__("os").getenv("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{
            "role": "user",
            "content": (
                "You are extracting search queries from a support ticket thread "
                "for a knowledge-base retrieval system.\n\n"
                "The thread may contain ONE issue or SEVERAL unrelated issues "
                "(e.g. a group chat covering multiple topics). Identify each "
                "distinct technical issue separately — do not merge unrelated "
                "problems into one entry.\n\n"
                "For each issue return:\n"
                "- \"problem\": a short human-readable description (1 sentence)\n"
                "- \"search_query\": a SHORT keyword-style phrase (5-12 words), "
                "written like the TITLE of a technical instruction article. "
                "Describe ONLY the problem itself — no resolution narrative, "
                "no markdown, no bullet points, no preamble like 'Summary of...'. "
                "Write it in the same language as the ticket.\n"
                "- \"resolved\": true or false — whether the thread shows the "
                "issue was resolved\n\n"
                "Ignore internal agent notes unless they clarify the root cause "
                "of a customer-facing issue.\n\n"
                "Return ONLY valid JSON in this exact shape, no extra text:\n"
                '{"issues": [{"problem": "...", "search_query": "...", "resolved": true}]}\n\n'
                f"TICKET THREAD:\n{transcript_for_llm}"
            ),
        }],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)["issues"]


def ticket_preprocessing(comments: list[dict], agent_ids: list[int]) -> dict:
    transcript = build_transcript(comments, agent_ids)
    sla_metrics = compute_sla_metrics(comments, agent_ids)
    issues = summarize_ticket_problem_via_llm(transcript)

    return {
        "issues": issues,
        "sla_metrics": sla_metrics,
        "transcript": transcript,
        "message_count": len(transcript),
    }