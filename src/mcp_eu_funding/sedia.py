"""Async client for the EU Funding & Tenders Portal search API (SEDIA). Public, no API key beyond the literal 'SEDIA'."""
from __future__ import annotations

import asyncio
import html
import json
import re
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

import httpx

SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
FACET_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/facet"
USER_AGENT = "mcp-eu-funding/0.1 (+https://github.com/olegsher-ds-2025/mcp-eu-funding)"

TYPES = {"tender": "0", "grant": "1", "europeaid": "2", "cascade": "8"}
TYPE_NAMES = {"0": "Tender", "1": "Grant topic", "2": "Call for proposals (EuropeAid)", "8": "Cascade funding call"}
STATUS = {"forthcoming": "31094501", "open": "31094502", "closed": "31094503"}
STATUS_NAMES = {v: k for k, v in STATUS.items()}


class SediaError(RuntimeError):
    pass


def _form(query: dict, languages=("en",), sort: dict | None = None) -> dict:
    files = {"query": (None, json.dumps(query), "application/json"),
             "languages": (None, json.dumps(list(languages)), "application/json")}
    if sort:
        files["sort"] = (None, json.dumps(sort), "application/json")
    return files


async def _post(url: str, params: dict, files: dict, retries: int = 4) -> dict:
    last: Exception | None = None
    async with httpx.AsyncClient(timeout=45, headers={"User-Agent": USER_AGENT}) as c:
        for i in range(retries):
            try:
                r = await c.post(url, params=params, files=files)
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as exc:  # the API intermittently drops connections
                last = exc
                await asyncio.sleep(1.5 * (i + 1))
    raise SediaError(f"EU Funding & Tenders API unavailable: {last}")


async def search(must: list[dict], text: str = "***", page: int = 1, size: int = 20,
                 sort: dict | None = None) -> dict:
    """Run a search. `must` is a list of Elasticsearch-style clauses (at least one required)."""
    params = {"apiKey": "SEDIA", "text": text or "***", "pageSize": max(1, min(size, 100)), "pageNumber": max(1, page)}
    return await _post(SEARCH_URL, params, _form({"bool": {"must": must}}, sort=sort))


_FACET_CACHE: dict[str, tuple[float, dict]] = {}


async def facets(must: list[dict], ttl: float = 6 * 3600) -> dict[str, list[dict]]:
    """Facet counts + human labels for the codes used in results (programmes, destinations, missions...)."""
    key = json.dumps(must, sort_keys=True)
    hit = _FACET_CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    data = await _post(FACET_URL, {"apiKey": "SEDIA", "text": "***"}, _form({"bool": {"must": must}}))
    out = {f.get("name"): [{"code": v.get("rawValue"), "name": (v.get("value") or "").strip(), "count": v.get("count")}
                           for v in f.get("values", [])] for f in data.get("facets", [])}
    _FACET_CACHE[key] = (time.time(), out)
    return out


def iso(d: str) -> str:
    """'2026-11-18' -> SEDIA range format."""
    return datetime.fromisoformat(d[:10]).strftime("%Y-%m-%dT00:00:00.000+0000")


def first(m: dict, key: str) -> Any:
    v = m.get(key)
    if isinstance(v, list):
        return v[0] if v else None
    return v


def as_list(m: dict, key: str) -> list:
    v = m.get(key)
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def jload(v: Any) -> Any:
    if not v:
        return None
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


class _Text(HTMLParser):
    BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "tr", "ul", "ol"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(s: str | None, limit: int | None = None) -> str | None:
    if not s:
        return None
    p = _Text()
    p.feed(s)
    txt = html.unescape("".join(p.parts))
    txt = re.sub(r"[ \t\xa0]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n\n", txt).strip()
    if limit and len(txt) > limit:
        txt = txt[:limit].rsplit(" ", 1)[0] + " …"
    return txt


def next_deadline(dates: list[str]) -> tuple[str | None, bool]:
    """Return (next deadline >= now or last deadline, is_future)."""
    now = datetime.now(UTC)
    parsed = []
    for d in dates:
        try:
            parsed.append(datetime.strptime(d[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC))
        except (TypeError, ValueError):
            continue
    if not parsed:
        return None, False
    future = sorted(x for x in parsed if x >= now)
    if future:
        return future[0].strftime("%Y-%m-%d %H:%M UTC"), True
    return max(parsed).strftime("%Y-%m-%d %H:%M UTC"), False


def budget(m: dict) -> dict | None:
    bo = jload(first(m, "budgetOverview")) or {}
    rows = []
    for acts in (bo.get("budgetTopicActionMap") or {}).values():
        for a in acts:
            years = a.get("budgetYearMap") or {}
            rows.append({
                "action": a.get("action"),
                "budget_eur": sum(v for v in years.values() if isinstance(v, (int, float))) or None,
                "by_year": years or None,
                "expected_grants": a.get("expectedGrants"),
                "min_contribution_eur": a.get("minContribution"),
                "max_contribution_eur": a.get("maxContribution"),
                "opening": a.get("plannedOpeningDate"),
                "deadline_model": a.get("deadlineModel"),
                "deadlines": a.get("deadlineDates"),
            })
    if not rows:
        b = first(m, "budget")
        return {"total_eur": float(b) if b and str(b).replace(".", "").isdigit() else None} if b else None
    total = sum(r["budget_eur"] or 0 for r in rows) or None
    return {"total_eur": total, "actions": rows}


def meta() -> dict:
    return {
        "source": "EU Funding & Tenders Portal (European Commission) — SEDIA search API",
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "attribution": "© European Union. Unofficial tool; always confirm details on the official topic page before applying.",
    }
