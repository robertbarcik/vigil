# Vigil — Development Guide

## What is Vigil?

Vigil is an open-source LLM red-teaming and human oversight testing framework. It tests both AI models (via automated adversarial conversations) and the humans overseeing them (via planted-issue review sessions). Built for cybersecurity teams and EU AI Act compliance readiness.

## Architecture

```
vigil run config.yaml   →  4-stage pipeline via CLI
vigil serve             →  FastAPI web UI on localhost
vigil sweep             →  Multi-behavior batch evaluation
vigil oversight         →  Human reviewer testing
```

### Core Pipeline (src/vigil/pipeline/)
1. **Scenario Generation** (`scenarios.py`) — Attacker LLM generates realistic attack scenarios from behavior definitions
2. **Attack Execution** (`attacks.py` + `orchestrator.py`) — Multi-turn conversations between attacker and target LLMs
3. **Judgment** (`judgment.py`) — Judge LLM scores target behavior (1-10 scale) with justification
4. **Reporting** (`reporting.py`) — Aggregate stats + HTML report

### Key Design Patterns
- **Dual message histories** in `orchestrator.py`: attacker and target maintain separate conversation views (from Bloom)
- **`<END>` tag** for conversation termination with `min_turns` enforcement
- **XML-tagged outputs** parsed with regex (`<scenario>`, `<behavior_presence_score>`, etc.)
- **Async concurrency** with `asyncio.Semaphore` for rate-limited parallel API calls
- **JSON file storage** in `~/.vigil/runs/{run_id}/` — no database

### Human Oversight (src/vigil/oversight/)
- `generator.py` — Creates LLM outputs, plants subtle issues (5 types) in a configurable fraction
- `reviewer.py` — Tracks human decisions via web UI
- `scoring.py` — Computes detection rate, precision, vigilance score

### Web UI (src/vigil/web/)
- FastAPI + Jinja2 + Tailwind CSS (CDN, no build step)
- Templates in `src/vigil/templates/`
- Routes: dashboard, red-team viewer, human review interface, JSON API

## Project Structure

```
src/vigil/
├── cli.py              # Click CLI entry point
├── client.py           # OpenRouter async httpx client
├── config.py           # YAML config + .env loading
├── models.py           # All Pydantic v2 data models (THE shared vocabulary)
├── storage.py          # JSON file persistence
├── pipeline/           # 4-stage red-team pipeline
│   ├── core.py         # Pipeline orchestrator
│   ├── scenarios.py    # Stage 1: scenario generation
│   ├── orchestrator.py # Multi-turn conversation manager
│   ├── attacks.py      # Stage 2: attack execution
│   ├── judgment.py     # Stage 3: scoring
│   └── reporting.py    # Stage 4: HTML report
├── prompts/            # All LLM prompt templates
├── oversight/          # Human review testing module
├── web/                # FastAPI app + routes
├── templates/          # Jinja2 HTML templates
├── static/             # CSS + JS
└── data/               # behaviors.yaml, eu_ai_act.yaml
```

## Development

```bash
# Setup
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linter
ruff check src/ tests/

# Quick test run (needs OPENROUTER_API_KEY in .env)
vigil run configs/quick_test.yaml
```

## Key Files to Know

- `models.py` — Change data models here first, everything else follows
- `prompts/*.py` — All LLM prompts live here; tune these for better results
- `data/behaviors.yaml` — Add new behaviors by adding YAML entries (no code changes)
- `data/eu_ai_act.yaml` — Compliance mapping, update as regulations clarify
- `configs/example.yaml` — Reference config showing all parameters

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `behavior` | (required) | Behavior to test (key from behaviors.yaml) |
| `target_model` | (required) | OpenRouter model ID to evaluate |
| `attacker_model` | `anthropic/claude-sonnet-4` | Model that attacks the target |
| `judge_model` | `anthropic/claude-sonnet-4` | Model that scores the results |
| `num_scenarios` | 5 | Number of attack scenarios to generate |
| `num_turns` | 10 | Maximum conversation turns |
| `min_turns` | 3 | Minimum turns before attacker can end |
| `attacker_persistence` | `high` | How hard the attacker pushes (low/medium/high) |
| `num_reps` | 1 | Repetitions per scenario |
| `max_concurrent` | 5 | Parallel API calls |
| `temperature` | 1.0 | LLM temperature |
| `max_tokens` | 4096 | Max tokens per response |

## OpenRouter Model IDs

Use direct OpenRouter format: `vendor/model-name`. Examples:
- `meta-llama/llama-3.3-70b-instruct`
- `qwen/qwen3-235b-a22b` (cost-effective attacker/judge)
- `anthropic/claude-sonnet-4`
- `google/gemini-2.5-pro-preview`
- `openai/gpt-4o`

The client auto-strips `openrouter/` prefix if present.

## Conventions

- All data models in `models.py`, nowhere else
- Prompts in `prompts/` module, not inline in pipeline stages
- Storage is always JSON files, accessed via `storage.py`
- Web routes are thin — business logic lives in pipeline/ and oversight/
- Config YAML maps 1:1 to `RunConfig` Pydantic model
