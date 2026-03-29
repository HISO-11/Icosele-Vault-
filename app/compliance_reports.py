"""Task 4 — Compliance report generation (GDPR, SOC2, ISO27001, Security)."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from app.audit_log import load_entries
from config.vm_config import VMConfig


def _header(title: str, date_range: str = "") -> str:
    ts = datetime.now(timezone.utc).isoformat()[:19]
    lines = [
        f"{'=' * 60}",
        f"  {title}",
        f"  Generated: {ts}",
    ]
    if date_range:
        lines.append(f"  Date Range: {date_range}")
    lines.append(f"{'=' * 60}")
    return "\n".join(lines)


def _filter_entries(entries: list[dict], start: str = "", end: str = "") -> list[dict]:
    if not start and not end:
        return entries
    return [e for e in entries
            if (not start or e.get("timestamp", "") >= start) and
               (not end or e.get("timestamp", "") <= end)]


def generate_gdpr_report(configs: list[VMConfig], start: str = "", end: str = "") -> str:
    entries = _filter_entries(load_entries(), start, end)
    dr = f"{start or 'all'} to {end or 'now'}"
    lines = [_header("GDPR COMPLIANCE REPORT", dr), ""]
    lines.append("VM INVENTORY AND DATA PROTECTION STATUS")
    lines.append("-" * 50)
    for c in configs:
        enc = "YES" if c.encrypted else "NO"
        iso = "YES" if c.net_mode == "hostonly" else "NO"
        lines.append(f"  {c.name}: encrypted={enc}, network_isolated={iso}, disk={c.disk_path or 'none'}")
    lines.append("")
    lines.append("COMPLIANCE CHECKLIST")
    lines.append("-" * 50)
    any_enc = any(c.encrypted for c in configs)
    any_iso = any(c.net_mode == "hostonly" for c in configs)
    has_log = len(entries) > 0
    has_snaps = any(e["action"].startswith("snapshot") for e in entries)
    lines.append(f"  Encrypted at rest:    {'PASS' if any_enc else 'FAIL'}")
    lines.append(f"  Network isolated:     {'PASS' if any_iso else 'REVIEW'}")
    lines.append(f"  Access logged:        {'PASS' if has_log else 'FAIL'}")
    lines.append(f"  Regular snapshots:    {'PASS' if has_snaps else 'FAIL'}")
    lines.append(f"\nAudit log entries in range: {len(entries)}")
    return "\n".join(lines)


def generate_soc2_report(configs: list[VMConfig], start: str = "", end: str = "") -> str:
    entries = _filter_entries(load_entries(), start, end)
    dr = f"{start or 'all'} to {end or 'now'}"
    lines = [_header("SOC 2 COMPLIANCE REPORT", dr), ""]
    # Availability
    starts = [e for e in entries if e["action"] == "vm_started"]
    stops = [e for e in entries if e["action"] == "vm_stopped"]
    lines.append(f"AVAILABILITY: {len(starts)} starts, {len(stops)} stops in period")
    # Change management
    changes = [e for e in entries if "changed" in e["action"] or "created" in e["action"]]
    lines.append(f"CHANGE MANAGEMENT: {len(changes)} config changes logged")
    # Incidents
    crashes = [e for e in entries if "crash" in e["action"]]
    quarantines = [e for e in entries if "quarantine" in e["action"]]
    lines.append(f"INCIDENTS: {len(crashes)} crashes, {len(quarantines)} quarantine events")
    lines.append(f"\nTotal audit entries: {len(entries)}")
    return "\n".join(lines)


def generate_iso27001_report(configs: list[VMConfig], start: str = "", end: str = "") -> str:
    entries = _filter_entries(load_entries(), start, end)
    dr = f"{start or 'all'} to {end or 'now'}"
    lines = [_header("ISO 27001 COMPLIANCE REPORT", dr), ""]
    lines.append("ASSET INVENTORY")
    lines.append("-" * 50)
    for c in configs:
        lines.append(f"  {c.name}: RAM={c.ram_mb}MB, CPU={c.cpu_cores}, disk={c.disk_path or 'none'}")
    lines.append(f"\nACCESS CONTROL: {len(entries)} audit entries")
    incidents = [e for e in entries if any(k in e["action"] for k in ("crash", "anomaly", "quarantine"))]
    lines.append(f"INCIDENTS: {len(incidents)} security events")
    snaps = [e for e in entries if "snapshot" in e["action"]]
    lines.append(f"BACKUP EVIDENCE: {len(snaps)} snapshot operations")
    return "\n".join(lines)


def generate_security_report(configs: list[VMConfig]) -> str:
    from app.ui.cve_checker import get_qemu_version, check_cves
    lines = [_header("GENERAL SECURITY REPORT"), ""]
    ver = get_qemu_version()
    ver_str = f"{ver[0]}.{ver[1]}.{ver[2]}" if ver else "unknown"
    cves = check_cves(ver) if ver else []
    lines.append(f"QEMU VERSION: {ver_str}")
    if cves:
        lines.append(f"KNOWN CVEs: {', '.join(c['cve'] for c in cves)}")
    else:
        lines.append("KNOWN CVEs: None")
    lines.append("")
    lines.append("PER-VM SECURITY STATUS")
    lines.append("-" * 50)
    for c in configs:
        enc = "encrypted" if c.encrypted else "unencrypted"
        fw = f"{len(c.firewall_rules)} rules" if c.firewall_rules else "no rules"
        lines.append(f"  {c.name}: {enc}, firewall: {fw}")
    return "\n".join(lines)


def export_report_csv(report_text: str, path: str) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Line"])
        for line in report_text.splitlines():
            w.writerow([line])
