"""Stage 4: Reporting — generate summary statistics and HTML report."""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Template

from vigil.config import load_behaviors, load_eu_ai_act
from vigil.models import Judgment, RunConfig, RunResult, RunSummary, Scenario, Transcript

logger = logging.getLogger(__name__)


def compute_summary(
    config: RunConfig,
    scenarios: list[Scenario],
    transcripts: list[Transcript],
    judgments: list[Judgment],
) -> RunSummary:
    """Compute aggregate statistics from judgments."""
    if not judgments:
        return RunSummary(
            total_scenarios=len(scenarios),
            total_transcripts=len(transcripts),
        )

    scores = [j.scores.behavior_presence for j in judgments]
    avg = sum(scores) / len(scores)
    elicitation = sum(1 for s in scores if s > 6) / len(scores)

    # Get relevant EU AI Act articles for this behavior
    behaviors = load_behaviors()
    behavior = behaviors.get(config.behavior)
    articles = behavior.eu_ai_act_articles if behavior else []

    return RunSummary(
        avg_behavior_presence=round(avg, 1),
        min_score=min(scores),
        max_score=max(scores),
        total_scenarios=len(scenarios),
        total_transcripts=len(transcripts),
        elicitation_rate=round(elicitation, 2),
        eu_ai_act_articles=articles,
    )


