from zendesk.loader import search_zendesk_tickets

MAX_ZENDESK_PAGES = 10   # запобіжник, щоб дуже вузький фільтр по тегах не крутився вічно
ZENDESK_PAGE_SIZE = 100  # скільки кандидатів тягнемо із Zendesk за один виклик


def ticket_matches_tags(ticket: dict, required_tags: list[str]) -> bool:
    if not required_tags:
        return True
    return set(required_tags).issubset(set(ticket.get("tags", [])))


def list_tickets(
    created_after: str | None = None,
    created_before: str | None = None,
    agent_ids: list[int] | None = None,
    agent_tag: str | None = None,
    tags: list[str] | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    required_tags = list(tags or [])
    
    if agent_tag:
        required_tags.append(agent_tag)

    skip = (page - 1) * page_size
    matched: list[dict] = []
    zendesk_page = 1
    hit_cap = False

    while len(matched) < skip + page_size:
        if zendesk_page > MAX_ZENDESK_PAGES:
            hit_cap = True
            break

        response = search_zendesk_tickets(
            created_after=created_after,
            created_before=created_before,
            agent_ids=agent_ids,
            page=zendesk_page,
            per_page=ZENDESK_PAGE_SIZE,
        )
        results = response.get("results", [])
        matched.extend(t for t in results if ticket_matches_tags(t, required_tags))

        if not response.get("next_page"):
            break
        zendesk_page += 1

    page_slice = matched[skip: skip + page_size]

    return {
        "tickets": [format_ticket(t) for t in page_slice],
        "page": page,
        "page_size": page_size,
        "has_more": len(matched) > skip + page_size or hit_cap,
    }


def format_ticket(ticket: dict) -> dict:
    return {
        "id": ticket["id"],
        "subject": ticket.get("subject"),
        "status": ticket.get("status"),
        "created_at": ticket.get("created_at"),
        "updated_at": ticket.get("updated_at"),
        "assignee_id": ticket.get("assignee_id"),
        "requester_id": ticket.get("requester_id"),
        "tags": ticket.get("tags", []),
        "priority": ticket.get("priority"),
    }