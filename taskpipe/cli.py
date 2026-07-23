"""
CLI entry point for taskpipe.

Usage:
    taskpipe run pipeline.yaml
    taskpipe run pipeline.yaml --schedule
    taskpipe validate pipeline.yaml
    taskpipe report pipeline.yaml
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from .scheduler.runner import PipelineRunner
from .utils.config_loader import load_pipeline_config, ConfigError
from .scheduler.reporter import generate_json_report


def main():
    parser = argparse.ArgumentParser(
        prog="taskpipe",
        description="taskpipe — cron-based pipeline task orchestrator",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a pipeline from a YAML config")
    run_p.add_argument("config", help="Path to pipeline YAML")
    run_p.add_argument(
        "--schedule", action="store_true",
        help="Run on the cron schedule defined in the YAML (blocks)"
    )
    run_p.add_argument(
        "--report-dir", default=None,
        help="Directory for logs and reports (overrides YAML log_dir)"
    )
    run_p.add_argument(
        "--json", action="store_true", dest="json_out",
        help="Print JSON report to stdout after run"
    )

    val_p = sub.add_parser("validate", help="Validate a pipeline YAML without running it")
    val_p.add_argument("config", help="Path to pipeline YAML")

    rep_p = sub.add_parser("report", help="Print a summary of the last run from a JSON report file")
    rep_p.add_argument("report_file", help="Path to a *_report.json file")

    args = parser.parse_args()

    if args.command == "run":
        try:
            runner = PipelineRunner.from_file(args.config)
        except (FileNotFoundError, ConfigError) as e:
            _err(str(e))

        if args.schedule:
            try:
                runner.run_scheduled(report_dir=args.report_dir)
            except (ImportError, ValueError) as e:
                _err(str(e))
        else:
            result = runner.run_once(report_dir=args.report_dir)
            if args.json_out:
                print(json.dumps(generate_json_report(result), indent=2))
            sys.exit(0 if result.status.value == "success" else 1)

    elif args.command == "validate":
        try:
            cfg = load_pipeline_config(args.config)
            print(f"✓  Pipeline '{cfg.name}' is valid.")
            print(f"   Tasks: {len(cfg.tasks)}")
            for t in cfg.tasks:
                deps = f"  [depends: {', '.join(t.depends_on)}]" if t.depends_on else ""
                print(f"   - {t.name} ({t.type.value}){deps}")
        except (FileNotFoundError, ConfigError) as e:
            _err(str(e))

    elif args.command == "report":
        path = Path(args.report_file)
        if not path.exists():
            _err(f"Report file not found: {path}")
        raw = json.loads(path.read_text())

        print(f"\n{'='*55}")
        print(f"  Pipeline : {raw['pipeline']}")
        print(f"  Status   : {raw['status'].upper()}")
        print(f"  Duration : {raw['duration_seconds']:.2f}s")
        s = raw['summary']
        print(f"  Tasks    : {s['total']}  ✓{s['success']}  ✗{s['failed']}  –{s['skipped']}")
        print(f"{'='*55}")
        for t in raw['tasks']:
            icon = {"success": "✓", "failed": "✗", "skipped": "–"}.get(t['status'], "?")
            print(f"  {icon}  {t['name']:<28} {t['status']:<10} {t['duration_seconds']:.2f}s")
            if t.get('error'):
                print(f"       ERROR: {t['error'].strip()[:100]}")
        print(f"{'='*55}\n")


def _err(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
