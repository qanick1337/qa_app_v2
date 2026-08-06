import httpx
import os
import json
import sys
from dotenv import  load_dotenv
from bs4 import BeautifulSoup
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.chunker import chunk_text

load_dotenv()

ZENDESK_DOMAIN = os.getenv("ZENDESK_DOMAIN")
ZENDESK_TOKEN = os.getenv("ZENDESK_TOKEN")
ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL")
LOCALE = "uk-ua"

CONFLUENCE_DOMAIN = os.getenv("CONFLUENCE_DOMAIN")
CONFLUENCE_TOKEN = os.getenv("CONFLUENCE_TOKEN")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")

internal_sections_id = {
    "SERVER\\CLOUD": 24883831794716,
    "SENET ID": 28377706634268,
    "BUNDLE\\ELAUNCHER": 24704786083100,
    "IDM (SSO)": 23608960282524,
    "Game Update": 12189427098652,
    "CONTROLLER\\SENET TV APPLICATION": 23830010350492,
    "CHECKBOX":24648504609308,
    "Налаштування платіжних систем": 9711371463196,
    "SMS-service": 9711319839132,
    "Інструкції АПП (Django)": 9709108818332,
    "Гайди SENET Boot": 9709313884700,
    "Сапноути Сервер": 4404391814418
}

public_section_id = {
    "Чекліст для ігрового клубу": 22733877562268,
    "Керування клубом і тарифікація":360005265780,
    "Карта клубу":20425235578524,
    "Ігри та застосунки":20696304828572,
    "Клієнтський інтерфейс Shell":14174897259420,
    "Система, аналітика та інтеграції":360005265740,
    "E-launcher":24354942244124,
    "Усунення несправностей в роботі клубу":23424461497116,
    "FAQ":24353995039260,
    "Встановлення SENET Boot":4407569111058,
    "Системні вимоги":4406990049938,
    "Налаштування BIOS":13672068703900,
    "Керування SENET Boot":4407576450578,
    "Усунення несправностей SENET BOOT":10914649996572,
    "Змінопис":12473806172444,
    "Версії інсталятора лаунчера":360005673760,
    "Реліз-ноути SENET Boot":4405356081426,
    "Game Update":25589868967708,
    "Бонусна система":24353932658460,
    "Бронювання":360005516299,
    "Онлайн-платежі та поповнення":24216846716700,
    "Консолі та контролери":360005311419,
    "Мобільний застосунок":24572820615196,
}


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True)

