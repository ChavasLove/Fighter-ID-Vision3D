#!/usr/bin/env python3
"""
Review Report Generator
Orchestrates code quality and PR analysis, then writes a structured markdown report.
"""

import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

# Allow running from any directory by adding the scripts/ dir to the path
_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from code_quality_checker import CodeQualityChecker  # noqa: E402
from pr_analyzer import PrAnalyzer  # noqa: E402

POSITIVE_OBSERVATIONS = [
    "Modular vision engine layout under `fighterid_vision_engine/` with clear submodule boundaries (camera, detection, pipeline, config).",
    "GPU inference with automatic fallback chain: DirectML → CUDA → CPU, ensuring broad hardware compatibility.",
    "Thread-safe camera capture (`CameraStream`) with per-frame locking and graceful backend fallback.",
    "CI/CD pipeline (`.github/workflows/lint.yml`) actively scans for hardcoded credentials and validates syntax on every push.",
    "Configuration centralised in `settings.py` with URL-validation helpers, sourced from `.env` via `python-dotenv`.",
    "3-layer temporal strike detection (`temporal_strike.py`) provides a well-structured kinematic analysis pipeline.",
    "Hungarian algorithm tracker (`tracker.py`) maintains stable RED/BLUE fighter identity across occlusions.",
]


def _severity_order(finding: Dict) -> int:
    return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(finding.get("severity", "LOW"), 3)


def _findings_table(findings: List[Dict], include_file: bool = True) -> str:
    if not findings:
        return "_No findings._\n"
    lines = []
    if include_file:
        lines.append("| Severity | File | Line | Issue |")
        lines.append("|----------|------|------|-------|")
        for f in findings:
            loc = str(f.get("line", "")) if f.get("line") else "—"
            lines.append(
                f"| {f['severity']} | `{f.get('file', '')}` | {loc} | {f['message']} |"
            )
    else:
        lines.append("| Severity | Issue |")
        lines.append("|----------|-------|")
        for f in findings:
            lines.append(f"| {f['severity']} | {f['message']} |")
    return "\n".join(lines) + "\n"


