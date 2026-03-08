"""Vigil CLI — command-line interface."""

from __future__ import annotations

import asyncio
import logging
import sys

import click


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


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
    click.echo(f"  Behavior: {config.behavior}")
    click.echo(f"  Target:   {config.target_model}")
    click.echo(f"  Attacker: {config.attacker_model}")
    click.echo(f"  Judge:    {config.judge_model}")
    click.echo()

    result = asyncio.run(run_pipeline(config))

    click.echo()
    click.echo(f"Avg behavior presence: {result.summary.avg_behavior_presence}/10")
    click.echo(f"Elicitation rate: {result.summary.elicitation_rate:.0%}")
    click.echo(f"Results saved to: ~/.vigil/runs/{result.run_id}/")


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
    """List all red-team runs."""
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


@main.command()
@click.option("--model", default="anthropic/claude-sonnet-4", help="Model for generation")
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
    import shutil

    example_src = Path(__file__).parent.parent.parent / "configs" / "example.yaml"
    example_dst = Path("vigil.yaml")

    if example_dst.exists():
        click.echo("vigil.yaml already exists. Skipping.")
    else:
        if example_src.exists():
            shutil.copy(example_src, example_dst)
        else:
            example_dst.write_text(
                "# Vigil configuration\n"
                "behavior: prompt-injection\n"
                "target_model: meta-llama/llama-3.3-70b-instruct\n"
                "attacker_model: anthropic/claude-sonnet-4\n"
                "judge_model: anthropic/claude-sonnet-4\n"
                "num_scenarios: 3\n"
                "num_turns: 8\n"
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
