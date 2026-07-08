"""Mission impact estimates for detected threats."""

from __future__ import annotations

from typing import Any

from dah_flawless.schemas import MissionRisk, Threat, decision


def estimate_mission_risk(
    redacted_state: dict,
    threats: list[Threat],
    zta_decisions: list[Any] | None = None,
) -> tuple[list[MissionRisk], dict]:
    risks: list[MissionRisk] = []

    for threat in threats:
        if threat.target == "telemetry":
            risks.append(MissionRisk("telemetry", "return decision may be delayed", 0.18, "state health cannot be trusted"))
        elif threat.target == "mission":
            risks.append(MissionRisk("mission", "wrong reconnaissance area may be selected", 0.12, "priority update lacks evidence"))
        elif threat.target == "command":
            risks.append(MissionRisk("command", "stale command may override safe return", 0.20, "replay indicators present"))

    risk_domains = {risk.target for risk in risks}
    for item in zta_decisions or []:
        domain = getattr(item, "domain", None)
        restrictive = bool(getattr(item, "restrictive", False))
        if not restrictive or domain in risk_domains:
            continue
        risks.append(_zta_policy_risk(item))
        risk_domains.add(domain)

    log = decision(
        "MissionMonitorAgent",
        "mission_risk_estimated",
        "threat_to_mission_impact",
        before={
            "threats": [threat.to_dict() for threat in threats],
            "zta_restrictive_decisions": [
                item.to_dict() for item in zta_decisions or [] if bool(getattr(item, "restrictive", False))
            ],
        },
        after=[risk.to_dict() for risk in risks],
    )
    return risks, log


def _zta_policy_risk(item: Any) -> MissionRisk:
    if item.domain == "telemetry":
        return MissionRisk(
            "telemetry",
            "telemetry may be used only as non-authoritative evidence",
            0.10,
            f"zero trust gate decision {item.decision}",
        )
    if item.domain == "mission":
        return MissionRisk(
            "mission",
            "mission recommendation requires corroboration before tasking",
            0.08,
            f"zero trust gate decision {item.decision}",
        )
    if item.domain == "command":
        return MissionRisk(
            "command",
            "command path should be held or revalidated before execution",
            0.12,
            f"zero trust gate decision {item.decision}",
        )
    return MissionRisk(
        str(item.domain),
        "external observe use is restricted by policy",
        0.05,
        f"zero trust gate decision {item.decision}",
    )
