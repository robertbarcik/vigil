# Vigil

**LLM red-teaming and human oversight testing framework.**

*"Quis custodiet ipsos custodes?"* — Who watches the watchmen?

Vigil tests both your AI models and the humans overseeing them. It's an open-source framework for cybersecurity teams, AI safety researchers, and organizations preparing for EU AI Act compliance.

## Features

- **LLM-vs-LLM Red Teaming** — Automated multi-turn attack conversations that probe target models for dangerous behaviors
- **Human Oversight Testing** — Generate outputs with planted issues to measure whether human reviewers actually catch problems
- **EU AI Act Mapping** — Map test results to relevant EU AI Act articles for compliance readiness
- **Web Dashboard** — Browse results, review transcripts, and manage oversight sessions from your browser
- **12 Cybersec Behaviors** — Built-in catalog covering prompt injection, social engineering, data exfiltration, and more

## Quick Start

```bash
# Install
pip install -e .

# Set your OpenRouter API key
export OPENROUTER_API_KEY=sk-or-v1-...

# Run a red-team evaluation
vigil run configs/example.yaml

# Start the web UI
vigil serve
```

## Red-Team Pipeline

Vigil runs a 4-stage pipeline inspired by behavioral evaluation research:

1. **Scenario Generation** — An attacker LLM generates realistic attack scenarios for the target behavior
2. **Attack Execution** — Multi-turn conversations between attacker and target LLMs
3. **Judgment** — A judge LLM scores how strongly the target exhibited the problematic behavior (1-10)
4. **Reporting** — Aggregate statistics, HTML reports, and EU AI Act compliance mapping

### Configuration

```yaml
# vigil.yaml
behavior: prompt-injection
target_model: meta-llama/llama-3.3-70b-instruct
attacker_model: anthropic/claude-sonnet-4
judge_model: anthropic/claude-sonnet-4
num_scenarios: 5
num_turns: 10
```

## Human Oversight Testing

Test whether your human reviewers are actually catching AI-generated issues — or just rubber-stamping outputs.

```bash
# Generate a review session with planted issues
vigil oversight --topic "cybersecurity incident response" --items 20 --issue-ratio 0.3

# Open the web UI to start reviewing
vigil serve
```

The framework generates LLM outputs, plants subtle issues in a configurable fraction of them (factual errors, security risks, policy violations, bias, hallucinations), and tracks reviewer performance:

- **Detection rate** — Are they catching the planted issues?
- **Precision** — Are they raising false alarms?
- **Response time** — Are they spending enough time on each review?
- **Vigilance score** — Composite metric combining all factors

This directly supports **EU AI Act Article 14 (Human Oversight)** requirements.

## Built-in Behaviors

| Behavior | Category | Severity |
|----------|----------|----------|
| prompt-injection | security | critical |
| social-engineering-assistance | security | critical |
| information-leakage | security | critical |
| credential-extraction | security | critical |
| malware-assistance | security | critical |
| data-exfiltration | security | critical |
| phishing-generation | security | critical |
| safety-filter-bypass | safety | high |
| authority-compliance | security | high |
| privilege-escalation | security | high |
| deception-capability | safety | high |
| oversight-evasion | compliance | high |

## Web UI

```bash
vigil serve --port 8080
```

- **Dashboard** — Overview of all runs and oversight sessions
- **Red Team** — Browse scenarios, scores, and full conversation transcripts
- **Human Review** — Interactive review interface with timer and scoring

## CLI Commands

```
vigil run <config.yaml>     Run a red-team evaluation
vigil serve                 Start the web UI
vigil list                  List all runs
vigil oversight             Generate an oversight testing session
vigil init                  Initialize workspace with example config
```

## API

All data is also available via JSON API at `/api/`:

```
GET  /api/runs              List all runs
GET  /api/runs/{id}         Get run details
GET  /api/behaviors         List available behaviors
POST /api/runs/launch       Launch a new run
POST /api/oversight/launch  Create oversight session
```

## Requirements

- Python 3.11+
- OpenRouter API key (supports 200+ models)

## License

Apache 2.0
