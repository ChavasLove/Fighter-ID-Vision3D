#!/usr/bin/env python3
"""
PR Analyzer
Git-based pull request analysis for the Fighter-ID-Vision3D project.
"""

import os
import re
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Risk classification for changed files
HIGH_RISK_PATTERNS = [
    re.compile(p) for p in [
        r"supabase", r"settings\.py", r"config/", r"\.yml$", r"\.yaml$",
        r"\.env", r"schema\.sql", r"migration",
    ]
]
MEDIUM_RISK_PATTERNS = [
    re.compile(p) for p in [
        r"engine\.py", r"tracker\.py", r"temporal_strike\.py",
        r"fight_manager\.py", r"pose\.py", r"capture\.py",
    ]
]

CREDENTIAL_PATTERNS = [
    (re.compile(r"sb_publishable_[A-Za-z0-9_]+"), "Supabase publishable key"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{20,}"), "Possible JWT token"),
    (re.compile(r"https://[a-z0-9]+\.supabase\.co"), "Hardcoded Supabase URL"),
]


def run_git(args: List[str], cwd: Path) -> Tuple[int, str, str]:
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def find_base_commit(repo_root: Path) -> Optional[str]:
    """Find the commit where this branch diverged from main or master."""
    for branch in ("origin/main", "origin/master", "main", "master"):
        code, out, _ = run_git(["merge-base", branch, "HEAD"], repo_root)
        if code == 0 and out.strip():
            return out.strip()
    # Fallback: diff against the initial commit
    code, out, _ = run_git(["rev-list", "--max-parents=0", "HEAD"], repo_root)
    if code == 0 and out.strip():
        return out.strip()
    return None


def classify_risk(filepath: str) -> str:
    fp = filepath.replace("\\", "/")
    for pat in HIGH_RISK_PATTERNS:
        if pat.search(fp):
            return "HIGH"
    for pat in MEDIUM_RISK_PATTERNS:
        if pat.search(fp):
            return "MEDIUM"
    return "LOW"


def has_test_change(changed_files: List[str]) -> bool:
    return any("test" in f.lower() for f in changed_files)


def files_needing_tests(changed_files: List[str], test_files: List[str]) -> List[str]:
    """Return changed source files that have no corresponding changed test file."""
    untested = []
    for f in changed_files:
        stem = Path(f).stem
        if stem.startswith("test_"):
            continue
        if f.startswith("tests/") or "/tests/" in f:
            continue
        expected_test = f"test_{stem}.py"
        if not any(expected_test in tf for tf in test_files):
            untested.append(f)
    return untested


def scan_diff_for_credentials(diff_text: str) -> List[Dict]:
    findings = []
    for lineno, line in enumerate(diff_text.splitlines(), start=1):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for pat, label in CREDENTIAL_PATTERNS:
            if pat.search(line):
                findings.append({
                    "severity": "HIGH",
                    "line": lineno,
                    "message": f"{label} found in diff at line {lineno}: {line[:120]}",
                })
                break
    return findings


def scan_diff_for_new_todos(diff_text: str) -> List[Dict]:
    findings = []
    todo_pat = re.compile(r"\+(.*?)(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)
    for lineno, line in enumerate(diff_text.splitlines(), start=1):
        if line.startswith("+++"):
            continue
        m = todo_pat.search(line)
        if m:
            tag = m.group(2).upper()
            findings.append({
                "severity": "LOW",
                "line": lineno,
                "message": f"New {tag} added in diff: {line.strip()[:120]}",
            })
    return findings


def parse_diff_stat(diff_stat: str) -> Tuple[int, int]:
    """Return (insertions, deletions) from git diff --stat output."""
    insertions = 0
    deletions = 0
    for line in diff_stat.splitlines():
        m = re.search(r"(\d+) insertion", line)
        if m:
            insertions = int(m.group(1))
        m = re.search(r"(\d+) deletion", line)
        if m:
            deletions = int(m.group(1))
    return insertions, deletions


class PrAnalyzer:
    """Git-based PR/branch analyser for the Fighter-ID-Vision3D project."""

    def __init__(self, target_path: str, verbose: bool = False):
        self.target_path = Path(target_path).resolve()
        self.verbose = verbose
        self.results: Dict = {}

    def run(self) -> Dict:
        print(f"Running PrAnalyzer...")
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
        git_dir = self.target_path / ".git"
        if not git_dir.exists():
            raise ValueError(f"Not a git repository: {self.target_path}")
        if self.verbose:
            print(f"  Target validated: {self.target_path}")

    def analyze(self):
        if self.verbose:
            print("  Resolving base commit...")

        base = find_base_commit(self.target_path)
        if not base:
            self.results = {
                "status": "error",
                "target": str(self.target_path),
                "message": "Could not determine base commit. Is this a git repository with a remote?",
                "findings": [],
            }
            return

        if self.verbose:
            print(f"  Base commit: {base[:12]}")

        # Changed files
        _, changed_raw, _ = run_git(["diff", "--name-only", base], self.target_path)
        changed_files = [f.strip() for f in changed_raw.splitlines() if f.strip()]

        if self.verbose:
            print(f"  Changed files: {len(changed_files)}")

        # Diff text
        _, diff_text, _ = run_git(["diff", base], self.target_path)

        # Diff stat
        _, diff_stat, _ = run_git(["diff", "--stat", base], self.target_path)
        insertions, deletions = parse_diff_stat(diff_stat)

        # Current branch
        _, branch, _ = run_git(["branch", "--show-current"], self.target_path)
        branch = branch.strip()

        # Per-file risk
        test_files = [f for f in changed_files if "test" in f.lower()]
        source_files = [f for f in changed_files if "test" not in f.lower()]

        file_risks = [
            {"file": f, "risk": classify_risk(f)}
            for f in changed_files
        ]

        untested_files = files_needing_tests(source_files, test_files)

        findings: List[Dict] = []
        findings.extend(scan_diff_for_credentials(diff_text))
        findings.extend(scan_diff_for_new_todos(diff_text))

        for uf in untested_files:
            findings.append({
                "severity": "MEDIUM",
                "line": 0,
                "message": f"`{uf}` was modified but no corresponding test file was changed.",
            })

        high_risk = [fr for fr in file_risks if fr["risk"] == "HIGH"]
        if high_risk:
            for hr in high_risk:
                findings.append({
                    "severity": "HIGH",
                    "line": 0,
                    "message": f"High-risk file changed: `{hr['file']}`. Review carefully for security/stability impact.",
                })

        self.results = {
            "status": "success",
            "target": str(self.target_path),
            "branch": branch,
            "base_commit": base[:12],
            "changed_files": len(changed_files),
            "insertions": insertions,
            "deletions": deletions,
            "file_risks": file_risks,
            "findings": findings,
            "summary": {
                "HIGH": sum(1 for f in findings if f["severity"] == "HIGH"),
                "MEDIUM": sum(1 for f in findings if f["severity"] == "MEDIUM"),
                "LOW": sum(1 for f in findings if f["severity"] == "LOW"),
                "total": len(findings),
            },
        }

        if self.verbose:
            print(f"  Analysis complete: {len(findings)} findings")

    def generate_report(self):
        s = self.results.get("summary", {})
        print("\n" + "=" * 60)
        print("PR ANALYSIS REPORT")
        print("=" * 60)
        print(f"Branch        : {self.results.get('branch', 'unknown')}")
        print(f"Base commit   : {self.results.get('base_commit', 'unknown')}")
        print(f"Changed files : {self.results.get('changed_files', 0)}")
        print(f"Insertions    : +{self.results.get('insertions', 0)}")
        print(f"Deletions     : -{self.results.get('deletions', 0)}")
        print(f"HIGH findings : {s.get('HIGH', 0)}")
        print(f"MEDIUM findings: {s.get('MEDIUM', 0)}")
        print(f"LOW findings  : {s.get('LOW', 0)}")
        print("=" * 60)

        file_risks = self.results.get("file_risks", [])
        if file_risks:
            print("\nChanged Files:")
            for fr in file_risks:
                print(f"  [{fr['risk']:<6}] {fr['file']}")

        findings = self.results.get("findings", [])
        for severity in ("HIGH", "MEDIUM"):
            group = [f for f in findings if f["severity"] == severity]
            if group:
                print(f"\n[{severity}]")
                for f in group:
                    print(f"  {f['message']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="PR Analyzer for Fighter-ID-Vision3D"
    )
    parser.add_argument("target", help="Root directory of the git repository")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--output", "-o", help="Write JSON results to this file")
    args = parser.parse_args()

    analyzer = PrAnalyzer(args.target, verbose=args.verbose)
    results = analyzer.run()

    if args.json or args.output:
        output = json.dumps(results, indent=2)
        if args.output:
            Path(args.output).write_text(output)
            print(f"Results written to {args.output}")
        else:
            print(output)


if __name__ == "__main__":
    main()
