#!/usr/bin/env python3
"""
Code Quality Checker
AST-based static analysis for the Fighter-ID-Vision3D Python codebase.
"""

import ast
import os
import re
import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

# Files where print() is an acceptable logging mechanism
PRINT_OK_FILES = {"main.py", "app.py", "check_system.py", "three_camera_ui.py",
                  "fight_manager.py", "vision_sync.py"}

# Directories to skip entirely
SKIP_DIRS = {".git", ".claude", "__pycache__", ".venv", "venv", "env", "archive",
             "node_modules", ".github"}

LOC_THRESHOLD = 500  # Lines-of-code warning threshold


def iter_python_files(root: Path) -> List[Path]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname.endswith(".py"):
                files.append(Path(dirpath) / fname)
    return sorted(files)


def count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
    except OSError:
        return 0


def parse_file(path: Path) -> Optional[ast.Module]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(source, filename=str(path))
    except SyntaxError:
        return None


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def check_large_files(files: List[Path], root: Path) -> List[Dict]:
    findings = []
    for f in files:
        loc = count_lines(f)
        if loc > LOC_THRESHOLD:
            findings.append({
                "severity": "MEDIUM",
                "file": rel(f, root),
                "line": loc,
                "message": f"File has {loc} lines (>{LOC_THRESHOLD}). Consider splitting into smaller modules.",
            })
    return findings


def check_missing_type_annotations(tree: ast.Module, filepath: str) -> List[Dict]:
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_") or node.name.startswith("test_"):
            continue
        missing_args = [
            arg.arg for arg in node.args.args
            if arg.arg not in ("self", "cls") and arg.annotation is None
        ]
        has_return = node.returns is not None
        if missing_args or not has_return:
            parts = []
            if missing_args:
                parts.append(f"args missing annotations: {', '.join(missing_args)}")
            if not has_return:
                parts.append("missing return type")
            findings.append({
                "severity": "LOW",
                "file": filepath,
                "line": node.lineno,
                "message": f"Function `{node.name}`: {'; '.join(parts)}.",
            })
    return findings


def check_bare_except(tree: ast.Module, filepath: str) -> List[Dict]:
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append({
                "severity": "MEDIUM",
                "file": filepath,
                "line": node.lineno,
                "message": "Bare `except:` catches all exceptions including KeyboardInterrupt/SystemExit. Use `except Exception:` or be specific.",
            })
    return findings


def check_missing_docstrings(tree: ast.Module, filepath: str) -> List[Dict]:
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            if not ast.get_docstring(node):
                kind = "Class" if isinstance(node, ast.ClassDef) else "Function"
                findings.append({
                    "severity": "LOW",
                    "file": filepath,
                    "line": node.lineno,
                    "message": f"{kind} `{node.name}` is missing a docstring.",
                })
    return findings


def check_print_in_library(tree: ast.Module, filepath: str) -> List[Dict]:
    fname = Path(filepath).name
    if fname in PRINT_OK_FILES:
        return []
    if "/tools/" in filepath.replace("\\", "/") or "/scripts/" in filepath.replace("\\", "/"):
        return []
    findings = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and
                isinstance(node.func, ast.Name) and
                node.func.id == "print"):
            findings.append({
                "severity": "LOW",
                "file": filepath,
                "line": node.lineno,
                "message": "Use `logging` instead of `print()` in library/engine modules.",
            })
    return findings