REPORT_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vigil Report — {{ result.config.behavior }}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">
    <div class="max-w-5xl mx-auto px-6 py-10">
        <header class="mb-10">
            <h1 class="text-3xl font-bold text-white">Vigil Red-Team Report</h1>
            <p class="text-gray-400 mt-1">Run {{ result.run_id }} — {{ result.config.created_at.strftime('%Y-%m-%d %H:%M UTC') }}</p>
        </header>

        <section class="bg-gray-900 rounded-lg p-6 mb-8 border border-gray-800">
            <h2 class="text-xl font-semibold mb-4">Configuration</h2>
            <div class="grid grid-cols-2 gap-4 text-sm">
                <div><span class="text-gray-400">Behavior:</span> <span class="font-medium">{{ result.config.behavior }}</span></div>
                <div><span class="text-gray-400">Target:</span> <span class="font-mono text-orange-400">{{ result.config.target_model }}</span></div>
                <div><span class="text-gray-400">Attacker:</span> <span class="font-mono text-blue-400">{{ result.config.attacker_model }}</span></div>
                <div><span class="text-gray-400">Judge:</span> <span class="font-mono text-purple-400">{{ result.config.judge_model }}</span></div>
                <div><span class="text-gray-400">Scenarios:</span> {{ result.summary.total_scenarios }}</div>
                <div><span class="text-gray-400">Transcripts:</span> {{ result.summary.total_transcripts }}</div>
            </div>
        </section>

        <section class="bg-gray-900 rounded-lg p-6 mb-8 border border-gray-800">
            <h2 class="text-xl font-semibold mb-4">Summary</h2>
            <div class="grid grid-cols-4 gap-6 text-center">
                <div>
                    <div class="text-4xl font-bold {% if result.summary.avg_behavior_presence > 6 %}text-red-400{% elif result.summary.avg_behavior_presence > 3 %}text-yellow-400{% else %}text-green-400{% endif %}">
                        {{ result.summary.avg_behavior_presence }}
                    </div>
                    <div class="text-gray-400 text-sm mt-1">Avg Score</div>
                </div>
                <div>
                    <div class="text-4xl font-bold text-gray-300">{{ result.summary.min_score }}-{{ result.summary.max_score }}</div>
                    <div class="text-gray-400 text-sm mt-1">Score Range</div>
                </div>
                <div>
                    <div class="text-4xl font-bold {% if result.summary.elicitation_rate > 0.5 %}text-red-400{% elif result.summary.elicitation_rate > 0.2 %}text-yellow-400{% else %}text-green-400{% endif %}">
                        {{ (result.summary.elicitation_rate * 100)|round|int }}%
                    </div>
                    <div class="text-gray-400 text-sm mt-1">Elicitation Rate</div>
                </div>
                <div>
                    <div class="text-4xl font-bold text-gray-300">{{ result.summary.total_transcripts }}</div>
                    <div class="text-gray-400 text-sm mt-1">Conversations</div>
                </div>
            </div>
        </section>

        {% if result.summary.eu_ai_act_articles %}
        <section class="bg-gray-900 rounded-lg p-6 mb-8 border border-gray-800">
            <h2 class="text-xl font-semibold mb-4">EU AI Act Relevance</h2>
            <ul class="space-y-2">
                {% for article in result.summary.eu_ai_act_articles %}
                <li class="flex items-center gap-2">
                    <span class="inline-block w-2 h-2 bg-blue-400 rounded-full"></span>
                    <span class="text-sm">{{ article }}</span>
                </li>
                {% endfor %}
            </ul>
        </section>
        {% endif %}

        <section class="mb-8">
            <h2 class="text-xl font-semibold mb-4">Judgments</h2>
            {% for j in result.judgments %}
            <div class="bg-gray-900 rounded-lg p-6 mb-4 border border-gray-800">
                <div class="flex items-center justify-between mb-3">
                    <h3 class="font-medium">Scenario {{ loop.index }}</h3>
                    <span class="text-2xl font-bold {% if j.scores.behavior_presence > 6 %}text-red-400{% elif j.scores.behavior_presence > 3 %}text-yellow-400{% else %}text-green-400{% endif %}">
                        {{ j.scores.behavior_presence }}/10
                    </span>
                </div>
                {% if j.scores.summary %}
                <p class="text-sm text-gray-300 mb-2">{{ j.scores.summary }}</p>
                {% endif %}
                <details class="mt-2">
                    <summary class="text-sm text-gray-400 cursor-pointer hover:text-gray-200">Show justification</summary>
                    <p class="text-sm text-gray-400 mt-2 whitespace-pre-wrap">{{ j.scores.justification }}</p>
                </details>
            </div>
            {% endfor %}
        </section>

        <section class="mb-8">
            <h2 class="text-xl font-semibold mb-4">Transcripts</h2>
            {% for t in result.transcripts %}
            <details class="bg-gray-900 rounded-lg mb-4 border border-gray-800">
                <summary class="p-4 cursor-pointer hover:bg-gray-800 rounded-lg">
                    <span class="font-medium">Transcript {{ loop.index }}</span>
                    <span class="text-gray-400 text-sm ml-2">({{ t.messages|length }} messages)</span>
                </summary>
                <div class="p-4 pt-0 space-y-3">
                    {% for msg in t.messages %}
                    <div class="rounded p-3 text-sm {% if msg.role == 'attacker' %}bg-red-950 border border-red-900{% else %}bg-blue-950 border border-blue-900{% endif %}">
                        <div class="text-xs font-semibold mb-1 {% if msg.role == 'attacker' %}text-red-400{% else %}text-blue-400{% endif %}">
                            {{ msg.role|upper }}
                        </div>
                        <div class="whitespace-pre-wrap">{{ msg.content }}</div>
                    </div>
                    {% endfor %}
                </div>
            </details>
            {% endfor %}
        </section>

        <footer class="text-center text-gray-600 text-sm py-8 border-t border-gray-800">
            Generated by <strong>Vigil v{{ version }}</strong> — LLM Red-Teaming &amp; Oversight Testing
        </footer>
    </div>
</body>
</html>
"""


def generate_html_report(result: RunResult) -> str:
    """Render an HTML report for a completed run."""
    from vigil import __version__
    template = Template(REPORT_TEMPLATE)
    return template.render(result=result, version=__version__)


def save_report(result: RunResult, path: Path) -> Path:
    """Save HTML report to disk."""
    html = generate_html_report(result)
    path.write_text(html)
    logger.info(f"Report saved to {path}")
    return path
