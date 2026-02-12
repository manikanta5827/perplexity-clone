import os, json, time, re, requests, concurrent.futures
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from newspaper import Article
from ddgs import DDGS

INCLUDE_SITES = [
    "reddit.com",
    "stackoverflow.com",
    "wikipedia.org",
    "medium.com",
    "docs.aws.amazon.com",
    "dev.to",
]

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}

# ---------- Models ----------


class ArticleResponse(BaseModel):
    url: str
    title: Optional[str]
    content: Optional[str]
    success: bool
    error: Optional[str]
    processing_time: float


class Page(BaseModel):
    url: str
    title: Optional[str]
    content: Optional[str]


# ---------- Helpers ----------


def _response(code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {"statusCode": code, "body": json.dumps(body), "headers": CORS_HEADERS}


def _build_query(q: str) -> str:
    return f"{q} ({' OR '.join(f'site:{s}' for s in INCLUDE_SITES)})"


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"```[\s\S]*?```|`[^`]*`", "", text)
    text = re.sub(r"[•●○◦▪▫■□‣⁃─━│┃┌┐└┘├┤┬┴┼]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text.replace("\t", " "))
    return "\n".join(l.strip() for l in text.splitlines()).strip()


def search_urls(query: str, limit: int = 5) -> List[str]:
    try:
        with DDGS() as d:
            return [r["href"] for r in d.text(query, max_results=limit)]
    except Exception:
        return []


def fetch_article(url: str, max_len: int = 7000) -> ArticleResponse:
    start = time.time()
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        r.raise_for_status()

        article = Article(url)
        article.set_html(r.text)
        article.parse()

        content = clean_text(article.text)[:max_len]
        title = clean_text(article.title)

        if not content or len(content) < 100:
            raise ValueError("Invalid article content")

        return ArticleResponse(
            url=url,
            title=title,
            content=content,
            success=True,
            error=None,
            processing_time=time.time() - start,
        )
    except Exception as e:
        return ArticleResponse(
            url=url,
            title=None,
            content=None,
            success=False,
            error=str(e),
            processing_time=time.time() - start,
        )


# ---------- LLM ----------


def generate_llm_response(topic: str, pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"status": False}

    articles = [
        {"title": p.get("title"), "content": p.get("content")[:5000]} for p in pages
    ]

    prompt = f"""
        You are an expert research analyst.

        STRICT RULES:
        - Use ONLY the provided articles
        - No external knowledge
        - No hallucination

        Task:
        Synthesize all articles about "{topic}" into ONE summary.

        Output:
        - 2-4 paragraphs based on context
        - 1–3 sentences each
        - Neutral, factual
        - No markdown, no references

        Articles:
        {json.dumps(articles)}
        """

    r = requests.post(
        "https://api.groq.com/openai/v1/responses",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "openai/gpt-oss-120b", "input": prompt},
        timeout=30,
    )
    r.raise_for_status()

    try:
        text = r.json()["output"][1]["content"][0]["text"]
        return {"status": True, "data": text.strip()}
    except Exception:
        return {"status": False}


# ---------- Lambda ----------
def lambda_handler(event, context):
    http_method = event.get("httpMethod") or event.get("requestContext", {}).get(
        "http", {}
    ).get("method")
    if http_method == "OPTIONS":
        return {"statusCode": 204, "headers": CORS_HEADERS, "body": ""}

    try:
        q = (event.get("queryStringParameters") or {}).get("query")
        if not q:
            return _response(400, {"status": "error", "message": "query is required"})

        urls = search_urls(_build_query(q))
        if not urls:
            return _response(500, {"status": "failed", "message": "No results found"})

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            results = list(ex.map(fetch_article, urls))

        pages = [
            Page(url=r.url, title=r.title, content=r.content).model_dump()
            for r in results
            if r.success and r.content
        ]

        if not pages:
            return _response(500, {"status": "failed", "message": "Scraping failed"})

        llm = generate_llm_response(q, pages)
        if not llm.get("status"):
            return _response(500, {"status": "failed", "message": "LLM failed"})

        return _response(200, {"status": "success", "data": llm["data"]})

    except Exception:
        return _response(500, {"status": "failed", "message": "Internal error"})
