import asyncio

import pytest
from fastmcp import Client

from mcp_eu_funding import server
from mcp_eu_funding.sedia import html_to_text, next_deadline

FAKE_RESULT = {"totalResults": 1, "results": [{"url": "https://example.eu/t", "metadata": {
    "identifier": ["HORIZON-TEST-01"], "title": ["Test topic"], "type": ["1"], "status": ["31094502"],
    "frameworkProgramme": ["43108390"], "deadlineDate": ["2099-01-01T17:00:00.000+0000"], "callIdentifier": ["HORIZON-TEST"],
    "budgetOverview": ['{"budgetTopicActionMap":{"1":[{"action":"HORIZON-TEST-01 - RIA","budgetYearMap":{"2027":3000000},"expectedGrants":2}]}}'],
    "descriptionByte": ["<p>Expected Outcome:</p><ul><li>Better things</li></ul>"], "topicConditions": ["<h4>Conditions</h4><p>Eligible countries</p>"]}}]}
FAKE_FACETS = {"frameworkProgramme": [{"code": "43108390", "name": "Horizon Europe (HORIZON)", "count": 800}], "type": []}


@pytest.fixture
def offline(monkeypatch):
    calls = []

    async def fake_search(must, **kw):
        calls.append((must, kw))
        return FAKE_RESULT

    async def fake_facets(must, ttl=0):
        return FAKE_FACETS

    monkeypatch.setattr(server, "search", fake_search)
    monkeypatch.setattr(server, "facets", fake_facets)
    return calls


def _call(tool, args):
    async def run():
        async with Client(server.mcp) as c:
            r = await c.call_tool(tool, args)
            return r.data if hasattr(r, "data") else r
    return asyncio.run(run())


def test_tools_registered():
    async def run():
        async with Client(server.mcp) as c:
            return {t.name for t in await c.list_tools()}, {p.name for p in await c.list_prompts()}
    tools, prompts = asyncio.run(run())
    assert {"search_funding", "get_topic", "upcoming_deadlines", "call_topics", "list_programmes", "search_tenders", "health"} <= tools
    assert "funding_match" in prompts


def test_search_resolves_programme_and_defaults_to_future(offline):
    data = _call("search_funding", {"query": "ai", "programme": "HORIZON"})
    must = offline[0][0]
    assert {"terms": {"frameworkProgramme": ["43108390"]}} in must
    assert any("range" in c for c in must)
    assert data["results"][0]["programme"] == "Horizon Europe (HORIZON)" and data["results"][0]["budget_eur"] == 3000000
    assert "source" in data


def test_get_topic_parses_text(offline):
    data = _call("get_topic", {"identifier": "HORIZON-TEST-01"})
    assert data["found"] and "Better things" in data["description"] and "Eligible countries" in data["conditions"]


def test_helpers():
    assert html_to_text("<p>A&amp;B</p><ul><li>x</li></ul>") == "A&B\n\n- x"
    d, future = next_deadline(["2000-01-01T00:00:00.000+0000", "2099-05-01T17:00:00.000+0000"])
    assert future and d.startswith("2099-05-01")


@pytest.mark.live
def test_live_health():
    assert _call("health", {})["status"] == "ok"
