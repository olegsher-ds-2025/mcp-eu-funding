"""mcp-eu-funding — EU Funding & Tenders Portal (Horizon Europe, Digital Europe, LIFE, EIC, Erasmus+, EDF …)
for AI assistants: search open and forthcoming calls, read full topic conditions and budgets, track deadlines,
browse programmes and EU tenders. Live data from the official SEDIA search API (no key)."""
from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta

from fastmcp import FastMCP

from . import __version__
from .sedia import (
    STATUS,
    STATUS_NAMES,
    TYPE_NAMES,
    TYPES,
    as_list,
    budget,
    facets,
    first,
    html_to_text,
    iso,
    jload,
    meta,
    next_deadline,
    search,
)

mcp = FastMCP(
    "mcp-eu-funding",
    version=__version__,
    instructions=(
        "EU funding opportunities from the official Funding & Tenders Portal. Use search_funding to find calls "
        "(filter by programme such as HORIZON, DIGITAL, LIFE, EDF, ERASMUS, by status and deadline), get_topic for "
        "full conditions/budget of one topic, upcoming_deadlines for what closes soon, call_topics for all topics "
        "in one call, list_programmes to discover programme codes, search_tenders for EU procurement. "
        "Israel is associated to Horizon Europe, so Israeli entities can usually apply on equal terms — always "
        "check the topic's eligibility conditions."
    ),
)


async def _programme_code(programme: str | None) -> str | None:
    """Accept a code ('43108390'), abbreviation ('HORIZON') or name fragment ('Digital Europe')."""
    if not programme:
        return None
    p = programme.strip()
    if p.isdigit():
        return p
    fac = await facets([{"terms": {"type": ["0", "1", "2", "8"]}}])
    items = fac.get("frameworkProgramme", [])
    up = p.upper()
    for it in items:
        if f"({up})" in (it["name"] or "").upper():
            return it["code"]
    for it in items:
        if up in (it["name"] or "").upper():
            return it["code"]
    raise ValueError(f"Unknown programme '{programme}'. Call list_programmes to see available programmes.")


def _status_codes(status: str) -> list[str]:
    s = status.lower().replace(" ", "_")
    if s in ("open_or_forthcoming", "active", "any_active"):
        return [STATUS["open"], STATUS["forthcoming"]]
    if s == "all":
        return list(STATUS.values())
    if s not in STATUS:
        raise ValueError("status must be open, forthcoming, closed, open_or_forthcoming or all")
    return [STATUS[s]]


