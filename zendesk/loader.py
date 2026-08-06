import httpx
import os
import json
import sys
from dotenv import  load_dotenv

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.chunker import chunk_text
from services.clean_html import clean_html

load_dotenv()

ZENDESK_DOMAIN = os.getenv("ZENDESK_DOMAIN")
ZENDESK_TOKEN = os.getenv("ZENDESK_TOKEN")
ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL")
LOCALE = "uk-ua"

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




def to_json(dictionary, filename):
    path = Path(filename)
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")

    with path.open("w", encoding="utf-8") as fp:
        json.dump(dictionary, fp, sort_keys=True, indent=4, ensure_ascii=False)
 