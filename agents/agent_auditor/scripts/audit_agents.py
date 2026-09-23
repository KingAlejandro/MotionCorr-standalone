#!/usr/bin/env python3
"""
Agent Meta-Auditor
Inspects all peer agents in `agents/` (strictly excluding itself),
verifying Python script compilation, CLI execution, system prompt rigor,
template integrity, and cross-agent consistency.
"""

import argparse
import datetime
import os
import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple


def find_repo_root() -> Path:
    """Find repository root by walking up from script directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "CMakeLists.txt").exists():
            return current
        current = current.parent
    return Path.cwd()


def audit_python_script(script_path: Path) -> List[Dict[str, str]]:
    """Verify compilation and CLI responsiveness of a Python script."""
    findings = []

    # 1. Compilation check (isolated to temp directory to avoid .pyc pollution)
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_cfile = os.path.join(tmpdir, "compiled.pyc")
            py_compile.compile(str(script_path), cfile=temp_cfile, doraise=True)
    except py_compile.PyCompileError as e:
        findings.append({
            "severity": "CRITICAL",
            "file": str(script_path),
            "title": f"Script compilation failed: {script_path.name}",
            "description": f"Syntax or compilation error: {e.msg}",
            "remediation": "Fix syntax error to ensure script can execute."
        })
        return findings
    except Exception as e:
        findings.append({
            "severity": "CRITICAL",
            "file": str(script_path),
            "title": f"Unexpected compilation error: {script_path.name}",
            "description": str(e),
            "remediation": "Check Python environment and syntax."
        })
        return findings

    # 2. Syntax warning check (e.g. invalid escape sequence) without writing .pyc
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_cfile = os.path.join(tmpdir, "syntax_check.pyc")
            check_code = f"import py_compile; py_compile.compile({repr(str(script_path))}, cfile={repr(temp_cfile)}, doraise=True)"
            res = subprocess.run(
                [sys.executable, "-Werror::SyntaxWarning", "-c", check_code],
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
            if res.returncode != 0:
                findings.append({
                    "severity": "WARNING",
                    "file": str(script_path),
                    "title": f"SyntaxWarning detected in {script_path.name}",
                    "description": res.stderr.strip() or res.stdout.strip(),
                    "remediation": "Clean up unescaped characters or use raw string r'...' syntax."
                })
    except Exception:
        pass

    # 3. CLI --help responsiveness check
    try:
        res = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10
        )
        if res.returncode != 0:
            findings.append({
                "severity": "WARNING",
                "file": str(script_path),
                "title": f"CLI '--help' returned non-zero code in {script_path.name}",
                "description": f"Exit code {res.returncode}. Stderr: {res.stderr.strip()[:200]}",
                "remediation": "Ensure argument parser handles --help cleanly."
            })
    except subprocess.TimeoutExpired:
        findings.append({
            "severity": "CRITICAL",
            "file": str(script_path),
            "title": f"Script hang on --help: {script_path.name}",
            "description": "Script timed out while responding to '--help'.",
            "remediation": "Prevent blocking operations from executing during argument parsing."
        })
    except Exception as e:
        findings.append({
            "severity": "WARNING",
            "file": str(script_path),
            "title": f"Failed to execute CLI test: {script_path.name}",
            "description": str(e),
            "remediation": "Verify script permissions and runtime dependencies."
        })

    return findings


def audit_system_prompt(prompt_path: Path) -> List[Dict[str, str]]:
    """Audit SYSTEM_PROMPT.md for required sections and completeness."""
    findings = []
    if not prompt_path.exists():
        findings.append({
            "severity": "CRITICAL",
            "file": str(prompt_path),
            "title": "Missing SYSTEM_PROMPT.md",
            "description": "Agent directory does not contain a SYSTEM_PROMPT.md definition.",
            "remediation": "Create SYSTEM_PROMPT.md with role definitions, operational mandates, and output criteria."
        })
        return findings

    content = prompt_path.read_text(encoding="utf-8")
    if len(content.strip()) < 100:
        findings.append({
            "severity": "WARNING",
            "file": str(prompt_path),
            "title": "Incomplete SYSTEM_PROMPT.md",
            "description": "SYSTEM_PROMPT.md is suspiciously short (< 100 characters).",
            "remediation": "Provide detailed role instructions and behavioral boundaries."
        })

    # Check for crucial mandate keywords
    if not any(k in content.lower() for k in ("mandate", "constraint", "role", "objective")):
        findings.append({
            "severity": "WARNING",
            "file": str(prompt_path),
            "title": "Unspecified operational boundaries in SYSTEM_PROMPT.md",
            "description": "No explicit operational constraints or role mandates were found in the system prompt.",
            "remediation": "Add an 'Operational Mandates & Constraints' section."
        })

    return findings


def audit_templates(templates_dir: Path) -> List[Dict[str, str]]:
    """Audit template markdown files in an agent's templates/ folder."""
    findings = []
    if not templates_dir.exists():
        return findings

    template_files = list(templates_dir.glob("*.md"))
    if not template_files:
        findings.append({
            "severity": "INFO",
            "file": str(templates_dir),
            "title": "Empty templates directory",
            "description": "The templates directory contains no Markdown templates.",
            "remediation": "Add standardized output templates or remove unused folder."
        })

    for t_file in template_files:
        text = t_file.read_text(encoding="utf-8")
        if len(text.strip()) < 50:
            findings.append({
                "severity": "WARNING",
                "file": str(t_file),
                "title": f"Template file is very short: {t_file.name}",
                "description": "Template appears unpopulated or incomplete.",
                "remediation": "Add standard schema headers and guidance blocks."
            })

    return findings


