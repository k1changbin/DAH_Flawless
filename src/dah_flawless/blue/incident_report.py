"""Incident report snippets for logs and report evidence."""

from __future__ import annotations

from dah_flawless.schemas import DefenseAction, MissionRisk, Score, Threat, decision


def write_incident_report(
    threats: list[Threat],
    risks: list[MissionRisk],
    actions: list[DefenseAction],
    score: Score,
) -> tuple[dict, dict]:
    report = {
        "summary": f"{score.target_domain} domain judged as {score.winner}",
        "threat_count": len(threats),
        "risk_count": len(risks),
        "actions": [action.action for action in actions],
        "winner": score.winner,
    }
    log = decision(
        "IncidentReportAgent",
        "incident_summary_written",
        "operator_report",
        before=None,
        after=report,
    )
    return report, log
