import sys, os
import re

# Only use vendor folder in Lambda (not locally)
# if os.environ.get("AWS_EXECUTION_ENV"):  # This env var only exists in Lambda
#     sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))

import json
import time
import concurrent.futures
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import requests
from newspaper import Article
from ddgs import DDGS


INCLUDE_SITES = [
    "reddit.com",
    "stackoverflow.com",
    "wikipedia.org",
    "medium.com",
    "github.com",
    "dev.to",
]


class ArticleResponse(BaseModel):
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    success: bool
    error: Optional[str] = None
    processing_time: float


class Page(BaseModel):
    url: str
    title: Optional[str] = None
    content: Optional[str] = None


def _build_query(user_query: str) -> str:
    site_query = " OR ".join(f"site:{site}" for site in INCLUDE_SITES)
    return f"{user_query} ({site_query})"


def clean_text_for_llm(text: str) -> str:
    """Clean text to be LLM-friendly by removing unwanted characters and formatting."""
    if not text:
        return ""

    # Remove excessive newlines (more than 2 consecutive)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Replace tabs with spaces
    text = text.replace("\t", " ")

    # Remove excessive spaces (more than 2 consecutive)
    text = re.sub(r" {3,}", " ", text)

    # Remove common code artifacts and formatting marks
    text = re.sub(r"```[\s\S]*?```", "", text)  # Remove code blocks
    text = re.sub(r"`[^`]*`", "", text)  # Remove inline code

    # Remove special characters that don't add meaning
    text = re.sub(r"[•●○◦▪▫■□‣⁃]", "", text)  # Bullet points
    text = re.sub(r"[─━│┃┌┐└┘├┤┬┴┼]", "", text)  # Box drawing

    # Clean up whitespace
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{2,}", "\n\n", text)  # Max 2 newlines

    # Remove leading/trailing whitespace
    text = text.strip()

    return text


def search_urls(query: str, max_results: int = 10) -> List[str]:
    try:
        with DDGS() as ddgs:
            results = []
            for result in ddgs.text(query, max_results=max_results):
                results.append(result["href"])
            return results
    except Exception as e:
        print(f"Error searching: {e}")
        return []


def fetch_article_streaming(url: str, max_length: int = 7000) -> ArticleResponse:
    start_time = time.time()

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; FastAPI-Scraper/1.0)"}

        response = requests.get(url, headers=headers, stream=True, timeout=5)
        response.raise_for_status()

        content_chunks = []
        total_length = 0
        max_download_size = max(max_length * 3, 1024 * 100)

        for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
            if chunk:
                content_chunks.append(chunk)
                total_length += len(chunk)

                if total_length >= max_download_size:
                    break

        if not content_chunks:
            raise Exception("No content received from URL")

        # check if the response is an error page
        if total_length < 100:
            raise Exception(
                f"Content too small ({total_length} chars), might be an error page"
            )

        html_content = "".join(content_chunks)

        article = Article(url)
        article.set_html(html_content)
        article.parse()

        # Clean the content for LLM consumption
        content = clean_text_for_llm(article.text)
        title = clean_text_for_llm(article.title) if article.title else None

        if content and len(content) > max_length:
            content = content[:max_length] + "..."

        processing_time = time.time() - start_time

        return ArticleResponse(
            url=url,
            title=title,
            content=content,
            success=True,
            error=None,
            processing_time=processing_time,
        )
    except Exception as e:
        processing_time = time.time() - start_time

        return ArticleResponse(
            url=url,
            title=None,
            content=None,
            success=False,
            error=str(e),
            processing_time=processing_time,
        )


def lambda_handler(event, context):
    try:
        print(json.dumps(event))

        query_params = event.get("queryStringParameters") or {}
        user_query = query_params.get("query")
        print("query ::", user_query)

        if not user_query:
            return _response(
                400,
                {"status": "error", "message": "query is required"},
            )

        full_query = _build_query(user_query)
        print("full_query ::", full_query)

        # use (ddgs) to get URLs
        web_pages = search_urls(full_query, max_results=10)

        if not web_pages:
            raise RuntimeError("No web pages found for the query")

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {
                executor.submit(fetch_article_streaming, url): url for url in web_pages
            }

            articles = []
            for future in concurrent.futures.as_completed(future_to_url):
                result = future.result()
                articles.append(result)

        url_to_article = {article.url: article for article in articles}
        pages = []

        for url in web_pages:
            if url in url_to_article:
                article = url_to_article[url]
                # Only include pages that successfully extracted content
                if article.content:
                    pages.append(
                        Page(
                            url=article.url,
                            title=article.title,
                            content=article.content,
                        )
                    )

        pages_dict = [page.model_dump() for page in pages]

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "success",
                    "pages": pages_dict,
                }
            ),
        }
    except Exception as e:
        print("Error:", str(e))
        return _response(
            500,
            {"status": "failed", "message": "Something went wrong"},
        )


def _response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "body": json.dumps(payload),
    }
