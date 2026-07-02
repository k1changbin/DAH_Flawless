"""Generate report figures from JSONL logs.

The module always writes SVG files and writes PNG files when Pillow is
available. The PNG outputs are intended for direct insertion into the
preliminary report.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from textwrap import wrap
from typing import Any

from dah_flawless.environment.hash_log import read_jsonl


def generate_figures(log_path: Path, out_dir: Path) -> list[Path]:
    logs = read_jsonl(log_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = [
        _write_scoreboard(logs, out_dir / "scoreboard"),
        _write_world_observed_diff(logs, out_dir / "world_observed_diff"),
        _write_availability(logs, out_dir / "availability"),
        _write_agent_architecture(out_dir / "agent_architecture"),
        _write_detect_contain_recover(logs, out_dir / "detect_contain_recover"),
        _write_attack_flow(logs, out_dir / "attack_flow"),
    ]
    return [path for group in outputs for path in group]


def _write_scoreboard(logs: list[dict], stem: Path) -> list[Path]:
    rows = []
    y = 82
    for entry in logs:
        rows.append(
            _svg_text(30, y, f'R{entry["round"]}', 16)
            + _svg_text(110, y, entry["attack"]["name"], 16)
            + _svg_text(360, y, entry["score"]["winner"], 16)
            + _svg_text(560, y, f'{entry["score"]["availability"]:.2f}', 16)
        )
        y += 34
    body = (
        _svg_text(30, 36, "Round Scoreboard", 22, weight=700)
        + _svg_text(30, 60, "round / attack / winner / availability", 13, fill="#475569")
        + "".join(rows)
    )
    svg_path = _write_svg(stem.with_suffix(".svg"), 760, max(180, y + 35), body)
    png_path = _write_scoreboard_png(logs, stem.with_suffix(".png"))
    return _existing(svg_path, png_path)


def _write_world_observed_diff(logs: list[dict], stem: Path) -> list[Path]:
    blocks = []
    y = 78
    for entry in logs:
        evidence = entry["score"]["evidence"]
        blocks.append(_svg_text(30, y, f'R{entry["round"]} {entry["attack"]["name"]}', 17, weight=700))
        y += 24
        for line in wrap(f'trusted: {_compact(evidence["trusted_value"], 140)}', width=118):
            blocks.append(_svg_text(50, y, line, 14))
            y += 20
        for line in wrap(f'observed: {_compact(evidence["observed_value"], 140)}', width=118):
            blocks.append(_svg_text(50, y, line, 14, fill="#b91c1c"))
            y += 20
        y += 18
    body = (
        _svg_text(30, 36, "World vs Observed Diff", 22, weight=700)
        + _svg_text(30, 60, "Scorer/Admin evidence. Blue input remains redacted.", 13, fill="#475569")
        + "".join(blocks)
    )
    svg_path = _write_svg(stem.with_suffix(".svg"), 1080, max(240, y + 35), body)
    png_path = _write_diff_png(logs, stem.with_suffix(".png"))
    return _existing(svg_path, png_path)


def _write_availability(logs: list[dict], stem: Path) -> list[Path]:
    width = 760
    height = 280
    left = 64
    bottom = 220
    top = 52
    right = 720
    points = []
    if logs:
        for idx, entry in enumerate(logs):
            x = left + (right - left) * idx / max(1, len(logs) - 1)
            y = bottom - (bottom - top) * entry["score"]["availability"]
            points.append((x, y))
    point_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#1d4ed8"/>' for x, y in points)
    body = (
        _svg_text(30, 32, "Availability Curve", 22, weight=700)
        + f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#94a3b8"/>'
        + f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#94a3b8"/>'
        + f'<line x1="{left}" y1="{bottom - (bottom - top) * 0.5:.1f}" x2="{right}" y2="{bottom - (bottom - top) * 0.5:.1f}" stroke="#ef4444" stroke-dasharray="6 5"/>'
        + f'<polyline points="{point_attr}" fill="none" stroke="#1d4ed8" stroke-width="3"/>'
        + circles
        + _svg_text(30, 250, "Defense cost lowers availability; below 0.5 is RED_ATTRITION.", 13, fill="#475569")
    )
    svg_path = _write_svg(stem.with_suffix(".svg"), width, height, body)
    png_path = _write_availability_png(logs, stem.with_suffix(".png"))
    return _existing(svg_path, png_path)


def _write_agent_architecture(stem: Path) -> list[Path]:
    boxes = [
        ("Red Agent", "observe tags -> choose attack -> mutate observed", 40, 84),
        ("Environment", "keeps world, applies observed-only mutation", 40, 178),
        ("Blue Agents", "Threat -> Mission -> Planner -> Report", 420, 178),
        ("Scorer/Admin", "compares world and observed, emits winner", 420, 84),
        ("Hash Log", "JSONL evidence with prev_hash / this_hash", 230, 296),
    ]
    body = _svg_text(30, 36, "Agent Architecture and Truth Boundary", 22, weight=700)
    for title, text, x, y in boxes:
        body += _svg_box(x, y, 310, 68, title, text)
    body += _svg_line(195, 152, 195, 178)
    body += _svg_line(350, 212, 420, 212)
    body += _svg_line(575, 178, 575, 152)
    body += _svg_line(420, 118, 350, 118)
    body += _svg_line(350, 330, 420, 246)
    body += _svg_text(42, 390, "Boundary rule: Red and Blue receive redacted observed state. Only Environment and Scorer retain world.", 14, fill="#475569")
    svg_path = _write_svg(stem.with_suffix(".svg"), 780, 430, body)
    png_path = _write_static_boxes_png(stem.with_suffix(".png"), "Agent Architecture and Truth Boundary", boxes)
    return _existing(svg_path, png_path)


def _write_detect_contain_recover(logs: list[dict], stem: Path) -> list[Path]:
    rows = []
    seen = set()
    for entry in logs:
        attack = entry["attack"]["name"]
        if attack in seen:
            continue
        seen.add(attack)
        threat_tags = ", ".join(tag for threat in entry["threats"] for tag in threat["tags"])
        actions = ", ".join(action["action"] for action in entry["defense_actions"])
        recovery = "trusted fallback" if entry["score"]["recovery_success"] else "hold/revalidate"
        rows.append((attack, threat_tags, actions, recovery))

    y = 84
    body = _svg_text(30, 36, "Detect / Contain / Recover Evidence", 22, weight=700)
    body += _svg_text(30, 62, "Attack-specific report view; internal Blue detection remains invariant-based.", 13, fill="#475569")
    for attack, detect, contain, recover in rows:
        body += _svg_text(30, y, attack, 16, weight=700)
        y += 22
        for label, value in (("Detect", detect), ("Contain", contain), ("Recover", recover)):
            body += _svg_text(48, y, f"{label}: {value}", 13)
            y += 18
        y += 16
    svg_path = _write_svg(stem.with_suffix(".svg"), 980, max(250, y + 30), body)
    png_path = _write_dcr_png(rows, stem.with_suffix(".png"))
    return _existing(svg_path, png_path)


def _write_attack_flow(logs: list[dict], stem: Path) -> list[Path]:
    rows = []
    seen = set()
    for entry in logs:
        attack = entry["attack"]["name"]
        if attack in seen:
            continue
        seen.add(attack)
        evidence = entry["score"]["evidence"]
        rows.append(
            (
                attack,
                entry["attack"]["target_domain"],
                _compact(evidence["observed_value"], 70),
                entry["score"]["winner"],
            )
        )
    y = 84
    body = _svg_text(30, 36, "Attack Flow Summary", 22, weight=700)
    body += _svg_text(30, 62, "Operational situation -> observed mutation -> Blue response -> score.", 13, fill="#475569")
    for attack, target, observed, winner in rows:
        body += _svg_text(30, y, f"{attack} ({target})", 16, weight=700)
        y += 22
        for line in wrap(f"observed mutation: {observed}", width=110):
            body += _svg_text(48, y, line, 13)
            y += 18
        body += _svg_text(48, y, f"result: {winner}", 13, fill="#2563eb")
        y += 34
    svg_path = _write_svg(stem.with_suffix(".svg"), 980, max(250, y + 30), body)
    png_path = _write_attack_flow_png(rows, stem.with_suffix(".png"))
    return _existing(svg_path, png_path)


def _write_scoreboard_png(logs: list[dict], path: Path) -> Path | None:
    image, draw, font, bold = _new_png(760, max(220, 120 + len(logs) * 38))
    if image is None:
        return None
    draw.text((30, 26), "Round Scoreboard", fill="#0f172a", font=bold)
    draw.text((30, 58), "round / attack / winner / availability", fill="#475569", font=font)
    y = 92
    for entry in logs:
        draw.text((30, y), f'R{entry["round"]}', fill="#0f172a", font=font)
        draw.text((110, y), entry["attack"]["name"], fill="#0f172a", font=font)
        draw.text((360, y), entry["score"]["winner"], fill="#0f172a", font=font)
        draw.text((560, y), f'{entry["score"]["availability"]:.2f}', fill="#0f172a", font=font)
        y += 38
    image.save(path)
    return path


def _write_diff_png(logs: list[dict], path: Path) -> Path | None:
    image, draw, font, bold = _new_png(1080, max(320, 150 + len(logs) * 116))
    if image is None:
        return None
    draw.text((30, 26), "World vs Observed Diff", fill="#0f172a", font=bold)
    draw.text((30, 58), "Scorer/Admin evidence. Blue input remains redacted.", fill="#475569", font=font)
    y = 96
    for entry in logs:
        evidence = entry["score"]["evidence"]
        draw.text((30, y), f'R{entry["round"]} {entry["attack"]["name"]}', fill="#0f172a", font=bold)
        y += 24
        y = _draw_wrapped(draw, f'trusted: {_compact(evidence["trusted_value"], 130)}', 50, y, 118, font, "#0f172a")
        y = _draw_wrapped(draw, f'observed: {_compact(evidence["observed_value"], 130)}', 50, y, 118, font, "#b91c1c")
        y += 18
    image.save(path)
    return path


def _write_availability_png(logs: list[dict], path: Path) -> Path | None:
    image, draw, font, bold = _new_png(760, 280)
    if image is None:
        return None
    draw.text((30, 22), "Availability Curve", fill="#0f172a", font=bold)
    left, bottom, top, right = 64, 220, 52, 720
    draw.line((left, bottom, right, bottom), fill="#94a3b8", width=1)
    draw.line((left, top, left, bottom), fill="#94a3b8", width=1)
    floor_y = bottom - (bottom - top) * 0.5
    draw.line((left, floor_y, right, floor_y), fill="#ef4444", width=1)
    points = []
    for idx, entry in enumerate(logs):
        x = left + (right - left) * idx / max(1, len(logs) - 1)
        y = bottom - (bottom - top) * entry["score"]["availability"]
        points.append((x, y))
    if len(points) > 1:
        draw.line(points, fill="#1d4ed8", width=3)
    for x, y in points:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="#1d4ed8")
    draw.text((30, 248), "Defense cost lowers availability; below 0.5 is RED_ATTRITION.", fill="#475569", font=font)
    image.save(path)
    return path


def _write_static_boxes_png(path: Path, title: str, boxes: list[tuple[str, str, int, int]]) -> Path | None:
    image, draw, font, bold = _new_png(780, 430)
    if image is None:
        return None
    draw.text((30, 26), title, fill="#0f172a", font=bold)
    for box_title, text, x, y in boxes:
        draw.rounded_rectangle((x, y, x + 310, y + 68), radius=8, outline="#1d4ed8", width=2, fill="#eff6ff")
        draw.text((x + 14, y + 12), box_title, fill="#0f172a", font=bold)
        draw.text((x + 14, y + 38), text, fill="#475569", font=font)
    draw.text((42, 390), "Boundary rule: Red and Blue receive redacted observed state. Only Environment and Scorer retain world.", fill="#475569", font=font)
    image.save(path)
    return path


def _write_dcr_png(rows: list[tuple[str, str, str, str]], path: Path) -> Path | None:
    image, draw, font, bold = _new_png(980, max(300, 124 + len(rows) * 112))
    if image is None:
        return None
    draw.text((30, 26), "Detect / Contain / Recover Evidence", fill="#0f172a", font=bold)
    draw.text((30, 58), "Attack-specific report view; internal Blue detection remains invariant-based.", fill="#475569", font=font)
    y = 96
    for attack, detect, contain, recover in rows:
        draw.text((30, y), attack, fill="#0f172a", font=bold)
        y += 24
        y = _draw_wrapped(draw, f"Detect: {detect}", 48, y, 115, font, "#0f172a")
        y = _draw_wrapped(draw, f"Contain: {contain}", 48, y, 115, font, "#0f172a")
        y = _draw_wrapped(draw, f"Recover: {recover}", 48, y, 115, font, "#0f172a")
        y += 14
    image.save(path)
    return path


def _write_attack_flow_png(rows: list[tuple[str, str, str, str]], path: Path) -> Path | None:
    image, draw, font, bold = _new_png(980, max(300, 124 + len(rows) * 106))
    if image is None:
        return None
    draw.text((30, 26), "Attack Flow Summary", fill="#0f172a", font=bold)
    draw.text((30, 58), "Operational situation -> observed mutation -> Blue response -> score.", fill="#475569", font=font)
    y = 96
    for attack, target, observed, winner in rows:
        draw.text((30, y), f"{attack} ({target})", fill="#0f172a", font=bold)
        y += 24
        y = _draw_wrapped(draw, f"observed mutation: {observed}", 48, y, 110, font, "#0f172a")
        draw.text((48, y), f"result: {winner}", fill="#2563eb", font=font)
        y += 34
    image.save(path)
    return path


def _new_png(width: int, height: int):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None, None, None, None

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Arial.ttf", 15)
        bold = ImageFont.truetype("Arial Bold.ttf", 21)
    except OSError:
        font = ImageFont.load_default()
        bold = ImageFont.load_default()
    return image, draw, font, bold


def _draw_wrapped(draw: Any, text: str, x: int, y: int, width: int, font: Any, fill: str) -> int:
    for line in wrap(text, width=width):
        draw.text((x, y), line, fill=fill, font=font)
        y += 19
    return y


def _write_svg(path: Path, width: int, height: int, body: str) -> Path:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        'font-family="Arial, Apple SD Gothic Neo, Malgun Gothic, sans-serif">'
        '<rect width="100%" height="100%" fill="#ffffff"/>'
        f"{body}</svg>"
    )
    path.write_text(svg, encoding="utf-8")
    return path


def _svg_text(x: int | float, y: int | float, value: str, size: int, fill: str = "#0f172a", weight: int | None = None) -> str:
    weight_attr = f' font-weight="{weight}"' if weight else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{weight_attr}>{_e(value)}</text>'


def _svg_box(x: int, y: int, width: int, height: int, title: str, text: str) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" fill="#eff6ff" stroke="#1d4ed8" stroke-width="2"/>'
        + _svg_text(x + 14, y + 25, title, 16, weight=700)
        + _svg_text(x + 14, y + 50, text, 13, fill="#475569")
    )


def _svg_line(x1: int, y1: int, x2: int, y2: int) -> str:
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#334155" stroke-width="2"/>'


def _compact(value: Any, limit: int) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _existing(*paths: Path | None) -> list[Path]:
    return [path for path in paths if path is not None and path.exists()]


def _e(value: str) -> str:
    return html.escape(value, quote=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate report figures from DAH Flawless logs")
    parser.add_argument("--log", type=Path, default=Path("data/logs/round_logs.jsonl"))
    parser.add_argument("--out-dir", type=Path, default=Path("reports/figures"))
    args = parser.parse_args()
    outputs = generate_figures(args.log, args.out_dir)
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
