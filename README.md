# mcp-eu-funding

<!-- mcp-name: io.github.olegsher-ds-2025/mcp-eu-funding -->

EU funding opportunities for AI assistants: **Horizon Europe, EIC, Digital Europe, LIFE, Erasmus+, EDF, Creative
Europe, Single Market, EU4Health** and more, straight from the official **EU Funding & Tenders Portal**.

Free, open source, no API key. Search open and forthcoming calls, read full topic conditions and budgets, track
deadlines, and browse EU tenders, all inside Claude or any MCP client.

## Tools

| Tool | What it does |
|---|---|
| `search_funding` | Grant topics, cascade/FSTP calls and EuropeAid calls by keyword, programme, status, deadline window, cross-cutting priority (e.g. AI) |
| `get_topic` | Full topic: expected outcome & scope, eligibility/admissibility conditions, budget per action, all deadlines, updates, support contacts, submission links |
| `upcoming_deadlines` | Open calls closing in the next N days |
| `call_topics` | Every topic in a call (e.g. `HORIZON-CL4-2027-01`) |
| `list_programmes` | Programmes with open/forthcoming counts; destinations, missions, priorities |
| `search_tenders` | EU institutions' calls for tenders |
| `health` | Connectivity check |

**Prompt:** `funding_match(organisation_profile, country)` turns the assistant into an EU funding consultant. It finds, shortlists and ranks calls for an organisation, checks eligibility and plans next steps.

## Try asking

- "Which Horizon Europe calls on AI in healthcare are open right now?"
- "What closes in the next 3 weeks under Digital Europe?"
- "Explain the conditions and budget of HORIZON-CL4-2027-01-MAT-PROD-22."
- "We're an Israeli SME doing computer vision for agriculture — find EU calls that fit."

## Install

```bash
uvx mcp-eu-funding
```

Claude Desktop / Claude Code (`.mcp.json`):

```json
{ "mcpServers": { "eu-funding": { "command": "uvx", "args": ["mcp-eu-funding"] } } }
```

HTTP mode: `MCP_TRANSPORT=http PORT=8000 mcp-eu-funding` → `http://localhost:8000/mcp`.
Docker: `docker build -t mcp-eu-funding . && docker run -p 8000:8000 mcp-eu-funding`.

## Notes

- Data: the portal's public search API (`api.tech.ec.europa.eu/search-api`). It occasionally drops connections, so requests are retried automatically.
- The portal keeps some calls marked "open" after their final deadline; searches return only future deadlines unless `include_past_deadlines=true`.
- Israel is associated to Horizon Europe; always confirm eligibility in the topic's conditions.

## Verify the package

Releases are built by GitHub Actions with PyPI Trusted Publishing and carry PyPI (PEP 740) and GitHub build-provenance attestations:

```bash
pip download mcp-eu-funding --no-deps -d dl && gh attestation verify dl/*.whl -R olegsher-ds-2025/mcp-eu-funding
```

## Development

```bash
pip install -e ".[dev]" && pytest   # offline
pytest -m live                      # hits the EU API
```

## Related

Part of a family of public-data MCP servers by [Oleg Sher](https://linkedin.com/in/sheroleg):
mcp-eu-funding · mcp-il-innovation · mcp-il-companies · mcp-il-vehicles · mcp-il-health · mcp-il-professionals.

© European Union for the data. Independent project, not affiliated with the European Commission. MIT licence.
