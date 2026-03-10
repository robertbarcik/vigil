"""Vigil CLI — command-line interface."""

from __future__ import annotations

import asyncio
import logging

import click


def _setup_logging(verbose: bool, log_file: str | None = None) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
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
    from vigil.config import get_run_dir, load_config
    from vigil.pipeline.core import run_pipeline

    config = load_config(config_path)
    log_path = get_run_dir(config.run_id) / "run.log"
    _setup_logging(verbose, log_file=str(log_path))

    click.echo(f"Starting Vigil run {config.run_id}")
    click.echo(f"  Behavior:    {config.behavior}")
    click.echo(f"  Target:      {config.target_model}")
    click.echo(f"  Attacker:    {config.attacker_model}")
    click.echo(f"  Judge:       {config.judge_model}")
    click.echo(f"  Scenarios:   {config.num_scenarios}")
    click.echo(f"  Turns:       {config.min_turns}-{config.num_turns}")
    click.echo(f"  Persistence: {config.attacker_persistence}")
    click.echo(f"  Log:         {log_path}")
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

    from vigil.config import get_run_dir

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
        log_path = get_run_dir(config.run_id) / "run.log"
        _setup_logging(verbose, log_file=str(log_path))
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
@click.option("--from-run", "from_run", default=None, help="Create closed-loop session from red-team run ID")
@click.option("--threshold", default=6.0, help="Score threshold for compromised transcripts (closed-loop)")
@click.option("--safe-ratio", default=0.4, help="Fraction of clean items in closed-loop session")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def oversight(model: str, topic: str, items: int, issue_ratio: float,
              from_run: str | None, threshold: float, safe_ratio: float, verbose: bool):
    """Generate a human oversight testing session.

    Use --from-run to create a closed-loop session from red-team transcripts.
    """
    _setup_logging(verbose)

    if from_run:
        from vigil.oversight.closed_loop import create_closed_loop_session
        from vigil.storage import get_run, save_oversight_session

        result = get_run(from_run)
        if not result:
            click.echo(f"Run not found: {from_run}")
            raise SystemExit(1)

        session = create_closed_loop_session(
            result, threshold=threshold, safe_ratio=safe_ratio,
        )
        save_oversight_session(session)

        compromised = sum(1 for i in session.items if i.has_issue)
        clean = len(session.items) - compromised
        click.echo(f"Closed-loop oversight session created: {session.session_id}")
        click.echo(f"  Source run: {from_run}")
        click.echo(f"  Items: {len(session.items)} ({compromised} compromised, {clean} clean)")
        click.echo(f"  Threshold: {threshold}")
        if compromised > 0 and clean == 0:
            click.echo()
            click.echo(
                "  WARNING: All transcripts scored above threshold — no clean items available."
            )
            click.echo(
                "  A reviewer can achieve 100% detection by flagging everything."
            )
            click.echo(
                "  Consider lowering --threshold or running more scenarios to get a mix."
            )
        click.echo("  Start reviewing at: vigil serve → Human Review")
        return

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
    click.echo("  Start reviewing at: vigil serve → Human Review")


@main.group()
def campaign():
    """Manage oversight campaigns."""
    pass


@campaign.command(name="create")
@click.option("--name", required=True, help="Campaign name")
@click.option("--description", default="", help="Campaign description")
def campaign_create(name: str, description: str):
    """Create a new oversight campaign."""
    from vigil.oversight.campaigns import create_campaign

    c = create_campaign(name, description)
    click.echo(f"Campaign created: {c.campaign_id}")
    click.echo(f"  Name: {c.name}")


@campaign.command(name="add-session")
@click.argument("campaign_id")
@click.argument("session_id")
def campaign_add_session(campaign_id: str, session_id: str):
    """Add an oversight session to a campaign."""
    from vigil.oversight.campaigns import add_session_to_campaign

    try:
        c = add_session_to_campaign(campaign_id, session_id)
        click.echo(f"Added session {session_id} to campaign {campaign_id}")
        click.echo(f"  Total sessions: {len(c.session_ids)}")
    except ValueError as e:
        click.echo(str(e))
        raise SystemExit(1)


