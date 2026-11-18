# mcp-eu-funding — CLAUDE.md

EU Funding & Tenders Portal MCP server (Horizon Europe etc.), live from the SEDIA search API.

## Stack
Python 3.11 · FastMCP · httpx · pytest. No database.

## Layout
- server.py — hosted entrypoint (`server.py:mcp`)
- src/mcp_eu_funding/sedia.py — API client: `search(must, text, page, size, sort)`, `facets(must)` (cached 6h), HTML→text, budget & deadline parsing
- src/mcp_eu_funding/server.py — tools + `funding_match` prompt
- tests/ — offline (monkeypatched search/facets); `pytest -m live` for real calls

## SEDIA API facts (verified 2026-11-18)
- POST https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=…&pageSize=…&pageNumber=… with multipart fields `query`, `languages`, `sort` (JSON). Facets: same body to /rest/facet.
- Match-all text is `***`; `query.bool.must` needs ≥1 clause.
- type: 0 tender · 1 grant topic · 2 EuropeAid call · 8 cascade funding. status: 31094501 forthcoming · 31094502 open · 31094503 closed.
- frameworkProgramme codes → names come from the facet endpoint (e.g. 43108390 Horizon Europe, 43152860 Digital Europe).
- Range filters need full ISO: `2026-11-18T00:00:00.000+0000`. Sort: `{"field":"deadlineDate","order":"ASC"}`.
- Metadata values are lists; budgetOverview/actions/latestInfos/links are JSON strings; descriptionByte/topicConditions are HTML.
- Some topics stay status=open after their last deadline → default filter deadline ≥ today.
- API intermittently drops connections → retries with backoff.

## Rules
- Every response includes `source`, `retrieved_at`, `attribution` via `meta()`.
- Bump version in pyproject.toml, __init__.py and server.json together BEFORE tagging a release.
- Update MEMORY.md at the end of every session.

## Model routing
Architect/Advisor: Fable (else Opus) · Orchestrator: Opus · Executor: Sonnet · Explorer/tests: Haiku · tiny text jobs: Jetson llama.cpp · graphics: Gemini/ChatGPT.
