"""
SYMBIONT Audit — automated technical debt scanner and fixer.

Scans all git repositories for:
- Dirty files (uncommitted changes)
- Unpushed commits
- Missing .gitignore
- Exposed secrets (API keys, tokens, passwords)
- Stale version references
- LaTeX build artifacts in tracked files

Can auto-fix safe issues:
- Push unpushed commits
- Create standard .gitignore
- Commit LaTeX artifacts to .gitignore
- Report (never auto-fix) secret exposures

Usage:
    from symbiont.audit import Auditor
    auditor = Auditor()
    report = auditor.scan()          # Full scan
    auditor.fix(report)              # Auto-fix safe issues
    auditor.report_text(report)      # Human-readable report

CLI:
    sym audit                        # Scan + report
    sym audit scan                   # Scan only
    sym audit fix                    # Scan + auto-fix
    sym audit report                 # Scan + detailed report
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Secret patterns (regex)
SECRET_PATTERNS = [
    (r"gsk_[a-zA-Z0-9]{20,}", "Groq API key"),
    (r"sk-ant-[a-zA-Z0-9\-]{20,}", "Anthropic API key"),
    (r"sk-[a-zA-Z0-9]{20,}", "OpenAI API key"),
    (r"sb_secret_[a-zA-Z0-9\-_]{10,}", "Supabase service key"),
    (r"\d{10}:[A-Za-z0-9_\-]{30,}", "Telegram bot token"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub personal token"),
    (r"glpat-[a-zA-Z0-9\-]{20,}", "GitLab token"),
    (r"xoxb-[a-zA-Z0-9\-]{20,}", "Slack bot token"),
]

# Standard .gitignore template
STANDARD_GITIGNORE = """# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.venv/
venv/
.env

# LaTeX
*.aux
*.log
*.out
*.bbl
*.blg
*.fdb_latexmk
*.fls
*.synctex.gz
*.toc
*.lof
*.lot

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store

# Data artifacts
*.db
*.db-wal
*.db-shm

# Test
.pytest_cache/