@campaign.command(name="list")
def campaign_list():
    """List all campaigns."""
    from vigil.storage import list_campaigns

    campaigns = list_campaigns()
    if not campaigns:
        click.echo("No campaigns found. Create one with: vigil campaign create --name 'My Campaign'")
        return

    click.echo(f"{'ID':<10} {'Name':<30} {'Sessions':>10} {'Reviewers':>10}")
    click.echo("-" * 65)
    for c in campaigns:
        click.echo(f"{c.campaign_id:<10} {c.name:<30} {len(c.session_ids):>10} {len(c.reviewer_ids):>10}")


@campaign.command(name="show")
@click.argument("campaign_id")
def campaign_show(campaign_id: str):
    """Show campaign details and trends."""
    from vigil.oversight.campaigns import detect_fatigue, get_campaign_trends
    from vigil.storage import load_campaign

    c = load_campaign(campaign_id)
    if not c:
        click.echo(f"Campaign not found: {campaign_id}")
        raise SystemExit(1)

    click.echo(f"Campaign: {c.name}")
    click.echo(f"  ID: {c.campaign_id}")
    if c.description:
        click.echo(f"  Description: {c.description}")
    click.echo(f"  Sessions: {len(c.session_ids)}")
    click.echo(f"  Reviewers: {', '.join(c.reviewer_ids) if c.reviewer_ids else 'None'}")
    click.echo()

    for reviewer_id in c.reviewer_ids:
        trends = get_campaign_trends(campaign_id, reviewer_id)
        if not trends:
            continue

        click.echo(f"  Reviewer: {reviewer_id}")
        click.echo(f"  {'Session':<10} {'Vigilance':>10} {'Detection':>10} {'Precision':>10} {'Items':>6}")
        click.echo(f"  {'-' * 50}")
        for t in trends:
            click.echo(
                f"  {t.session_id:<10} {t.vigilance_score:>9.0%} "
                f"{t.detection_rate:>9.0%} {t.precision:>9.0%} {t.items_reviewed:>6}"
            )

        fatigue = detect_fatigue(trends)
        if fatigue["fatigued"]:
            click.echo(f"  ⚠ FATIGUE WARNING: {fatigue['reason']}")
        click.echo()


@main.command(name="report")
@click.option("--campaign", "campaign_id", default=None, help="Generate from campaign")
@click.option("--run", "run_id", default=None, help="Include specific run")
@click.option("--session", "session_id", default=None, help="Include specific oversight session")
@click.option("--org", default="", help="Organization name")
def report(campaign_id: str | None, run_id: str | None, session_id: str | None, org: str):
    """Generate an EU AI Act compliance evidence report."""
    from vigil.compliance.report import generate_compliance_report, render_compliance_html
    from vigil.storage import get_run, load_campaign, load_oversight_session

    runs = []
    sessions = []

    if campaign_id:
        c = load_campaign(campaign_id)
        if not c:
            click.echo(f"Campaign not found: {campaign_id}")
            raise SystemExit(1)
        for sid in c.session_ids:
            s = load_oversight_session(sid)
            if s:
                sessions.append(s)
                # Also load linked runs from closed-loop sessions
                if s.source_run_id:
                    r = get_run(s.source_run_id)
                    if r and r.run_id not in [x.run_id for x in runs]:
                        runs.append(r)

    if run_id:
        r = get_run(run_id)
        if not r:
            click.echo(f"Run not found: {run_id}")
            raise SystemExit(1)
        if r.run_id not in [x.run_id for x in runs]:
            runs.append(r)

    if session_id:
        s = load_oversight_session(session_id)
        if not s:
            click.echo(f"Session not found: {session_id}")
            raise SystemExit(1)
        if s.session_id not in [x.session_id for x in sessions]:
            sessions.append(s)

    if not runs and not sessions:
        click.echo("No data specified. Use --campaign, --run, or --session.")
        raise SystemExit(1)

    report_obj = generate_compliance_report(
        runs, sessions, organization=org, campaign_id=campaign_id,
    )

    # Write HTML file
    html = render_compliance_html(report_obj)
    from pathlib import Path
    html_path = Path(f"vigil_compliance_{report_obj.report_id}.html")
    html_path.write_text(html)

    click.echo(f"Compliance report generated: {report_obj.report_id}")
    click.echo(f"  Status: {report_obj.overall_status}")
    click.echo(f"  Articles assessed: {sum(1 for a in report_obj.articles if a.status != 'not_assessed')}")
    click.echo(f"  HTML: {html_path}")
    click.echo(f"  JSON: ~/.vigil/compliance/{report_obj.report_id}/report.json")


