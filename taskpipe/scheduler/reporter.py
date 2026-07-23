"""
Status reporter: generates human-readable and JSON status reports.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

from ..models import PipelineResult, TaskStatus


def generate_text_report(result: PipelineResult) -> str:
    lines = [
        "=" * 60,
        f"  PIPELINE REPORT",
        f"  Pipeline : {result.pipeline_name}",
        f"  Status   : {result.status.value.upper()}",
        f"  Started  : {datetime.fromtimestamp(result.start_time).strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Finished : {datetime.fromtimestamp(result.end_time).strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Duration : {result.duration:.2f}s",
        "=" * 60,
        "",
        "  TASK RESULTS",
        "-" * 60,
    ]

    for r in result.task_results:
        icon = {"success": "✓", "failed": "✗", "skipped": "–"}.get(r.status.value, "?")
        lines.append(
            f"  {icon}  {r.task_name:<28} {r.status.value:<10}  {r.duration:.2f}s"
            + (f"  (attempt {r.attempt})" if r.attempt > 1 else "")
        )
        if r.error:
            lines.append(f"       ERROR: {r.error.strip()[:120]}")

    lines += [
        "-" * 60,
        f"  Total: {len(result.task_results)} tasks  |  "
        f"Success: {sum(1 for r in result.task_results if r.status == TaskStatus.SUCCESS)}  |  "
        f"Failed: {len(result.failed_tasks)}  |  "
        f"Skipped: {len(result.skipped_tasks)}",
        "=" * 60,
    ]
    return "\n".join(lines)


def generate_json_report(result: PipelineResult) -> dict:
    return {
        "pipeline": result.pipeline_name,
        "status": result.status.value,
        "started_at": datetime.fromtimestamp(result.start_time).isoformat(),
        "finished_at": datetime.fromtimestamp(result.end_time).isoformat(),
        "duration_seconds": round(result.duration, 3),
        "summary": {
            "total": len(result.task_results),
            "success": sum(1 for r in result.task_results if r.status == TaskStatus.SUCCESS),
            "failed": len(result.failed_tasks),
            "skipped": len(result.skipped_tasks),
        },
        "tasks": [
            {
                "name": r.task_name,
                "status": r.status.value,
                "attempt": r.attempt,
                "duration_seconds": round(r.duration, 3),
                "return_code": r.return_code,
                "error": r.error,
            }
            for r in result.task_results
        ],
    }


def save_report(
    result: PipelineResult,
    report_dir: str = "logs",
    fmt: str = "both",
) -> dict[str, str]:
    """
    Save report(s) to disk. Returns a dict of {format: filepath}.
    """
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.fromtimestamp(result.start_time).strftime("%Y%m%d_%H%M%S")
    safe = result.pipeline_name.replace(" ", "_")
    saved = {}

    if fmt in ("text", "both"):
        path = Path(report_dir) / f"{safe}_{ts}_report.txt"
        path.write_text(generate_text_report(result), encoding="utf-8")
        saved["text"] = str(path)

    if fmt in ("json", "both"):
        path = Path(report_dir) / f"{safe}_{ts}_report.json"
        path.write_text(
            json.dumps(generate_json_report(result), indent=2), encoding="utf-8"
        )
        saved["json"] = str(path)

    return saved
