# Skill Scout (Codex + MCP Discovery Agent)

Local agent + web UI that discovers, ranks, and searches:

- Codex/Agent `SKILL.md` skills (e.g., `openai/skills`, GitHub repos)
- MCP servers (official MCP Registry)
- Related “connectors / plugins / hooks / APIs” (GitHub + package registries via collectors)

## What it does

- **Refresh**: pulls items from multiple sources, deduplicates, and computes a “trending” score
- **Index**: stores everything locally in SQLite (`skill_scout.db`)
- **UI**: search + filters + install hints
- **Ask**: optional model-based rerank (supports OpenAI-compatible gateways like NVIDIA, OpenAI, or local Ollama)

## Quick start (Windows PowerShell)

1) Create a venv and install deps:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) Fetch the latest index:

```powershell
python -m skill_scout.cli refresh
```

3) Start the web UI:

```powershell
python -m skill_scout.cli serve
```

Then open: http://127.0.0.1:8787

## Config

Copy `.env.example` to `.env` and fill what you want:

- `GITHUB_TOKEN` (optional but recommended)
- `OPENAI_API_KEY` (optional, for agent “ask” features)
- `ANTHROPIC_API_KEY` / `OLLAMA_HOST` (optional)

### NVIDIA (OpenAI-compatible) example

Set:

- `OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1`
- `OPENAI_MODEL=minimaxai/minimax-m2.7`
- `OPENAI_API_KEY=...` (keep this only in `.env`)

## Commands

- `python -m skill_scout.cli refresh`
- `python -m skill_scout.cli serve`
- `python -m skill_scout.cli export --out skill_scout_export.json`