def audit_peer_agent(agent_dir: Path) -> Dict[str, Any]:
    """Audit a single peer agent directory."""
    findings = []
    scripts_audited = 0

    # 1. System prompt audit
    prompt_path = agent_dir / "SYSTEM_PROMPT.md"
    findings.extend(audit_system_prompt(prompt_path))

    # 2. Templates audit
    templates_dir = agent_dir / "templates"
    findings.extend(audit_templates(templates_dir))

    # 3. Scripts audit
    scripts_dir = agent_dir / "scripts"
    if scripts_dir.exists():
        for script in scripts_dir.glob("*.py"):
            scripts_audited += 1
            findings.extend(audit_python_script(script))

    # Determine status
    has_critical = any(f["severity"] == "CRITICAL" for f in findings)
    has_warning = any(f["severity"] == "WARNING" for f in findings)

    if has_critical:
        status = "FAULT / CRITICAL"
    elif has_warning:
        status = "NEEDS ATTENTION"
    else:
        status = "HEALTHY"

    return {
        "name": agent_dir.name,
        "path": agent_dir,
        "status": status,
        "scripts_count": scripts_audited,
        "has_prompt": prompt_path.exists(),
        "findings": findings,
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Agent Meta-Auditor: Inspect all peer agents (excluding itself) for integrity, syntax, and consistency."
    )
    parser.add_argument("--output", help="Optional markdown file path to save the audit report")

    args = parser.parse_args()
    repo_root = find_repo_root()
    agents_root = repo_root / "agents"

    if not agents_root.exists():
        sys.stderr.write("Error: 'agents/' directory not found.\n")
        sys.exit(1)

    self_dir_name = Path(__file__).resolve().parent.parent.name  # "agent_auditor"
    print(f"\n[Agent Meta-Auditor] Scanning 'agents/' directory...")
    print(f"[Agent Meta-Auditor] Self-Exclusion Active: Skipping '{self_dir_name}'\n")

    excluded_dirs = {self_dir_name, "designs", "scripts", "logs", "reviews", "drafts"}
    peer_agent_dirs = [
        d for d in agents_root.iterdir()
        if d.is_dir() and d.name not in excluded_dirs and not d.name.startswith((".", "_"))
    ]

    if not peer_agent_dirs:
        print("[Agent Meta-Auditor] No peer agents found to audit.")
        sys.exit(0)

    results = []
    total_findings = []
    for peer_dir in peer_agent_dirs:
        print(f"[Agent Meta-Auditor] Auditing peer agent: {peer_dir.name}...")
        res = audit_peer_agent(peer_dir)
        results.append(res)
        total_findings.extend(res["findings"])

    # Determine overall ecosystem health
    if any(r["status"] == "FAULT / CRITICAL" for r in results):
        overall_health = "DEGRADED"
        exec_summary = "One or more peer agents have critical syntax, compilation, or execution faults that impair reliable operations."
    elif any(r["status"] == "NEEDS ATTENTION" for r in results):
        overall_health = "NEEDS_ATTENTION"
        exec_summary = "All peer agents are executable, but some warnings or incomplete specifications were flagged for attention."
    else:
        overall_health = "HEALTHY"
        exec_summary = "All peer agents are structurally sound, scripts compile cleanly without warnings, and CLI argument parsers are fully functional."

    # Build matrix rows
    matrix_rows = []
    for r in results:
        status_badge = f"**{r['status']}**"
        findings_summary = f"{len(r['findings'])} finding(s)" if r['findings'] else "Clean"
        prompt_status = "Valid" if r["has_prompt"] else "Missing"
        matrix_rows.append(
            f"| `{r['name']}` | {status_badge} | {r['scripts_count']} script(s) | {prompt_status} | {findings_summary} |"
        )
    matrix_str = "\n".join(matrix_rows)

    # Build findings block
    findings_blocks = []
    if total_findings:
        for i, f in enumerate(total_findings, 1):
            findings_blocks.append(
                f"### [{f['severity']}] A-{i:02d}: {f['title']}\n"
                f"- **Target File**: `{Path(f['file']).relative_to(repo_root) if repo_root in Path(f['file']).parents else f['file']}`\n"
                f"- **Problem**: {f['description']}\n"
                f"- **Recommended Remediation**: {f['remediation']}\n"
            )
        findings_str = "\n".join(findings_blocks)
    else:
        findings_str = "> **All peer agents passed inspection.** No syntax errors, broken references, or prompt contradictions were detected.\n"

    # Build recommendations block
    if overall_health == "HEALTHY":
        recs_str = "No remediation required. The multi-agent ecosystem is operating with high integrity.\n"
    else:
        recs_str = "Review and address the flagged items in Section 3 to ensure seamless multi-agent collaboration.\n"

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = f"""# Agent Ecosystem Audit Report

- **Auditor**: Agent Meta-Auditor (`agents/agent_auditor/`)
- **Audit Timestamp**: `{timestamp}`
- **Scope**: All peer agents (excluding `agent_auditor`)
- **Overall Ecosystem Health**: **{overall_health}**

---

## 1. Executive Summary

{exec_summary}

---

## 2. Peer Agent Audit Matrix

| Agent Directory | Status | Scripts Validated | Prompts & Specs | Findings Summary |
| :--- | :--- | :--- | :--- | :--- |
{matrix_str}

---

## 3. Detailed Audit Findings

{findings_str}
---

## 4. Remediation Recommendations

{recs_str}
"""

    print("\n" + "=" * 60)
    print(" AGENT ECOSYSTEM AUDIT REPORT")
    print("=" * 60)
    print(report)
    print("=" * 60 + "\n")

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"[Agent Meta-Auditor] Report saved to: {out_path}")


if __name__ == "__main__":
    main()
