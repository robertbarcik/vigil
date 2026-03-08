"""Vigil CLI — command-line interface."""

from __future__ import annotations

import asyncio
import logging

import click


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet down noisy loggers unless debug
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


@click.group()
@click.version_option(package_name="vigil")
def main():
    """Vigil — LLM red-teaming and human oversight testing."""
    pass


@main.command()
@click.argument("config_path", type=click.Path(exists=True))
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def run(config_path: str, verbose: bool):
    """Run a red-team evaluation pipeline."""
    _setup_logging(verbose)

    from vigil.config import load_config
    from vigil.pipeline.core import run_pipeline

    config = load_config(config_path)
    click.echo(f"Starting Vigil run {config.run_id}")
    click.echo(f"  Behavior:    {config.behavior}")
    click.echo(f"  Target:      {config.target_model}")
    click.echo(f"  Attacker:    {config.attacker_model}")
    click.echo(f"  Judge:       {config.judge_model}")
    click.echo(f"  Scenarios:   {config.num_scenarios}")
    click.echo(f"  Turns:       {config.min_turns}-{config.num_turns}")
    click.echo(f"  Persistence: {config.attacker_persistence}")
    click.echo()

    result = asyncio.run(run_pipeline(config))

    click.echo()
    click.echo(f"Avg behavior presence: {result.summary.avg_behavior_presence}/10")
    click.echo(f"Elicitation rate: {result.summary.elicitation_rate:.0%}")
    click.echo(f"Results saved to: ~/.vigil/runs/{result.run_id}/")


@main.command()
@click.argument("behaviors", nargs=-1, required=True)
@click.option("--target", required=True, help="Target model ID")
@click.option("--attacker", default="qwen/qwen3-235b-a22b", help="Attacker model ID")
@click.option("--judge", default="qwen/qwen3-235b-a22b", help="Judge model ID")
@click.option("--scenarios", default=3, help="Scenarios per behavior")
@click.option("--turns", default=8, help="Max turns per conversation")
@click.option("--min-turns", default=3, help="Min turns before attacker can end")
@click.option("--persistence", default="high", type=click.Choice(["low", "medium", "high"]))
@click.option("-v", "--verbose", is_flag=True)
def sweep(behaviors: tuple[str], target: str, attacker: str, judge: str,
          scenarios: int, turns: int, min_turns: int, persistence: str, verbose: bool):
    """Run red-team evaluations across multiple behaviors.

    Example: vigil sweep prompt-injection information-leakage --target meta-llama/llama-3.3-70b-instruct
    """
    _setup_logging(verbose)

    from vigil.config import load_behaviors
    from vigil.models import RunConfig
    from vigil.pipeline.core import run_pipeline

    available = load_behaviors()

    # Support "all" keyword
    if behaviors == ("all",):
        behavior_list = list(available.keys())
    else:
        behavior_list = list(behaviors)
        for b in behavior_list:
            if b not in available:
                click.echo(f"Unknown behavior: {b}")
                click.echo(f"Available: {', '.join(sorted(available.keys()))}")
                raise SystemExit(1)

    click.echo(f"Vigil sweep: {len(behavior_list)} behaviors against {target}")
    click.echo(f"  Behaviors: {', '.join(behavior_list)}")
    click.echo()

    results = []
    for i, behavior in enumerate(behavior_list, 1):
        click.echo(f"[{i}/{len(behavior_list)}] Testing: {behavior}")
        config = RunConfig(
            behavior=behavior,
            target_model=target,
            attacker_model=attacker,
            judge_model=judge,
            num_scenarios=scenarios,
            num_turns=turns,
            min_turns=min_turns,
            attacker_persistence=persistence,
        )
        result = asyncio.run(run_pipeline(config))
        results.append((behavior, result))
        click.echo(
            f"  → Score: {result.summary.avg_behavior_presence}/10 "
            f"(elicitation: {result.summary.elicitation_rate:.0%})"
        )
        click.echo()

    # Summary table
    click.echo("=" * 70)
    click.echo("SWEEP SUMMARY")
    click.echo("=" * 70)
    click.echo(f"{'Behavior':<35} {'Score':>8} {'Elicitation':>12}")
    click.echo("-" * 70)
    for behavior, result in results:
        score = result.summary.avg_behavior_presence
        elic = result.summary.elicitation_rate
        click.echo(f"{behavior:<35} {score:>7.1f} {elic:>11.0%}")
    click.echo("-" * 70)
    avg_all = sum(r.summary.avg_behavior_presence for _, r in results) / len(results) if results else 0
    click.echo(f"{'OVERALL':.<35} {avg_all:>7.1f}")