def check_todos(path: Path, root: Path) -> List[Dict]:
    findings = []
    pattern = re.compile(r"#.*(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)
    try:
        for lineno, line in enumerate(
            path.open(encoding="utf-8", errors="replace"), start=1
        ):
            m = pattern.search(line)
            if m:
                tag = m.group(1).upper()
                findings.append({
                    "severity": "LOW",
                    "file": rel(path, root),
                    "line": lineno,
                    "message": f"{tag} comment: {line.strip()[:120]}",
                })
    except OSError:
        pass
    return findings


def check_hardcoded_credentials(path: Path, root: Path) -> List[Dict]:
    if path.name.startswith(".env") or path.suffix == ".sql":
        return []
    patterns = [
        (re.compile(r"sb_publishable_[A-Za-z0-9_]+"), "Supabase publishable key"),
        (re.compile(r"eyJ[A-Za-z0-9_\-]{20,}"), "Possible JWT token"),
        (re.compile(r"https://[a-z0-9]+\.supabase\.co"), "Hardcoded Supabase URL"),
    ]
    findings = []
    try:
        for lineno, line in enumerate(
            path.open(encoding="utf-8", errors="replace"), start=1
        ):
            if line.strip().startswith("#"):
                continue
            for pat, label in patterns:
                if pat.search(line):
                    findings.append({
                        "severity": "HIGH",
                        "file": rel(path, root),
                        "line": lineno,
                        "message": f"{label} appears hardcoded. Use environment variables instead.",
                    })
                    break
    except OSError:
        pass
    return findings


def check_duplicate_class_names(
    all_classes: Dict[str, List[Tuple[str, int]]]
) -> List[Dict]:
    findings = []
    for name, locations in all_classes.items():
        if len(locations) > 1:
            loc_str = ", ".join(f"{f}:{l}" for f, l in locations)
            findings.append({
                "severity": "HIGH",
                "file": locations[0][0],
                "line": locations[0][1],
                "message": f"Class `{name}` defined in multiple files: {loc_str}. Consolidate to one location.",
            })
    return findings


def check_missing_tests(root: Path) -> List[Dict]:
    findings = []
    engine_dir = root / "fighterid_vision_engine"
    tests_dir = root / "tests"
    if not engine_dir.exists():
        return findings
    for subdir in sorted(engine_dir.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("_"):
            continue
        for pyfile in sorted(subdir.glob("*.py")):
            if pyfile.name.startswith("_"):
                continue
            test_name = f"test_{pyfile.stem}.py"
            has_test = (
                (tests_dir / test_name).exists() or
                (tests_dir / subdir.name / test_name).exists() or
                (root / test_name).exists()
            )
            if not has_test:
                findings.append({
                    "severity": "HIGH",
                    "file": str(pyfile.relative_to(root)),
                    "line": 0,
                    "message": f"No test file found for `{pyfile.stem}`. "
                               f"Expected `tests/{test_name}`. Critical algorithm code needs unit tests.",
                })
    return findings


class CodeQualityChecker:
    """AST-based code quality analyser for the Fighter-ID-Vision3D project."""

    def __init__(self, target_path: str, verbose: bool = False):
        self.target_path = Path(target_path).resolve()
        self.verbose = verbose
        self.results: Dict = {}

    def run(self) -> Dict:
        print(f"Running CodeQualityChecker...")
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
            print("  Scanning Python files...")

        files = iter_python_files(self.target_path)
        if self.verbose:
            print(f"  Found {len(files)} Python files")

        findings: List[Dict] = []
        findings.extend(check_large_files(files, self.target_path))
        findings.extend(check_missing_tests(self.target_path))

        all_classes: Dict[str, List[Tuple[str, int]]] = defaultdict(list)

        for fpath in files:
            frel = rel(fpath, self.target_path)
            findings.extend(check_hardcoded_credentials(fpath, self.target_path))
            findings.extend(check_todos(fpath, self.target_path))

            tree = parse_file(fpath)
            if tree is None:
                findings.append({
                    "severity": "MEDIUM",
                    "file": frel,
                    "line": 0,
                    "message": "File has a syntax error and could not be parsed.",
                })
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    all_classes[node.name].append((frel, node.lineno))

            findings.extend(check_bare_except(tree, frel))
            findings.extend(check_missing_type_annotations(tree, frel))
            findings.extend(check_missing_docstrings(tree, frel))
            findings.extend(check_print_in_library(tree, frel))

        findings.extend(check_duplicate_class_names(all_classes))

        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        findings.sort(
            key=lambda f: (severity_order.get(f["severity"], 3), f["file"], f["line"])
        )

        self.results = {
            "status": "success",
            "target": str(self.target_path),
            "files_scanned": len(files),
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
        print("CODE QUALITY REPORT")
        print("=" * 60)
        print(f"Target  : {self.results.get('target')}")
        print(f"Scanned : {self.results.get('files_scanned')} Python files")
        print(f"HIGH    : {s.get('HIGH', 0)} issues")
        print(f"MEDIUM  : {s.get('MEDIUM', 0)} issues")
        print(f"LOW     : {s.get('LOW', 0)} issues")
        print(f"TOTAL   : {s.get('total', 0)} issues")
        print("=" * 60)

        findings = self.results.get("findings", [])
        for severity in ("HIGH", "MEDIUM"):
            group = [f for f in findings if f["severity"] == severity]
            if group:
                print(f"\n[{severity}]")
                for f in group:
                    loc = f":{f['line']}" if f["line"] else ""
                    print(f"  {f['file']}{loc}  --  {f['message']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Code Quality Checker for Fighter-ID-Vision3D"
    )
    parser.add_argument("target", help="Root directory of the project to analyse")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--output", "-o", help="Write JSON results to this file")
    args = parser.parse_args()

    checker = CodeQualityChecker(args.target, verbose=args.verbose)
    results = checker.run()

    if args.json or args.output:
        output = json.dumps(results, indent=2)
        if args.output:
            Path(args.output).write_text(output)
            print(f"Results written to {args.output}")
        else:
            print(output)


if __name__ == "__main__":
    main()