@main.group()
def probes():
    """Manage production probe pools for Level 3 oversight."""
    pass


@probes.command(name="create")
@click.argument("session_id")
@click.option("--description", default="", help="Pool description")
@click.option("--ttl", default=0, help="Probe TTL in hours (0 = no expiry)")
def probes_create(session_id: str, description: str, ttl: int):
    """Create a probe pool from an oversight session."""
    from vigil.oversight.probes import create_probe_pool
    from vigil.storage import load_oversight_session

    session = load_oversight_session(session_id)
    if not session:
        click.echo(f"Session not found: {session_id}")
        raise SystemExit(1)

    pool = create_probe_pool(session, description=description, probe_ttl_hours=ttl)
    issues = sum(1 for p in pool.probes if p.has_issue)
    click.echo(f"Probe pool created: {pool.pool_id}")
    click.echo(f"  Source session: {session_id}")
    click.echo(f"  Probes: {len(pool.probes)} ({issues} with issues, {len(pool.probes) - issues} clean)")
    if ttl:
        click.echo(f"  TTL: {ttl} hours")
    click.echo(f"  Draw probes via API: POST /api/probes/pools/{pool.pool_id}/next")


@probes.command(name="list")
def probes_list():
    """List all probe pools."""
    from vigil.oversight.probes import get_pool_stats
    from vigil.storage import list_probe_pools

    pools = list_probe_pools()
    if not pools:
        click.echo("No probe pools. Create one with: vigil probes create <session_id>")
        return

    click.echo(f"{'ID':<10} {'Description':<30} {'Total':>6} {'Avail':>6} {'Done':>6}")
    click.echo("-" * 65)
    for pool in pools:
        stats = get_pool_stats(pool)
        click.echo(
            f"{pool.pool_id:<10} {pool.description[:30]:<30} "
            f"{stats['total']:>6} {stats['available']:>6} {stats['completed']:>6}"
        )


@probes.command(name="show")
@click.argument("pool_id")
def probes_show(pool_id: str):
    """Show probe pool details and scoring results."""
    from vigil.oversight.probes import get_pool_stats
    from vigil.storage import load_probe_pool

    pool = load_probe_pool(pool_id)
    if not pool:
        click.echo(f"Pool not found: {pool_id}")
        raise SystemExit(1)

    stats = get_pool_stats(pool)
    click.echo(f"Probe Pool: {pool.pool_id}")
    click.echo(f"  Description: {pool.description}")
    click.echo(f"  Source session: {pool.source_session_id}")
    if pool.source_run_id:
        click.echo(f"  Source run: {pool.source_run_id}")
    click.echo()
    click.echo(f"  Total probes:  {stats['total']}")
    click.echo(f"  Available:     {stats['available']}")
    click.echo(f"  Injected:      {stats['injected']}")
    click.echo(f"  Completed:     {stats['completed']}")
    click.echo(f"  Expired:       {stats['expired']}")

    if stats['completed'] > 0:
        click.echo()
        click.echo("  Scoring:")
        click.echo(f"    Detection rate: {stats['detection_rate']:.0%}")
        click.echo(f"    Precision:      {stats['precision']:.0%}")
        click.echo(f"    Avg response:   {stats['avg_response_time']:.1f}s")
        click.echo(f"    TP={stats['true_positives']} FP={stats['false_positives']} "
                   f"FN={stats['false_negatives']} TN={stats['true_negatives']}")


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
