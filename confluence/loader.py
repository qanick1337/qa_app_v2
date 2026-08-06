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
from services.clean_html import clean_html


load_dotenv()

CONFLUENCE_DOMAIN = os.getenv("CONFLUENCE_DOMAIN")
CONFLUENCE_TOKEN = os.getenv("CONFLUENCE_TOKEN")
CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")

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


def fetch_confluence_page(page_id: str, parent_id: str | None = None, depth: int = 0) -> dict:
    url = f"https://{CONFLUENCE_DOMAIN}/wiki/api/v2/pages/{page_id}?body-format=storage"

    print(f"[fetch_confluence_article] depth={depth} article_id={page_id} parent_id={parent_id}: стягування статті...")

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
        print(f"[fetch_confluence_article] depth={depth} article_id={page_id} parent_id={parent_id}: HTTP error {error.response.status_code} on {url}")
    except httpx.ConnectError as exc:
        print(f"[fetch_confluence_article] depth={depth} article_id={page_id} parent_id={parent_id}: Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"[fetch_confluence_article] depth={depth} article_id={page_id} parent_id={parent_id}: Error: {error}")

    return {}


def fetch_confluence_page_as_folder(page_id: str, article: dict | None = None, parent_id: str | None = None, depth: int = 0) -> list[dict]:
    articles = []
    url = f"https://{CONFLUENCE_DOMAIN}/wiki/api/v2/pages/{page_id}/direct-children"

    print(f"[fetch_confluence_article_as_folder] depth={depth} article_id={page_id} parent_id={parent_id}: пошук дочірніх статей...")

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
                    articles.extend(fetch_confluence_folder(child["id"], parent_id=page_id, depth=depth + 1))
                    continue

                if child.get("type") != "page":
                    continue

                child_article = fetch_confluence_page(child["id"], parent_id=page_id, depth=depth + 1)

                if child_article:
                    articles.append(child_article)

                child_descendants = fetch_confluence_page_as_folder(child["id"], article=child_article, parent_id=page_id, depth=depth + 1)
                articles.extend(child_descendants)

            return articles

    except httpx.HTTPStatusError as error:
        print(f"[fetch_confluence_article_as_folder] depth={depth} article_id={page_id} parent_id={parent_id}: HTTP error {error.response.status_code} on {url}")
    except httpx.ConnectError as exc:
        print(f"[fetch_confluence_article_as_folder] depth={depth} article_id={page_id} parent_id={parent_id}: Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"[fetch_confluence_article_as_folder] depth={depth} article_id={page_id} parent_id={parent_id}: Error: {error}")

    return articles

def fetch_confluence_folder(folder_id: int, parent_id: str | None = None, depth: int = 0) -> list[dict]:
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

                child_article = fetch_confluence_page(child["id"], parent_id=folder_id, depth=depth + 1)

                if child_article:
                    articles.append(child_article)

                articles.extend(fetch_confluence_page_as_folder(child["id"], article=child_article, parent_id=folder_id, depth=depth + 1))

            return articles

    except httpx.HTTPStatusError as error:
        print(f"[fetch_confluence_folder] depth={depth} folder_id={folder_id} parent_id={parent_id}: HTTP error {error.response.status_code} on {url}")
    except httpx.ConnectError as exc:
        print(f"[fetch_confluence_folder] depth={depth} folder_id={folder_id} parent_id={parent_id}: Network or DNS error occurred: {exc}")
    except Exception as error:
        print(f"[fetch_confluence_folder] depth={depth} folder_id={folder_id} parent_id={parent_id}: Error: {error}")

    return articles
