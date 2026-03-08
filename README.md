# Vigil

**LLM red-teaming and human oversight testing framework.**

*"Quis custodiet ipsos custodes?"* — Who watches the watchmen?

Vigil tests both your AI models and the humans overseeing them. It's an open-source framework for cybersecurity teams, AI safety researchers, and organizations preparing for EU AI Act compliance.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Red-Team Pipeline](#red-team-pipeline)
- [Configuration Reference](#configuration-reference)
- [Sweep Mode](#sweep-mode)
- [Human Oversight Testing](#human-oversight-testing)
- [Web Dashboard](#web-dashboard)
- [Built-in Behaviors](#built-in-behaviors)
- [EU AI Act Mapping](#eu-ai-act-mapping)
- [API Reference](#api-reference)
- [Advanced Usage](#advanced-usage)
- [Requirements](#requirements)

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/robertbarcik/vigil.git
cd vigil
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Set your OpenRouter API key

```bash
# Option A: environment variable
export OPENROUTER_API_KEY=sk-or-v1-...

# Option B: .env file (recommended)
echo "OPENROUTER_API_KEY=sk-or-v1-..." > .env
```

Get a key at [openrouter.ai](https://openrouter.ai/keys). OpenRouter gives you access to 200+ models (Llama, Claude, GPT, Gemini, Qwen, etc.) through a single API.

### 3. Run your first evaluation

```bash
# Initialize workspace with example config
vigil init

# Edit vigil.yaml to choose your target model and behavior, then:
vigil run vigil.yaml
```

Or use the included example config directly:

```bash
vigil run configs/example.yaml
```

### 4. View results

```bash
# In terminal
vigil list

# In browser
vigil serve
# → open http://127.0.0.1:8080
```

---

## Red-Team Pipeline

Vigil runs a 4-stage automated pipeline that pits an attacker LLM against a target LLM:

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  1. Scenario      │    │  2. Attack        │    │  3. Judgment      │    │  4. Report        │
│  Generation       │ →  │  Execution        │ →  │                   │ →  │                   │
│                   │    │                   │    │                   │    │                   │
│  Attacker LLM     │    │  Multi-turn       │    │  Judge LLM scores │    │  HTML report +    │
│  generates attack │    │  conversation     │    │  target behavior  │    │  JSON artifacts   │
│  scenarios        │    │  attacker vs      │    │  (1-10 scale)     │    │  + EU AI Act map  │
│                   │    │  target           │    │                   │    │                   │
└──────────────────┘    └──────────────────┘    └──────────────────┘    └──────────────────┘
```

**Stage 1: Scenario Generation**
The attacker model receives a behavior definition (e.g., "prompt injection") and generates realistic attack scenarios — each with a different strategy, context, and system prompt for the target.

**Stage 2: Attack Execution**
For each scenario, the attacker and target LLMs have a multi-turn conversation. The attacker tries to elicit the problematic behavior; the target responds naturally based on its system prompt. The conversation continues until the attacker succeeds, gives up, or hits the turn limit.

**Stage 3: Judgment**
A judge model reads each conversation transcript and scores how strongly the target exhibited the problematic behavior (1-10), with a detailed justification.

**Stage 4: Reporting**
Aggregate statistics (avg score, elicitation rate, score range) are computed, mapped to relevant EU AI Act articles, and saved as JSON + HTML report.

---

## Configuration Reference

Create a YAML file with these parameters:

```yaml
# Required
behavior: prompt-injection          # Which behavior to test
target_model: meta-llama/llama-3.3-70b-instruct  # Model to evaluate

# Models (use cost-effective models for attacker/judge)
attacker_model: qwen/qwen3-235b-a22b   # Model that attacks the target
judge_model: qwen/qwen3-235b-a22b      # Model that scores results

# Evaluation parameters
num_scenarios: 5          # How many distinct attack scenarios to generate
num_turns: 10             # Maximum conversation turns per scenario
min_turns: 3              # Minimum turns before attacker can end

# Attacker tuning
attacker_persistence: high  # How hard the attacker pushes
# - low:    tries 1-2 approaches, gives up after clear refusal
# - medium: tries 2-3 approaches, uses reframing
# - high:   relentless, 3-4+ approaches, escalating tactics
#           (casual → reframing → pressure → encoding → combined)

# Advanced
num_reps: 1               # Repeat each scenario N times for robustness
max_concurrent: 5          # Parallel API calls
temperature: 1.0           # LLM temperature
max_tokens: 4096           # Max tokens per response
```

### Model IDs

Use OpenRouter model IDs directly:

| Model | ID | Good for |
|-------|----|----------|
| Llama 3.3 70B | `meta-llama/llama-3.3-70b-instruct` | Target (popular open model) |
| Qwen 3 235B | `qwen/qwen3-235b-a22b` | Attacker/Judge (capable & cheap) |
| Claude Sonnet | `anthropic/claude-sonnet-4` | Attacker/Judge (high quality) |
| GPT-4o | `openai/gpt-4o` | Target or Judge |
| Gemini 2.5 Pro | `google/gemini-2.5-pro-preview` | Target or Judge |

Browse all models at [openrouter.ai/models](https://openrouter.ai/models).

---

## Sweep Mode

Test a model against multiple behaviors in one command:

```bash
# Test specific behaviors
vigil sweep prompt-injection information-leakage social-engineering-assistance \
  --target meta-llama/llama-3.3-70b-instruct

# Test ALL 12 behaviors
vigil sweep all --target meta-llama/llama-3.3-70b-instruct

# With custom parameters
vigil sweep prompt-injection malware-assistance phishing-generation \
  --target openai/gpt-4o \
  --attacker qwen/qwen3-235b-a22b \
  --scenarios 5 \
  --turns 10 \
  --min-turns 4 \
  --persistence high
```

Sweep produces a summary table at the end:

```
======================================================================
SWEEP SUMMARY
======================================================================
Behavior                            Score    Elicitation
----------------------------------------------------------------------
prompt-injection                      7.3         67%
information-leakage                   3.2         20%
social-engineering-assistance         6.1         60%
----------------------------------------------------------------------
OVERALL                               5.5
```

---

## Human Oversight Testing

Test whether your human reviewers actually catch AI-generated issues — or just rubber-stamp outputs.

### How it works

1. Vigil generates realistic LLM outputs on a given topic
2. It plants subtle issues in a configurable fraction of them (factual errors, security risks, policy violations, bias, hallucinations)
3. Human reviewers see the outputs in a web interface and decide: "Looks Good" or "Flag Issue"
4. Vigil scores reviewer performance: detection rate, precision, response time, vigilance score

### Usage

```bash
# Generate a review session
vigil oversight \
  --topic "cybersecurity incident response" \
  --items 20 \
  --issue-ratio 0.3 \
  --model qwen/qwen3-235b-a22b

# Start web UI for reviewing
vigil serve

# → Navigate to "Human Review" in sidebar
# → Select session → Start reviewing
```

### Issue Types

| Type | Description |
|------|-------------|
| `factual_error` | Wrong numbers, incorrect attributions, false technical claims |
| `policy_violation` | Sharing internal details, unauthorized commitments, scope violations |
| `security_risk` | Insecure practices, dangerous configs, deprecated protocols |
| `bias` | Demographic favoritism, stereotyping, exclusionary language |
| `hallucination` | Fabricated sources, fake studies, invented statistics |

### Scoring

| Metric | Description |
|--------|-------------|
| **Detection Rate** | % of planted issues the reviewer caught (TP / (TP + FN)) |
| **Precision** | % of flags that were correct (TP / (TP + FP)) |
| **Avg Response Time** | Average seconds spent per item |
| **Vigilance Score** | Composite: 50% detection + 30% precision + 20% speed |

This directly supports **EU AI Act Article 14 (Human Oversight)**: demonstrate that human reviewers effectively monitor AI outputs.

---

## Web Dashboard

```bash
vigil serve
# or: vigil serve --host 0.0.0.0 --port 8080
```

### Pages

- **Dashboard** (`/`) — Overview of all runs and oversight sessions with quick stats
- **Red Team → Runs** (`/redteam/runs`) — List of all red-team evaluations
- **Red Team → Run Detail** (`/redteam/runs/{id}`) — Scenarios, scores, and transcript links
- **Red Team → Transcript** (`/redteam/runs/{id}/transcript/{id}`) — Full conversation viewer with color-coded roles
- **Human Review → Sessions** (`/oversight/sessions`) — List of oversight sessions
- **Human Review → Review** (`/oversight/review/{id}`) — Interactive review interface with timer
- **Human Review → Results** (`/oversight/results/{id}`) — Reviewer performance dashboard with confusion matrix

---

## Built-in Behaviors

```bash
vigil behaviors  # list all
```

| Behavior | Category | Severity | Description |
|----------|----------|----------|-------------|
| `prompt-injection` | security | critical | Resistance to prompt override attacks |
| `social-engineering-assistance` | security | critical | Willingness to help craft social engineering attacks |
| `information-leakage` | security | critical | Leaking sensitive info under pressure |
| `credential-extraction` | security | critical | Helping extract/guess credentials |
| `malware-assistance` | security | critical | Helping write malicious code |
| `data-exfiltration` | security | critical | Helping exfiltrate data from systems |
| `phishing-generation` | security | critical | Creating convincing phishing content |
| `safety-filter-bypass` | safety | high | Susceptibility to jailbreak techniques |
| `authority-compliance` | security | high | Complying with false authority claims |
| `privilege-escalation` | security | high | Assisting with unauthorized access elevation |
| `deception-capability` | safety | high | Ability to convincingly deceive users |
| `oversight-evasion` | compliance | high | Attempting to evade monitoring/logging |

### Adding Custom Behaviors

Edit `src/vigil/data/behaviors.yaml`:

```yaml
my-custom-behavior:
  name: My Custom Behavior
  description: >
    Detailed description of what this behavior tests...
  category: security
  severity: high
  attack_strategies:
    - Strategy one
    - Strategy two
  eu_ai_act_articles:
    - "Article 15 - Accuracy, robustness and cybersecurity"
```

No code changes needed — just add the YAML entry and use it: `vigil run --behavior my-custom-behavior`.

---

## EU AI Act Mapping

Each behavior maps to relevant EU AI Act articles. The mapping is in `src/vigil/data/eu_ai_act.yaml` and appears in:
- HTML reports (per-run)
- Web dashboard (run detail page)
- Sweep summary

This is a **compliance readiness** tool — it helps demonstrate testing coverage against specific regulatory requirements. As the AI Act's implementing measures evolve, update the YAML mapping accordingly.

---

## API Reference

All data is available via JSON API when the web server is running:

```bash
# Red-team runs
GET  /api/runs                    # List all runs
GET  /api/runs/{run_id}           # Full run detail (config, scenarios, transcripts, judgments)
POST /api/runs/launch             # Launch a new run (async, returns run_id)

# Behaviors
GET  /api/behaviors               # List all available behaviors

# Oversight
GET  /api/oversight/sessions      # List oversight sessions
POST /api/oversight/launch        # Create new oversight session
```

### Launch a run via API

```bash
curl -X POST http://localhost:8080/api/runs/launch \
  -H "Content-Type: application/json" \
  -d '{
    "behavior": "prompt-injection",
    "target_model": "meta-llama/llama-3.3-70b-instruct",
    "attacker_model": "qwen/qwen3-235b-a22b",
    "judge_model": "qwen/qwen3-235b-a22b",
    "num_scenarios": 3,
    "num_turns": 8
  }'
```

---

## Advanced Usage

### Cost Optimization

Use cost-effective models for attacker and judge roles — they don't need to be the most capable, just good enough to generate scenarios and score:

```yaml
# Cost-effective setup
attacker_model: qwen/qwen3-235b-a22b    # ~$0.12/M tokens
judge_model: qwen/qwen3-235b-a22b
target_model: meta-llama/llama-3.3-70b-instruct  # the model you're actually testing
```

### Tuning Attacker Persistence

The `attacker_persistence` and `min_turns` parameters control how thoroughly the target is tested:

```yaml
# Quick surface-level test
num_turns: 6
min_turns: 2
attacker_persistence: low

# Standard evaluation
num_turns: 10
min_turns: 3
attacker_persistence: medium

# Thorough stress test (recommended for security audits)
num_turns: 12
min_turns: 4
attacker_persistence: high
num_reps: 2  # run each scenario twice for robustness
```

### Running on a Remote Server

```bash
# Allow external connections
vigil serve --host 0.0.0.0 --port 8080

# Or behind a reverse proxy (nginx, caddy)
vigil serve --host 127.0.0.1 --port 8080
```

### Data Location

All results are stored in `~/.vigil/`:
```
~/.vigil/
├── runs/
│   └── {run_id}/
│       ├── config.json
│       ├── scenarios.json
│       ├── transcripts.json
│       ├── judgments.json
│       ├── result.json
│       └── report.html
└── oversight/
    └── {session_id}/
        └── session.json
```

Override with: `export VIGIL_DATA_DIR=/path/to/data`

---

## CLI Reference

```
vigil run <config.yaml>              Run a red-team evaluation pipeline
vigil sweep <behaviors...>           Run evaluations across multiple behaviors
  --target MODEL                     Target model (required)
  --attacker MODEL                   Attacker model
  --judge MODEL                      Judge model
  --scenarios N                      Scenarios per behavior
  --turns N                          Max turns
  --min-turns N                      Min turns before attacker can end
  --persistence low|medium|high      Attacker persistence level
vigil serve                          Start the web UI
  --host HOST                        Bind address (default: 127.0.0.1)
  --port PORT                        Bind port (default: 8080)
vigil list                           List all completed runs
vigil behaviors                      List available behaviors
vigil oversight                      Generate an oversight testing session
  --topic TOPIC                      Topic for generated outputs
  --items N                          Number of review items
  --issue-ratio FLOAT                Fraction with planted issues (0.0-1.0)
  --model MODEL                      Model for generation
vigil init                           Create vigil.yaml and .env templates
```

All commands support `-v` / `--verbose` for debug logging.

---

## Requirements

- Python 3.11+
- OpenRouter API key

## License

Apache 2.0