@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8080, help="Port to bind to")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def serve(host: str, port: int, verbose: bool):
    """Start the Vigil web UI."""
    _setup_logging(verbose)
    import uvicorn

    from vigil.web.app import create_app

    app = create_app()
    click.echo(f"Starting Vigil web UI at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


@main.command(name="list")
def list_runs():
    """List all completed red-team runs."""
    from vigil.storage import get_run, list_runs as _list_runs

    runs = _list_runs()
    if not runs:
        click.echo("No runs found. Run 'vigil run <config.yaml>' to start one.")
        return

    click.echo(f"{'ID':<10} {'Behavior':<30} {'Target':<40} {'Score':>6}")
    click.echo("-" * 90)
    for config in runs:
        result = get_run(config.run_id)
        score = f"{result.summary.avg_behavior_presence}/10" if result else "..."
        click.echo(f"{config.run_id:<10} {config.behavior:<30} {config.target_model:<40} {score:>6}")


@main.command(name="behaviors")
def list_behaviors():
    """List all available behaviors."""
    from vigil.config import load_behaviors

    behaviors = load_behaviors()
    click.echo(f"{'Behavior':<35} {'Category':<12} {'Severity':<10} {'Strategies'}")
    click.echo("-" * 90)
    for key, b in sorted(behaviors.items()):
        click.echo(f"{key:<35} {b.category:<12} {b.severity:<10} {len(b.attack_strategies)}")


@main.command()
@click.option("--model", default="qwen/qwen3-235b-a22b", help="Model for generation")
@click.option("--topic", default="cybersecurity best practices", help="Topic for generated outputs")
@click.option("--items", default=10, help="Number of review items to generate")
@click.option("--issue-ratio", default=0.3, help="Fraction of items with planted issues")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def oversight(model: str, topic: str, items: int, issue_ratio: float, verbose: bool):
    """Generate a human oversight testing session."""
    _setup_logging(verbose)

    from vigil.client import VigilClient
    from vigil.models import OversightSession
    from vigil.oversight.generator import generate_review_batch
    from vigil.storage import save_oversight_session

    async def _generate():
        client = VigilClient()
        try:
            review_items = await generate_review_batch(
                client=client,
                model=model,
                topic=topic,
                num_items=items,
                issue_ratio=issue_ratio,
            )
            session = OversightSession(
                topic=topic,
                model=model,
                num_items=items,
                issue_ratio=issue_ratio,
                items=review_items,
            )
            save_oversight_session(session)
            return session
        finally:
            await client.close()

    session = asyncio.run(_generate())
    click.echo(f"Oversight session created: {session.session_id}")
    click.echo(f"  Items: {len(session.items)} ({int(issue_ratio * 100)}% with issues)")
    click.echo(f"  Topic: {topic}")
    click.echo(f"  Start reviewing at: vigil serve → Human Review")


@main.command()
def init():
    """Initialize a Vigil workspace with example config."""
    from pathlib import Path

    config_path = Path("vigil.yaml")
    if config_path.exists():
        click.echo("vigil.yaml already exists. Skipping.")
    else:
        config_path.write_text(
            "# Vigil red-team configuration\n"
            "# See: vigil behaviors (to list available behaviors)\n"
            "\n"
            "behavior: prompt-injection\n"
            "target_model: meta-llama/llama-3.3-70b-instruct\n"
            "\n"
            "# Attacker and judge models (cost-effective defaults)\n"
            "attacker_model: qwen/qwen3-235b-a22b\n"
            "judge_model: qwen/qwen3-235b-a22b\n"
            "\n"
            "# Evaluation parameters\n"
            "num_scenarios: 3\n"
            "num_turns: 8\n"
            "min_turns: 3\n"
            "attacker_persistence: high  # low, medium, high\n"
            "\n"
            "# Advanced\n"
            "# num_reps: 1\n"
            "# max_concurrent: 5\n"
            "# temperature: 1.0\n"
            "# max_tokens: 4096\n"
        )
        click.echo("Created vigil.yaml — edit it and run 'vigil run vigil.yaml'")

    env_path = Path(".env")
    if not env_path.exists():
        env_path.write_text("OPENROUTER_API_KEY=sk-or-v1-your-key-here\n")
        click.echo("Created .env — add your OpenRouter API key")
    else:
        click.echo(".env already exists.")


if __name__ == "__main__":
    main()
