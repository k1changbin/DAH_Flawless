"""Build the DAH preliminary source ZIP without local caches."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


EXCLUDED_DIRS = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".DS_Store",
}

INCLUDED_ROOTS = [
    "README.md",
    "requirements.txt",
    "pyproject.toml",
    "Dockerfile",
    "streamlit_app.py",
    "configs",
    "docs",
    "src",
    "tests",
    "data/logs",
    "reports/figures",
    "reports/evidence_trace.md",
    "reports/submission_checklist.md",
    "reports/prelim_report_draft.md",
    "reports/DAH2026_prelim_report_DAH_Flawless_draft.pdf",
    "scripts",
]


def build_zip(project_root: Path, team_name: str) -> Path:
    dist_dir = project_root / "dist"
    dist_dir.mkdir(exist_ok=True)
    archive = dist_dir / f"DAH2026_소스코드_{team_name}.zip"

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root in INCLUDED_ROOTS:
            path = project_root / root
            if not path.exists():
                continue
            if path.is_file():
                _write_file(zf, project_root, path)
            else:
                for child in path.rglob("*"):
                    if child.is_file() and not _is_excluded(child):
                        _write_file(zf, project_root, child)
    return archive


def _write_file(zf: zipfile.ZipFile, project_root: Path, path: Path) -> None:
    zf.write(path, path.relative_to(project_root))


def _is_excluded(path: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True
    if path.name in EXCLUDED_SUFFIXES:
        return True
    return path.suffix in EXCLUDED_SUFFIXES


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DAH 2026 source-code submission ZIP")
    parser.add_argument("--team-name", default="DAH_Flawless", help="Team name segment for the archive filename")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    archive = build_zip(project_root, args.team_name)
    print(archive)


if __name__ == "__main__":
    main()
