"""Mission impact estimates for detected threats."""

from __future__ import annotations

from dah_flawless.schemas import MissionRisk, Threat, decision


def estimate_mission_risk(redacted_state: dict, threats: list[Threat]) -> tuple[list[MissionRisk], dict]:
    risks: list[MissionRisk] = []

    for threat in threats:
        if threat.target == "telemetry":
            risks.append(MissionRisk("telemetry", "return decision may be delayed", 0.18, "state health cannot be trusted"))
        elif threat.target == "mission":
            risks.append(MissionRisk("mission", "wrong reconnaissance area may be selected", 0.12, "priority update lacks evidence"))
        elif threat.target == "command":
            risks.append(MissionRisk("command", "stale command may override safe return", 0.20, "replay indicators present"))

    log = decision(
        "MissionMonitorAgent",
        "mission_risk_estimated",
        "threat_to_mission_impact",
        before=[threat.to_dict() for threat in threats],
        after=[risk.to_dict() for risk in risks],
    )
    return risks, log
