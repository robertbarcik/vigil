"""Generate compliance evidence reports in HTML and JSON."""

from __future__ import annotations

from vigil.compliance.evidence import collect_evidence
from vigil.models import ComplianceReport, RunResult, OversightSession
from vigil.storage import save_compliance_report


def generate_compliance_report(
    runs: list[RunResult],
    sessions: list[OversightSession],
    organization: str = "",
    title: str = "EU AI Act Compliance Evidence Report",
    campaign_id: str | None = None,
) -> ComplianceReport:
    """Generate a compliance report from runs and sessions."""
    articles = collect_evidence(runs, sessions)

    target_models = list({r.config.target_model for r in runs})
    run_ids = [r.run_id for r in runs]
    session_ids = [s.session_id for s in sessions]

    # Compute overall status
    statuses = [a.status for a in articles]
    if all(s == "addressed" for s in statuses if s != "not_assessed"):
        overall = "addressed"
    elif any(s == "not_addressed" for s in statuses):
        overall = "not_addressed"
    elif any(s == "addressed" or s == "partially_addressed" for s in statuses):
        overall = "partially_addressed"
    else:
        overall = "not_assessed"

    # Generate summary
    assessed = [a for a in articles if a.status != "not_assessed"]
    addressed = sum(1 for a in assessed if a.status == "addressed")
    partial = sum(1 for a in assessed if a.status == "partially_addressed")
    not_addressed = sum(1 for a in assessed if a.status == "not_addressed")

    summary_parts = [
        f"Assessed {len(assessed)} of {len(articles)} relevant EU AI Act articles.",
    ]
    if addressed:
        summary_parts.append(f"{addressed} addressed.")
    if partial:
        summary_parts.append(f"{partial} partially addressed.")
    if not_addressed:
        summary_parts.append(f"{not_addressed} not addressed — action required.")
    if runs:
        summary_parts.append(
            f"Based on {len(runs)} red-team run(s) across {len(target_models)} model(s)."
        )
    if sessions:
        summary_parts.append(f"{len(sessions)} human oversight session(s) evaluated.")

    report = ComplianceReport(
        title=title,
        organization=organization,
        target_models=target_models,
        run_ids=run_ids,
        session_ids=session_ids,
        campaign_id=campaign_id,
        articles=articles,
        overall_status=overall,
        summary_text=" ".join(summary_parts),
    )

    save_compliance_report(report)
    return report


def render_compliance_json(report: ComplianceReport) -> str:
    """Render a compliance report as JSON."""
    return report.model_dump_json(indent=2)


def render_compliance_html(report: ComplianceReport) -> str:
    """Render a compliance report as standalone HTML."""
    status_colors = {
        "addressed": "#22c55e",
        "partially_addressed": "#eab308",
        "not_addressed": "#ef4444",
        "not_assessed": "#6b7280",
    }
    status_labels = {
        "addressed": "Addressed",
        "partially_addressed": "Partially Addressed",
        "not_addressed": "Not Addressed",
        "not_assessed": "Not Assessed",
    }

    articles_html = ""
    for article in report.articles:
        color = status_colors.get(article.status, "#6b7280")
        label = status_labels.get(article.status, article.status)

        findings_html = ""
        if article.red_team_findings:
            findings_html = "<ul>" + "".join(
                f"<li>{f}</li>" for f in article.red_team_findings
            ) + "</ul>"

        articles_html += f"""
        <div class="article" style="border-left: 4px solid {color}; padding: 16px; margin: 16px 0; background: #1a1a2e;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h3 style="margin: 0; color: #e0e0e0;">{article.article}</h3>
                <span style="background: {color}; color: white; padding: 4px 12px; border-radius: 4px; font-size: 0.85em;">{label}</span>
            </div>
            <p style="color: #a0a0a0; margin: 8px 0;">{article.summary}</p>
            <div style="display: flex; gap: 24px; margin-top: 8px; font-size: 0.9em;">
                <span style="color: #9ca3af;">Risk Level: <strong style="color: #e0e0e0;">{article.risk_level}</strong></span>
                <span style="color: #9ca3af;">Avg AI Score: <strong style="color: {'#ef4444' if article.avg_behavior_score > 6 else '#22c55e' if article.avg_behavior_score < 4 else '#eab308'};">{article.avg_behavior_score}/10</strong></span>
                <span style="color: #9ca3af;">Detection Rate: <strong style="color: {'#22c55e' if article.avg_detection_rate > 0.7 else '#ef4444' if article.avg_detection_rate < 0.5 else '#eab308'};">{article.avg_detection_rate:.0%}</strong></span>
            </div>
            {findings_html}
        </div>
        """

    overall_color = status_colors.get(report.overall_status, "#6b7280")
    overall_label = status_labels.get(report.overall_status, report.overall_status)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report.title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f23; color: #e0e0e0; max-width: 900px; margin: 0 auto; padding: 40px 20px; }}
        h1 {{ color: #38bdf8; }}
        h2 {{ color: #e0e0e0; border-bottom: 1px solid #333; padding-bottom: 8px; }}
        .meta {{ color: #9ca3af; font-size: 0.9em; margin: 16px 0; }}
        .overall {{ display: inline-block; background: {overall_color}; color: white; padding: 8px 20px; border-radius: 6px; font-size: 1.1em; font-weight: bold; }}
        .summary {{ background: #1a1a2e; padding: 20px; border-radius: 8px; margin: 20px 0; line-height: 1.6; }}
        ul {{ color: #9ca3af; }}
        .footer {{ color: #6b7280; font-size: 0.8em; margin-top: 40px; border-top: 1px solid #333; padding-top: 16px; }}
    </style>
</head>
<body>
    <h1>{report.title}</h1>
    <div class="meta">
        {f'<strong>Organization:</strong> {report.organization}<br>' if report.organization else ''}
        <strong>Generated:</strong> {report.created_at.strftime('%Y-%m-%d %H:%M UTC')}<br>
        <strong>Models Tested:</strong> {', '.join(report.target_models) or 'None'}<br>
        <strong>Red-Team Runs:</strong> {len(report.run_ids)} &middot; <strong>Oversight Sessions:</strong> {len(report.session_ids)}
    </div>

    <h2>Overall Status</h2>
    <div class="overall">{overall_label}</div>
    <div class="summary">{report.summary_text}</div>

    <h2>Article-by-Article Evidence</h2>
    {articles_html}

    <div class="footer">
        Generated by Vigil v0.2.0 — LLM Red-Teaming & Human Oversight Testing Framework<br>
        Report ID: {report.report_id}
    </div>
</body>
</html>"""
