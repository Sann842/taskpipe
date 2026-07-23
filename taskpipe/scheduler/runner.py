"""
PipelineRunner: top-level entry point.
- One-shot run: load config → run → report
- Scheduled run: parse cron expression → loop via schedule library
"""
from __future__ import annotations
import time
from typing import Optional

from ..models import PipelineConfig, PipelineResult
from ..utils.config_loader import load_pipeline_config, load_pipeline_config_str
from ..utils.logger import get_run_logger
from .pipeline import Pipeline
from .reporter import save_report


class PipelineRunner:
    """
    High-level runner.

    Usage (one-shot):
        runner = PipelineRunner.from_file("pipeline.yaml")
        result = runner.run_once()

    Usage (scheduled):
        runner = PipelineRunner.from_file("pipeline.yaml")
        runner.run_scheduled()   # blocks, uses cron in YAML
    """

    def __init__(self, config: PipelineConfig):
        self.config = config

    @classmethod
    def from_file(cls, path: str) -> "PipelineRunner":
        config = load_pipeline_config(path)
        return cls(config)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "PipelineRunner":
        config = load_pipeline_config_str(yaml_str)
        return cls(config)

    def run_once(self, report_dir: Optional[str] = None) -> PipelineResult:
        """Execute the pipeline once and save reports."""
        cfg = self.config
        log_dir = report_dir or cfg.log_dir
        logger = get_run_logger(cfg.name, log_dir=log_dir, log_level=cfg.log_level)

        pipeline = Pipeline(cfg, logger)
        result = pipeline.run()

        saved = save_report(result, report_dir=log_dir)
        for fmt, path in saved.items():
            logger.info(f"Report saved ({fmt}): {path}")

        return result

    def run_scheduled(self, report_dir: Optional[str] = None) -> None:
        """
        Block and run the pipeline on the cron schedule defined in the YAML.
        Requires `schedule` and `croniter` packages.

        Install: pip install taskpipe[scheduled]
        """
        try:
            import schedule as sched
            from croniter import croniter
        except ImportError:
            raise ImportError(
                "Scheduled runs require extra deps:\n"
                "  pip install taskpipe[scheduled]"
            )

        cron_expr = self.config.schedule
        if not cron_expr:
            raise ValueError(
                "No 'schedule' field in pipeline config. "
                "Add a cron expression, e.g. schedule: '0 9 * * 1-5'"
            )

        if not croniter.is_valid(cron_expr):
            raise ValueError(f"Invalid cron expression: {cron_expr!r}")

        cfg = self.config
        log_dir = report_dir or cfg.log_dir
        ctrl_logger = get_run_logger(
            f"{cfg.name}_scheduler", log_dir=log_dir, log_level=cfg.log_level
        )
        ctrl_logger.info(
            f"Scheduler started for pipeline '{cfg.name}' — cron: '{cron_expr}'"
        )

        def _job():
            ctrl_logger.info(f"Cron triggered — running pipeline '{cfg.name}'")
            self.run_once(report_dir=log_dir)

        sched.every().minute.do(_check_and_run, cron_expr=cron_expr, job=_job)

        ctrl_logger.info("Scheduler loop running. Press Ctrl+C to stop.")
        try:
            while True:
                sched.run_pending()
                time.sleep(30)
        except KeyboardInterrupt:
            ctrl_logger.info("Scheduler stopped.")


def _check_and_run(cron_expr: str, job):
    """Called every minute; delegates to croniter to check if now matches."""
    from croniter import croniter
    import datetime
    now = datetime.datetime.now()
    cron = croniter(cron_expr, now - datetime.timedelta(minutes=1))
    next_run = cron.get_next(datetime.datetime)
    if abs((next_run - now).total_seconds()) <= 30:
        job()
