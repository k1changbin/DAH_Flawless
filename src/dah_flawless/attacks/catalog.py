"""Attack catalog for the MVP."""

from __future__ import annotations

from dah_flawless.schemas import Attack


ATTACK_CATALOG: dict[str, Attack] = {
    "PRIORITY_POISONING": Attack(
        name="PRIORITY_POISONING",
        feasibility="real",
        weight=5.0,
        preferred_tags=("PAYLOAD_HIDDEN", "C2_ENCRYPTED"),
        target_domain="mission",
    ),
    "TELEMETRY_FDI": Attack(
        name="TELEMETRY_FDI",
        feasibility="real",
        weight=5.0,
        preferred_tags=("GNSS_PRIMARY", "C2_ENCRYPTED", "CROSS_CHECK_UNAVAILABLE"),
        target_domain="telemetry",
    ),
    "TIME_DESYNC_REPLAY": Attack(
        name="TIME_DESYNC_REPLAY",
        feasibility="real",
        weight=5.0,
        preferred_tags=("HIGH_LATENCY", "PACKET_LOSS_HIGH", "C2_ENCRYPTED"),
        target_domain="command",
    ),
    "DIRECT_DECRYPTION": Attack(
        name="DIRECT_DECRYPTION",
        feasibility="out_of_scope",
        weight=0.0,
        preferred_tags=("CRYPTO_WEAKNESS_HINT",),
        target_domain="comms",
    ),
}


def get_attack(name: str) -> Attack:
    try:
        return ATTACK_CATALOG[name]
    except KeyError as exc:
        raise ValueError(f"unknown attack: {name}") from exc


def realistic_attacks() -> list[Attack]:
    return [attack for attack in ATTACK_CATALOG.values() if attack.weight > 0 and attack.feasibility == "real"]