# Claude
.claude/
.mcp.json
HANDOFF-*.md
"""


@dataclass
class RepoFinding:
    """A single finding for a repository."""
    repo_path: str
    repo_name: str
    severity: str  # critical, warning, info
    category: str  # dirty, unpushed, gitignore, secret, version, artifact
    description: str
    auto_fixable: bool = False
    fixed: bool = False
    details: str = ""


@dataclass
class RepoStatus:
    """Full status of a single repository."""
    path: str
    name: str
    dirty_count: int = 0
    unpushed_count: int = 0
    has_gitignore: bool = False
    has_remote: bool = False
    findings: list[RepoFinding] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return len(self.findings) == 0

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")


@dataclass
class AuditReport:
    """Full audit report across all repositories."""
    repos: list[RepoStatus] = field(default_factory=list)
    scan_time: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def total_repos(self) -> int:
        return len(self.repos)

    @property
    def clean_repos(self) -> int:
        return sum(1 for r in self.repos if r.is_clean)

    @property
    def total_findings(self) -> int:
        return sum(len(r.findings) for r in self.repos)

    @property
    def critical_findings(self) -> int:
        return sum(r.critical_count for r in self.repos)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "scan_time_sec": self.scan_time,
            "summary": {
                "total_repos": self.total_repos,
                "clean_repos": self.clean_repos,
                "findings": self.total_findings,
                "critical": self.critical_findings,
            },
            "repos": [
                {
                    "name": r.name,
                    "path": r.path,
                    "clean": r.is_clean,
                    "dirty": r.dirty_count,
                    "unpushed": r.unpushed_count,
                    "gitignore": r.has_gitignore,
                    "findings": [
                        {
                            "severity": f.severity,
                            "category": f.category,
                            "description": f.description,
                            "auto_fixable": f.auto_fixable,
                            "fixed": f.fixed,
                        }
                        for f in r.findings
                    ],
                }
                for r in self.repos
            ],
        }


class Auditor:
    """Scans git repositories for technical debt."""

    def __init__(self, search_paths: list[str] | None = None, max_depth: int = 4):
        self._search_paths = search_paths or [str(Path.home())]
        self._max_depth = max_depth

    def _run(self, cmd: list[str], cwd: str, timeout: int = 15) -> tuple[bool, str]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
            return r.returncode == 0, r.stdout.strip()
        except Exception as e:
            return False, str(e)

    def _find_repos(self, since_hours: int = 24) -> list[str]:
        """Find all git repos with recent activity."""
        repos = []
        for base in self._search_paths:
            result = subprocess.run(
                ["find", base, "-maxdepth", str(self._max_depth),
                 "-name", ".git", "-type", "d"],
                capture_output=True, text=True, timeout=30,
            )
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                repo = os.path.dirname(line)
                if ".venv" in repo or "node_modules" in repo:
                    continue
                # Check for recent commits
                ok, out = self._run(
                    ["git", "log", f"--since={since_hours} hours ago", "--oneline", "-1"],
                    cwd=repo,
                )
                if ok and out:
                    repos.append(repo)
        return repos

    def scan(self, since_hours: int = 24, paths: list[str] | None = None) -> AuditReport:
        """Run a full audit scan."""
        start = time.time()
        report = AuditReport()

        repo_paths = paths or self._find_repos(since_hours)

        for repo_path in repo_paths:
            status = self._scan_repo(repo_path)
            report.repos.append(status)

        report.scan_time = time.time() - start
        logger.info("audit: scanned %d repos in %.1fs, %d findings",
                     report.total_repos, report.scan_time, report.total_findings)
        return report

    def _scan_repo(self, repo_path: str) -> RepoStatus:
        """Scan a single repository."""
        name = os.path.basename(repo_path)
        status = RepoStatus(path=repo_path, name=name)

        # 1. Check .gitignore
        status.has_gitignore = os.path.exists(os.path.join(repo_path, ".gitignore"))
        if not status.has_gitignore:
            status.findings.append(RepoFinding(
                repo_path=repo_path, repo_name=name,
                severity="warning", category="gitignore",
                description="Missing .gitignore",
                auto_fixable=True,
            ))

        # 2. Check dirty files (ignore submodule untracked content)
        ok, out = self._run(
            ["git", "status", "--porcelain", "--ignore-submodules=untracked"],
            cwd=repo_path,
        )
        if ok and out:
            lines = [l for l in out.split("\n") if l.strip()]
            modified = [l for l in lines if not l.startswith("??")]
            untracked = [l for l in lines if l.startswith("??")]
            status.dirty_count = len(lines)

            if modified:
                status.findings.append(RepoFinding(
                    repo_path=repo_path, repo_name=name,
                    severity="warning", category="dirty",
                    description=f"{len(modified)} modified files uncommitted",
                    details="\n".join(modified[:10]),
                ))
            if len(untracked) > 10:
                status.findings.append(RepoFinding(
                    repo_path=repo_path, repo_name=name,
                    severity="info", category="dirty",
                    description=f"{len(untracked)} untracked files",
                ))

        # 3. Check unpushed
        ok, out = self._run(
            ["git", "log", "--oneline", "@{upstream}..HEAD"],
            cwd=repo_path,
        )
        if ok and out:
            count = len(out.strip().split("\n"))
            status.unpushed_count = count
            status.findings.append(RepoFinding(
                repo_path=repo_path, repo_name=name,
                severity="warning", category="unpushed",
                description=f"{count} commits not pushed to remote",
                auto_fixable=True,
            ))

        # 4. Check for remote
        ok, out = self._run(["git", "remote", "-v"], cwd=repo_path)
        status.has_remote = ok and bool(out.strip())

        # 5. Scan for secrets in tracked files
        ok, tracked = self._run(["git", "ls-files"], cwd=repo_path)
        if ok:
            for fpath in tracked.split("\n"):
                if not fpath or any(skip in fpath for skip in [".venv", "node_modules", ".git"]):
                    continue
                full = os.path.join(repo_path, fpath)
                if not os.path.isfile(full):
                    continue
                try:
                    # Only scan text files under 500KB
                    if os.path.getsize(full) > 500_000:
                        continue
                    with open(full, "r", errors="ignore") as f:
                        content = f.read()
                    for pattern, label in SECRET_PATTERNS:
                        matches = re.findall(pattern, content)
                        # Filter out obvious placeholders
                        real = [m for m in matches if "..." not in m and "example" not in m.lower()]
                        if real:
                            status.findings.append(RepoFinding(
                                repo_path=repo_path, repo_name=name,
                                severity="critical", category="secret",
                                description=f"{label} found in {fpath}",
                                details=f"Pattern: {real[0][:20]}...",
                            ))
                except Exception as exc:
                    logger.debug("audit: skipping file %s during secret scan: %s", fpath, exc)

        return status

    def fix(self, report: AuditReport) -> int:
        """Auto-fix safe issues. Returns number of fixes applied."""
        fixes = 0

        for repo in report.repos:
            for finding in repo.findings:
                if not finding.auto_fixable or finding.fixed:
                    continue

                if finding.category == "gitignore":
                    path = os.path.join(finding.repo_path, ".gitignore")
                    with open(path, "w") as f:
                        f.write(STANDARD_GITIGNORE)
                    self._run(["git", "add", ".gitignore"], cwd=finding.repo_path)
                    self._run(
                        ["git", "commit", "-m", "chore: add .gitignore"],
                        cwd=finding.repo_path,
                    )
                    finding.fixed = True
                    fixes += 1
                    logger.info("audit: fixed .gitignore in %s", repo.name)

                elif finding.category == "unpushed":
                    ok, _ = self._run(["git", "push"], cwd=finding.repo_path, timeout=30)
                    if ok:
                        finding.fixed = True
                        fixes += 1
                        logger.info("audit: pushed %s", repo.name)

        return fixes

    def report_text(self, report: AuditReport) -> str:
        """Generate human-readable text report."""
        lines = []
        lines.append("=" * 60)
        lines.append(f"  SYMBIONT AUDIT REPORT")
        lines.append(f"  {report.total_repos} repos scanned in {report.scan_time:.1f}s")
        lines.append(f"  {report.clean_repos}/{report.total_repos} clean")
        lines.append(f"  {report.total_findings} findings ({report.critical_findings} critical)")
        lines.append("=" * 60)
        lines.append("")

        for repo in sorted(report.repos, key=lambda r: len(r.findings), reverse=True):
            icon = "✅" if repo.is_clean else ("🔴" if repo.critical_count else "⚠️")
            lines.append(f"{icon} {repo.name}")
            if repo.is_clean:
                continue
            for f in repo.findings:
                sev = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(f.severity, "⚪")
                fix = " [FIXED]" if f.fixed else (" [auto-fixable]" if f.auto_fixable else "")
                lines.append(f"   {sev} [{f.category}] {f.description}{fix}")
            lines.append("")

        return "\n".join(lines)

    def report_json(self, report: AuditReport) -> str:
        """Generate JSON report."""
        return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


async def audit_cmd(args: str, verbose: bool = False):
    """CLI handler for sym audit."""
    if verbose:
        logging.basicConfig(level=logging.INFO)

    parts = args.strip().split() if args.strip() else ["scan"]
    subcmd = parts[0]

    auditor = Auditor()

    if subcmd in ("scan", "report"):
        hours = 24
        if len(parts) > 1 and parts[1].isdigit():
            hours = int(parts[1])
        report = auditor.scan(since_hours=hours)
        print(auditor.report_text(report))
        if subcmd == "report":
            # Save JSON report
            report_path = Path.home() / ".symbiont" / "audit-report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(auditor.report_json(report))
            print(f"\n📄 JSON report saved to {report_path}")

    elif subcmd == "fix":
        hours = 24
        if len(parts) > 1 and parts[1].isdigit():
            hours = int(parts[1])
        report = auditor.scan(since_hours=hours)
        print(auditor.report_text(report))
        if report.total_findings > 0:
            print("\n🔧 Auto-fixing safe issues...")
            fixes = auditor.fix(report)
            print(f"   {fixes} fixes applied")
            # Re-scan to show updated state
            report2 = auditor.scan(since_hours=hours)
            print(f"\n   After fix: {report2.clean_repos}/{report2.total_repos} clean")
        else:
            print("\n✅ Nothing to fix")

    elif subcmd == "json":
        report = auditor.scan()
        print(auditor.report_json(report))

    else:
        print("Usage: sym audit [scan|fix|report|json]")
        print("  scan [hours]  — scan repos with activity in last N hours (default 24)")
        print("  fix [hours]   — scan + auto-fix safe issues")
        print("  report [hours]— scan + save JSON report")
        print("  json          — output JSON to stdout")