def _summary(r: dict, programme_names: dict[str, str]) -> dict:
    m = r.get("metadata", {})
    typ = first(m, "type")
    dl, future = next_deadline(as_list(m, "deadlineDate"))
    b = budget(m)
    prog = first(m, "frameworkProgramme")
    out = {
        "identifier": first(m, "identifier"),
        "title": (first(m, "title") or r.get("summary") or "").strip()[:300],
        "kind": TYPE_NAMES.get(typ, typ),
        "status": STATUS_NAMES.get(first(m, "status"), first(m, "status")),
        "programme": programme_names.get(prog, prog),
        "call": first(m, "callIdentifier"),
        "opens": (first(m, "startDate") or "")[:10] or None,
        "next_deadline": dl,
        "deadline_passed": (dl is not None and not future) or None,
        "deadline_model": first(m, "deadlineModel"),
        "type_of_action": first(m, "typesOfAction"),
        "budget_eur": (b or {}).get("total_eur"),
        "tags": as_list(m, "tags")[:8] or None,
        "url": first(m, "url") or r.get("url"),
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


async def _names() -> dict[str, str]:
    try:
        fac = await facets([{"terms": {"type": ["0", "1", "2", "8"]}}])
        return {i["code"]: i["name"] for i in fac.get("frameworkProgramme", [])}
    except Exception:  # noqa: BLE001
        return {}


@mcp.tool
async def search_funding(query: str = "", programme: str = "", status: str = "open_or_forthcoming",
                         kinds: list[str] | None = None, deadline_from: str = "", deadline_to: str = "",
                         cross_cutting: str = "", include_past_deadlines: bool = False,
                         limit: int = 20, page: int = 1) -> dict:
    """Search EU funding opportunities (grant topics, cascade/FSTP calls, EuropeAid calls).

    Args:
        query: free text, e.g. "artificial intelligence healthcare", "hydrogen", "quantum".
        programme: "HORIZON", "DIGITAL", "LIFE", "EDF", "ERASMUS+", "CREA", "SMP", "EU4H", "CEF"… (see list_programmes).
        status: open, forthcoming, closed, open_or_forthcoming (default) or all.
        kinds: any of "grant" (programme topics), "cascade" (third-party funding / FSTP), "europeaid". Default: all three.
        deadline_from / deadline_to: YYYY-MM-DD bounds on the deadline.
        cross_cutting: priority code such as "AI", "DigitalAgenda", "EC-WORLD" (international cooperation).
        include_past_deadlines: the portal keeps some calls marked "open" after their last deadline; by default
            only opportunities with a deadline today or later are returned.
        limit / page: pagination (max 100 per page).
    Results are sorted by deadline (soonest first).
    """
    kinds = kinds or ["grant", "cascade", "europeaid"]
    bad = [k for k in kinds if k not in ("grant", "cascade", "europeaid")]
    if bad:
        raise ValueError(f"Unknown kinds {bad}; use grant, cascade, europeaid (tenders: use search_tenders)")
    must: list[dict] = [{"terms": {"type": [TYPES[k] for k in kinds]}}, {"terms": {"status": _status_codes(status)}}]
    code = await _programme_code(programme)
    if code:
        must.append({"terms": {"frameworkProgramme": [code]}})
    if cross_cutting:
        must.append({"terms": {"crossCuttingPriorities": [cross_cutting]}})
    if not deadline_from and not include_past_deadlines and status.lower() != "closed":
        deadline_from = date.today().isoformat()
    if deadline_from or deadline_to:
        rng = {}
        if deadline_from:
            rng["gte"] = iso(deadline_from)
        if deadline_to:
            rng["lte"] = iso(deadline_to)
        must.append({"range": {"deadlineDate": rng}})
    data, names = await asyncio.gather(
        search(must, text=query or "***", page=page, size=limit, sort={"field": "deadlineDate", "order": "ASC"}),
        _names())
    results = [_summary(r, names) for r in data.get("results", [])]
    return {"total": data.get("totalResults", 0), "page": page, "results": results, **meta()}


@mcp.tool
async def get_topic(identifier: str, max_chars: int = 6000) -> dict:
    """Full details of one topic/call by identifier (e.g. "HORIZON-CL4-2027-01-MAT-PROD-22"): description
    (expected outcome, scope), eligibility & admissibility conditions, budget per action, deadlines, type of
    action, latest updates, support contacts and submission links."""
    ident = identifier.strip()
    data = await search([{"terms": {"identifier": [ident]}}], size=10)
    hits = [r for r in data.get("results", []) if (first(r.get("metadata", {}), "identifier") or "").upper() == ident.upper()]
    if not hits:
        data = await search([{"terms": {"type": ["0", "1", "2", "8"]}}], text=f'"{ident}"', size=5)
        hits = data.get("results", [])
    if not hits:
        return {"identifier": ident, "found": False, **meta()}
    r = sorted(hits, key=lambda x: len(first(x["metadata"], "descriptionByte") or first(x["metadata"], "description") or ""),
               reverse=True)[0]
    m = r["metadata"]
    names = await _names()
    dl, future = next_deadline(as_list(m, "deadlineDate"))
    infos = jload(first(m, "latestInfos")) or []
    actions = jload(first(m, "actions")) or []
    links = jload(first(m, "links")) or []
    out = {
        "found": True,
        **_summary(r, names),
        "all_deadlines": [d[:16].replace("T", " ") for d in as_list(m, "deadlineDate")],
        "next_deadline_is_future": future,
        "description": html_to_text(first(m, "descriptionByte") or first(m, "description"), max_chars),
        "conditions": html_to_text(first(m, "topicConditions"), max_chars),
        "how_to_apply": html_to_text(first(m, "beneficiaryAdministration"), 2000),
        "budget": budget(m),
        "actions": [{"types": [t.get("typeOfAction") for t in a.get("types", [])], "status": a.get("status", {}).get("abbreviation")
                     if isinstance(a.get("status"), dict) else a.get("status"),
                     "deadlines": a.get("deadlineDates"), "opening": a.get("plannedOpeningDate")} for a in actions][:10] or None,
        "latest_updates": [{"date": (i.get("lastChangeDate") or "")[:10], "text": html_to_text(i.get("content"), 600)}
                           for i in infos][:5] or None,
        "support": html_to_text(first(m, "supportInfo"), 1500),
        "submission_links": [{"action": lk.get("criterionDescription"), "url": lk.get("url")} for lk in links][:10] or None,
        "partner_search_enabled": (first(m, "allowPartnerSearch") == "true") or None,
        "keywords": as_list(m, "keywords")[:15] or None,
        **meta(),
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


@mcp.tool
async def upcoming_deadlines(days: int = 30, programme: str = "", query: str = "", limit: int = 30) -> dict:
    """Open calls whose deadline falls within the next N days, soonest first."""
    today = date.today()
    res = await search_funding(query=query, programme=programme, status="open",
                               deadline_from=today.isoformat(), deadline_to=(today + timedelta(days=days)).isoformat(),
                               limit=limit)
    return {"window": f"{today.isoformat()} → {(today + timedelta(days=days)).isoformat()}", **res}


@mcp.tool
async def call_topics(call_identifier: str, limit: int = 100) -> dict:
    """All topics belonging to one call (e.g. "HORIZON-CL4-2027-01"), with deadlines and budgets."""
    data, names = await asyncio.gather(
        search([{"terms": {"callIdentifier": [call_identifier.strip()]}}], size=limit,
               sort={"field": "deadlineDate", "order": "ASC"}), _names())
    seen, rows = set(), []
    for r in data.get("results", []):
        s = _summary(r, names)
        if s.get("identifier") in seen:
            continue
        seen.add(s.get("identifier"))
        rows.append(s)
    total_budget = sum(x.get("budget_eur") or 0 for x in rows) or None
    return {"call": call_identifier, "topics": len(rows), "total_budget_eur": total_budget, "results": rows, **meta()}


@mcp.tool
async def list_programmes(status: str = "open_or_forthcoming", include_breakdown: bool = False) -> dict:
    """EU funding programmes with the number of open/forthcoming opportunities, plus (optionally) a breakdown by
    Horizon Europe destination, mission and cross-cutting priority (e.g. AI, Digital Agenda)."""
    must = [{"terms": {"type": ["1", "2", "8"]}}, {"terms": {"status": _status_codes(status)}}]
    fac = await facets(must)
    out = {"status": status, "programmes": fac.get("frameworkProgramme", []),
           "by_kind": fac.get("type", []), **meta()}
    if include_breakdown:
        out.update({"destinations": fac.get("destination", [])[:40], "missions": fac.get("mission", []),
                    "cross_cutting_priorities": fac.get("crossCuttingPriorities", []),
                    "biggest_calls": fac.get("callIdentifier", [])[:30]})
    return out


@mcp.tool
async def search_tenders(query: str = "", status: str = "open", include_past_deadlines: bool = False,
                         limit: int = 20, page: int = 1) -> dict:
    """EU institutions' public procurement (calls for tenders) on the Funding & Tenders Portal.
    By default only tenders with a deadline today or later are returned."""
    must = [{"terms": {"type": [TYPES["tender"]]}}, {"terms": {"status": _status_codes(status)}}]
    if not include_past_deadlines and status.lower() != "closed":
        must.append({"range": {"deadlineDate": {"gte": iso(date.today().isoformat())}}})
    data = await search(must, text=query or "***", page=page, size=limit, sort={"field": "deadlineDate", "order": "ASC"})
    rows = []
    for r in data.get("results", []):
        m = r.get("metadata", {})
        dl, future = next_deadline(as_list(m, "deadlineDate"))
        rows.append({k: v for k, v in {
            "identifier": first(m, "callIdentifier") or first(m, "identifier"),
            "title": (first(m, "title") or "").strip()[:300],
            "contracting_authority": first(m, "caName"),
            "status": STATUS_NAMES.get(first(m, "status")),
            "deadline": dl, "deadline_passed": (dl is not None and not future) or None,
            "description": html_to_text(first(m, "description"), 500),
            "cpv": as_list(m, "mainCpv")[:5] or None,
            "url": first(m, "url") or r.get("url"),
        }.items() if v not in (None, "", [])})
    return {"total": data.get("totalResults", 0), "page": page, "results": rows, **meta()}


@mcp.tool
async def health() -> dict:
    """Check connectivity to the EU Funding & Tenders API."""
    try:
        data = await search([{"terms": {"type": ["1"]}}, {"terms": {"status": [STATUS["open"]]}}], size=1)
        return {"status": "ok", "open_grant_topics": data.get("totalResults"), **meta()}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}


@mcp.prompt
def funding_match(organisation_profile: str, country: str = "Israel") -> str:
    """Find and rank EU calls that fit an organisation, then explain eligibility and next steps."""
    return f"""Act as an EU funding consultant. My organisation: {organisation_profile}. Country: {country}.

1. Derive 3-5 search phrases from the profile and call `search_funding` for each (status open_or_forthcoming,
   programme HORIZON first, then DIGITAL, EIC-related topics and others that fit).
2. Shortlist the 5 best-fitting topics. For each, call `get_topic` and summarise: goal in one line, type of
   action (RIA/IA/CSA/EIC…), budget per project, next deadline, consortium requirements, TRL if stated.
3. Check eligibility for an entity from {country} (association status to Horizon Europe, single-applicant vs
   consortium, SME rules). Flag anything that needs confirmation on the official page.
4. Rank the 5 by fit and effort, and give concrete next steps (partner search, national contact point,
   proposal timeline back-planned from the deadline).
Cite the official topic URL for every recommendation."""


def main() -> None:
    if os.environ.get("MCP_TRANSPORT", "stdio") == "stdio":
        mcp.run()
    else:
        mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