def fetch_single_zendesk_article(article_id) -> dict:
    url = f"https://{ZENDESK_DOMAIN}/api/v2/help_center/{LOCALE}/articles/{article_id}.json"

    try:
        with httpx.Client() as client:
            response = client.get(
                url,
                auth=(f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN),
            )
            response.raise_for_status()
            data = response.json()

            article = data.get("article")

            article = {
                "id": article["id"],
                "title": article["title"],
                "body": clean_html(article["body"]),
                "url": article["html_url"],
                "section_id": article["section_id"],
            }

    except httpx.HTTPStatusError as error:
        if error.response.status_code == 401:
            print("Error 401: Auth is required. Перевірте правильність ZENDESK_EMAIL та ZENDESK_TOKEN.")
        elif error.response.status_code == 403:
            print("Error 403: Access is denied. Перевірте права токена або доступ до цієї статті.")
        else:
            print(f"HTTP error: {error.response.status_code}")
    except httpx.ConnectError as exc:
        print(f"Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"Error: {error}")

    return article

def fetch_zendesk_section_name(section_id):
    url = f"https://{ZENDESK_DOMAIN}/api/v2/help_center/{LOCALE}/sections/{section_id}"

    try:
        with httpx.Client() as client:
            response = client.get(
                url,
                auth=(f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN),
            )
            response.raise_for_status()

            data = response.json()

    except httpx.ConnectError as exc:
        print(f"Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"Error: {error}")

    section = data.get("section", data)
    return section["name"]

def fetch_zendesk_article_section(section_id):

    articles = []
    url = f"https://{ZENDESK_DOMAIN}/api/v2/help_center/{LOCALE}/sections/{section_id}/articles.json"

    try:
        with httpx.Client() as client:
            while url:
                try:
                    response = client.get(
                        url,
                        auth=(f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN),
                    )
                    response.raise_for_status()

                    data = response.json()

                except httpx.HTTPStatusError as error:
                    if error.response.status_code == 401:
                        print("Error 401: Auth is required")
                    elif error.response.status_code == 403:
                        print("Error 403: Acces is denied")
                    else:
                        print(f"HTTP error: {error.response.status_code}")
                    raise

                for article in data["articles"]:
                    if article["draft"]:
                        continue
                    articles.append({
                        "id": article["id"],
                        "title": article["title"],
                        "body": clean_html(article["body"]),
                        "url": article["html_url"],
                        "section_id": article["section_id"],
                        "section":fetch_zendesk_section_name(article["section_id"])
                    })

                url = data.get("next_page")
    except httpx.ConnectError as exc:
        print(f"Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"Error: {error}")

    return articles

def fetch_zendesk_articles() -> list[dict]:
    articles = []
    url = f"https://{ZENDESK_DOMAIN}/api/v2/help_center/{LOCALE}/articles.json?query=senet+id&per_page=30"

    try:
        with httpx.Client() as client:
            while url:
                try:
                    response = client.get(
                        url,
                        auth=(f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN),
                    )
                    response.raise_for_status()

                    data = response.json()

                except httpx.HTTPStatusError as error:
                    if error.response.status_code == 401:
                        print("Error 401: Auth is required")
                    elif error.response.status_code == 403:
                        print("Error 403: Acces is denied")
                    else:
                        print(f"HTTP error: {error.response.status_code}")
                    raise
                


                for article in data["articles"]:
                    if article["draft"]:
                        continue
                    articles.append({
                        "id": article["id"],
                        "title": article["title"],
                        "body": clean_html(article["body"]),
                        "url": article["html_url"],
                        "section_id": article["section_id"],
                    })

                url = data.get("next_page")  
    except httpx.ConnectError as exc:
        print(f"Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"Error: {error}")

    return articles

def fetch_single_zendesk_ticket_conversation(ticket_id: int):
    url = f"https://{ZENDESK_DOMAIN}/api/v2/tickets/{ticket_id}/comments.json"
    comments_list = []

    try:
        with httpx.Client() as client:
            response = client.get(
                url,
                auth=(f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN),
            )
            response.raise_for_status()
            data = response.json()

            comments = data.get("comments", [])
            
            for comment in comments:
                comments_list.append({
                    "id": comment["id"],
                    "author_id": comment["author_id"],
                    "body": comment["body"], 
                    "created_at": comment["created_at"],
                    "public": comment["public"]
                })

    except httpx.HTTPStatusError as error:
        if error.response.status_code == 401:
            print("Error 401: Auth is required.")
        elif error.response.status_code == 403:
            print("Error 403: Access is denied.")
        elif error.response.status_code == 404:
            print(f"Error 404: Ticket {ticket_id} not found.")
        else:
            print(f"HTTP error: {error.response.status_code}")
    except httpx.ConnectError as exc:
        print(f"Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"Error: {error}")

    return comments_list

def fetch_single_zendesk_ticket(ticket_id: int):
    url = f"https://{ZENDESK_DOMAIN}/api/v2/tickets/{ticket_id}/comments.json"

    try:
        with httpx.Client() as client:
            response = client.get(
                url,
                auth=(f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN),
            )
            response.raise_for_status()
            data = response.json()

    except httpx.HTTPStatusError as error:
        if error.response.status_code == 401:
            print("Error 401: Auth is required.")
        elif error.response.status_code == 403:
            print("Error 403: Access is denied.")
        elif error.response.status_code == 404:
            print(f"Error 404: Ticket {ticket_id} not found.")
        else:
            print(f"HTTP error: {error.response.status_code}")
    except httpx.ConnectError as exc:
        print(f"Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"Error: {error}")

    return data

def fetch_space_confluence(space_id: int):
    url = f"https://{CONFLUENCE_DOMAIN}/wiki/rest/api/space/{space_id}"

    try:
        with httpx.Client() as client:
            response = client.get(
                url,
                auth=(CONFLUENCE_EMAIL, CONFLUENCE_TOKEN),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()

            return response.json()

    except httpx.HTTPStatusError as error:
        if error.response.status_code == 401:
            print("Error 401: Auth is required. Перевірте правильність CONFLUENCE_EMAIL and CONFLUENCE API TOKEN.")
        elif error.response.status_code == 403:
            print("Error 403: Access is denied.")
        else:
            print(f"HTTP error: {error.response.status_code}")
    except httpx.ConnectError as exc:
        print(f"Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"Error: {error}")

def fetch_confluence_page_title(page_id: str) -> str | None:
    url = f"https://{CONFLUENCE_DOMAIN}/wiki/api/v2/pages/{page_id}"

    try:
        with httpx.Client() as client:
            response = client.get(
                url,
                auth=(CONFLUENCE_EMAIL, CONFLUENCE_TOKEN),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()["title"]

    except Exception:
        return None


def fetch_confluence_article(article_id: str, parent_id: str | None = None, depth: int = 0) -> dict:
    url = f"https://{CONFLUENCE_DOMAIN}/wiki/api/v2/pages/{article_id}?body-format=storage"

    print(f"[fetch_confluence_article] depth={depth} article_id={article_id} parent_id={parent_id}: стягування статті...")

    try:
        with httpx.Client() as client:
            response = client.get(
                url,
                auth=(CONFLUENCE_EMAIL, CONFLUENCE_TOKEN),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            article_parent_id = data["parentId"]

            # section - назва батьківської статті, отримана за parentId
            return {
                "id": data["id"],
                "title": data["title"],
                "body": clean_html(data["body"]["storage"]["value"]),
                "url": str(data["_links"]["base"]+data["_links"]["webui"]),
                "section": fetch_confluence_page_title(article_parent_id) if article_parent_id else None,
            }

    except httpx.HTTPStatusError as error:
        print(f"[fetch_confluence_article] depth={depth} article_id={article_id} parent_id={parent_id}: HTTP error {error.response.status_code} on {url}")
    except httpx.ConnectError as exc:
        print(f"[fetch_confluence_article] depth={depth} article_id={article_id} parent_id={parent_id}: Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"[fetch_confluence_article] depth={depth} article_id={article_id} parent_id={parent_id}: Error: {error}")

    return {}


def fetch_confluence_article_as_folder(article_id: str, article: dict | None = None, parent_id: str | None = None, depth: int = 0) -> list[dict]:
    articles = []
    url = f"https://{CONFLUENCE_DOMAIN}/wiki/api/v2/pages/{article_id}/direct-children"

    print(f"[fetch_confluence_article_as_folder] depth={depth} article_id={article_id} parent_id={parent_id}: пошук дочірніх статей...")

    try:
        with httpx.Client() as client:
            response = client.get(
                url,
                auth=(CONFLUENCE_EMAIL, CONFLUENCE_TOKEN),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            if len(data["results"]) == 0:
                return articles


            for child in data["results"]:
                if child.get("status") == "draft":
                    continue

                if child.get("type") == "folder":
                    articles.extend(fetch_confluence_folder(child["id"], parent_id=article_id, depth=depth + 1))
                    continue

                if child.get("type") != "page":
                    continue

                child_article = fetch_confluence_article(child["id"], parent_id=article_id, depth=depth + 1)

                if child_article:
                    articles.append(child_article)

                child_descendants = fetch_confluence_article_as_folder(child["id"], article=child_article, parent_id=article_id, depth=depth + 1)
                articles.extend(child_descendants)

            return articles

    except httpx.HTTPStatusError as error:
        print(f"[fetch_confluence_article_as_folder] depth={depth} article_id={article_id} parent_id={parent_id}: HTTP error {error.response.status_code} on {url}")
    except httpx.ConnectError as exc:
        print(f"[fetch_confluence_article_as_folder] depth={depth} article_id={article_id} parent_id={parent_id}: Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"[fetch_confluence_article_as_folder] depth={depth} article_id={article_id} parent_id={parent_id}: Error: {error}")

    return articles

def fetch_confluence_folder(folder_id: int, parent_id: str | None = None, depth: int = 0):
    articles = []
    url = f"https://{CONFLUENCE_DOMAIN}/wiki/api/v2/folders/{folder_id}/direct-children"

    try:
        with httpx.Client() as client:
            response = client.get(
                url,
                auth=(CONFLUENCE_EMAIL, CONFLUENCE_TOKEN),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            for child in data["results"]:
                if child.get("status") == "draft":
                    continue

                if child.get("type") == "folder":
                    articles.extend(fetch_confluence_folder(child["id"], parent_id=folder_id, depth=depth + 1))
                    continue

                if child.get("type") != "page":
                    continue

                child_article = fetch_confluence_article(child["id"], parent_id=folder_id, depth=depth + 1)

                if child_article:
                    articles.append(child_article)

                articles.extend(fetch_confluence_article_as_folder(child["id"], article=child_article, parent_id=folder_id, depth=depth + 1))

            return articles

    except httpx.HTTPStatusError as error:
        print(f"[fetch_confluence_folder] depth={depth} folder_id={folder_id} parent_id={parent_id}: HTTP error {error.response.status_code} on {url}")
    except httpx.ConnectError as exc:
        print(f"[fetch_confluence_folder] depth={depth} folder_id={folder_id} parent_id={parent_id}: Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"[fetch_confluence_folder] depth={depth} folder_id={folder_id} parent_id={parent_id}: Error: {error}")

    return {}

def to_json(dictionary, filename):
    path = Path(filename)
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")

    with path.open("w", encoding="utf-8") as fp:
        json.dump(dictionary, fp, sort_keys=True, indent=4, ensure_ascii=False)
 