def build_report(
    quality: Dict,
    pr: Dict,
    target_path: Path,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    q_summary = quality.get("summary", {})
    q_findings = quality.get("findings", [])
    p_findings = pr.get("findings", [])

    high_q = [f for f in q_findings if f["severity"] == "HIGH"]
    med_q = [f for f in q_findings if f["severity"] == "MEDIUM"]
    low_q = [f for f in q_findings if f["severity"] == "LOW"]

    total_high = q_summary.get("HIGH", 0) + sum(1 for f in p_findings if f["severity"] == "HIGH")
    total_med = q_summary.get("MEDIUM", 0) + sum(1 for f in p_findings if f["severity"] == "MEDIUM")
    total_low = q_summary.get("LOW", 0) + sum(1 for f in p_findings if f["severity"] == "LOW")

    lines = []

    # Header
    lines += [
        "# Code Review Report — Fighter-ID-Vision3D",
        f"",
        f"_Generated: {now}_  ",
        f"_Target: `{target_path}`_",
        "",
        "---",
        "",
    ]

    # Executive summary
    lines += [
        "## Executive Summary",
        "",
        f"| Category | HIGH | MEDIUM | LOW | Total |",
        f"|----------|------|--------|-----|-------|",
        f"| Code Quality | {q_summary.get('HIGH',0)} | {q_summary.get('MEDIUM',0)} | {q_summary.get('LOW',0)} | {q_summary.get('total',0)} |",
    ]
    if pr.get("status") == "success":
        p_sum = pr.get("summary", {})
        lines.append(
            f"| PR Changes | {p_sum.get('HIGH',0)} | {p_sum.get('MEDIUM',0)} | {p_sum.get('LOW',0)} | {p_sum.get('total',0)} |"
        )
    lines += [
        f"| **Combined** | **{total_high}** | **{total_med}** | **{total_low}** | **{total_high+total_med+total_low}** |",
        "",
    ]

    # Files scanned
    lines += [
        f"> **{quality.get('files_scanned', 0)}** Python files scanned.",
        "",
        "---",
        "",
    ]

    # High priority
    lines += [
        "## High Priority Issues",
        "",
        "These issues carry the highest risk and should be addressed before merging.",
        "",
    ]
    all_high = high_q + [f for f in p_findings if f["severity"] == "HIGH"]
    lines.append(_findings_table(all_high))

    # Medium priority
    lines += [
        "## Medium Priority Issues",
        "",
        "Address these in the current sprint or immediately after merging.",
        "",
    ]
    all_med = med_q + [f for f in p_findings if f["severity"] == "MEDIUM"]
    lines.append(_findings_table(all_med))

    # Low priority
    lines += [
        "## Low Priority Issues",
        "",
        "<details>",
        "<summary>Expand low-priority findings</summary>",
        "",
    ]
    all_low = low_q + [f for f in p_findings if f["severity"] == "LOW"]
    lines.append(_findings_table(all_low))
    lines += ["</details>", ""]

    # PR changes section
    if pr.get("status") == "success":
        lines += [
            "---",
            "",
            "## PR Changes",
            "",
            f"**Branch:** `{pr.get('branch', 'unknown')}`  ",
            f"**Base:** `{pr.get('base_commit', 'unknown')}`  ",
            f"**Changes:** {pr.get('changed_files', 0)} files, "
            f"+{pr.get('insertions', 0)} / -{pr.get('deletions', 0)} lines",
            "",
            "### File Risk Assessment",
            "",
            "| Risk | File |",
            "|------|------|",
        ]
        for fr in pr.get("file_risks", []):
            lines.append(f"| {fr['risk']} | `{fr['file']}` |")
        lines.append("")
    elif pr.get("status") == "error":
        lines += [
            "---",
            "",
            "## PR Changes",
            "",
            f"> Note: {pr.get('message', 'PR analysis unavailable.')}",
            "",
        ]

    # Positive observations
    lines += [
        "---",
        "",
        "## Positive Observations",
        "",
    ]
    for obs in POSITIVE_OBSERVATIONS:
        lines.append(f"- {obs}")
    lines.append("")

    # Reference links
    lines += [
        "---",
        "",
        "## Reference",
        "",
        "- [Code Review Checklist](.claude/skills/code-reviewer/references/code_review_checklist.md)",
        "- [Coding Standards](.claude/skills/code-reviewer/references/coding_standards.md)",
        "- [Common Antipatterns](.claude/skills/code-reviewer/references/common_antipatterns.md)",
        "",
    ]

    return "\n".join(lines)


class ReviewReportGenerator:
    """Orchestrates quality + PR analysis and writes a markdown review report."""

    def __init__(self, target_path: str, verbose: bool = False, output: str = ""):
        self.target_path = Path(target_path).resolve()
        self.verbose = verbose
        self.output_path = Path(output) if output else self.target_path / "review_report.md"
        self.results: Dict = {}

    def run(self) -> Dict:
        print(f"Running ReviewReportGenerator...")
        print(f"Target: {self.target_path}")
        try:
            self.validate_target()
            self.analyze()
            self.generate_report()
            print("Completed successfully!")
            return self.results
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    def validate_target(self):
        if not self.target_path.exists():
            raise ValueError(f"Target path does not exist: {self.target_path}")
        if self.verbose:
            print(f"  Target validated: {self.target_path}")

    def analyze(self):
        if self.verbose:
            print("  Running code quality checks...")
        quality_checker = CodeQualityChecker(str(self.target_path), verbose=self.verbose)
        quality_checker.validate_target()
        quality_checker.analyze()
        quality = quality_checker.results

        if self.verbose:
            print("  Running PR analysis...")
        pr_analyzer = PrAnalyzer(str(self.target_path), verbose=self.verbose)
        try:
            pr_analyzer.validate_target()
            pr_analyzer.analyze()
            pr = pr_analyzer.results
        except Exception:
            pr = {
                "status": "error",
                "message": "Repository is not a git repo or has no remote branches.",
                "findings": [],
            }

        self.results = {
            "status": "success",
            "target": str(self.target_path),
            "quality": quality,
            "pr": pr,
        }

    def generate_report(self):
        quality = self.results["quality"]
        pr = self.results["pr"]

        report_md = build_report(quality, pr, self.target_path)
        self.output_path.write_text(report_md, encoding="utf-8")

        q_sum = quality.get("summary", {})
        p_sum = pr.get("summary", {}) if pr.get("status") == "success" else {}

        print("\n" + "=" * 60)
        print("REVIEW REPORT SUMMARY")
        print("=" * 60)
        print(f"Report written to : {self.output_path}")
        print(f"Files scanned     : {quality.get('files_scanned', 0)}")
        print(f"HIGH issues       : {q_sum.get('HIGH', 0) + p_sum.get('HIGH', 0)}")
        print(f"MEDIUM issues     : {q_sum.get('MEDIUM', 0) + p_sum.get('MEDIUM', 0)}")
        print(f"LOW issues        : {q_sum.get('LOW', 0) + p_sum.get('LOW', 0)}")
        print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Review Report Generator for Fighter-ID-Vision3D"
    )
    parser.add_argument("target", help="Root directory of the project")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--json", action="store_true", help="Also output results as JSON")
    parser.add_argument(
        "--output", "-o",
        help="Path for the markdown report (default: <target>/review_report.md)",
    )
    args = parser.parse_args()

    generator = ReviewReportGenerator(
        args.target,
        verbose=args.verbose,
        output=args.output or "",
    )
    results = generator.run()

    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
