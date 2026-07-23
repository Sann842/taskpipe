"""Tests for Pipeline orchestration — sequential, parallel, dependencies."""
import logging
import pytest

from taskpipe.models import (
    ExecutionMode, FailureStrategy, PipelineConfig,
    RetryConfig, TaskConfig, TaskStatus, TaskType,
)
from taskpipe.scheduler.pipeline import Pipeline, DependencyError

logger = logging.getLogger("test_pipeline")
logging.basicConfig(level=logging.DEBUG)


def shell(name, command, depends_on=None, on_failure=FailureStrategy.STOP, enabled=True):
    return TaskConfig(
        name=name,
        type=TaskType.SHELL,
        command=command,
        depends_on=depends_on or [],
        on_failure=on_failure,
        retry=RetryConfig(max_attempts=1, backoff_seconds=0.01),
        enabled=enabled,
    )


def pipeline(tasks, mode=ExecutionMode.SEQUENTIAL, max_workers=4):
    return PipelineConfig(
        name="test-pipeline",
        tasks=tasks,
        execution_mode=mode,
        log_dir="/tmp/taskpipe_test_logs",
        max_workers=max_workers,
    )


class TestSequentialPipeline:
    def test_all_success(self):
        cfg = pipeline([
            shell("t1", "echo t1"),
            shell("t2", "echo t2"),
            shell("t3", "echo t3"),
        ])
        result = Pipeline(cfg, logger).run()
        assert result.status == TaskStatus.SUCCESS
        assert all(r.status == TaskStatus.SUCCESS for r in result.task_results)

    def test_aborts_on_stop_failure(self):
        cfg = pipeline([
            shell("ok", "echo ok"),
            shell("bad", "exit 1", on_failure=FailureStrategy.STOP),
            shell("never", "echo never"),
        ])
        result = Pipeline(cfg, logger).run()
        assert result.status == TaskStatus.FAILED
        names = {r.task_name: r.status for r in result.task_results}
        assert names["bad"] == TaskStatus.FAILED
        assert names["never"] == TaskStatus.SKIPPED

    def test_skip_does_not_abort(self):
        cfg = pipeline([
            shell("ok", "echo ok"),
            shell("skip_me", "exit 1", on_failure=FailureStrategy.SKIP),
            shell("after", "echo after"),
        ])
        result = Pipeline(cfg, logger).run()
        names = {r.task_name: r.status for r in result.task_results}
        assert names["skip_me"] == TaskStatus.SKIPPED
        assert names["after"] == TaskStatus.SUCCESS

    def test_disabled_task_skipped(self):
        cfg = pipeline([
            shell("t1", "echo t1"),
            shell("disabled", "echo never", enabled=False),
            shell("t3", "echo t3"),
        ])
        result = Pipeline(cfg, logger).run()
        names = {r.task_name: r.status for r in result.task_results}
        assert names["disabled"] == TaskStatus.SKIPPED
        assert names["t3"] == TaskStatus.SUCCESS


class TestDependencies:
    def test_dependency_respected(self):
        import tempfile, os
        flag = tempfile.mktemp()
        cfg = pipeline([
            shell("t1", f"touch {flag}"),
            shell("t2", f"test -f {flag}", depends_on=["t1"]),
        ])
        result = Pipeline(cfg, logger).run()
        assert result.status == TaskStatus.SUCCESS
        os.unlink(flag)

    def test_failed_dep_skips_downstream(self):
        cfg = pipeline([
            shell("t1", "exit 1", on_failure=FailureStrategy.SKIP),
            shell("t2", "echo t2", depends_on=["t1"]),
        ])
        result = Pipeline(cfg, logger).run()
        names = {r.task_name: r.status for r in result.task_results}
        assert names["t2"] == TaskStatus.SKIPPED

    def test_diamond_dependency(self):
        cfg = pipeline([
            shell("t1", "echo t1"),
            shell("t2", "echo t2", depends_on=["t1"]),
            shell("t3", "echo t3", depends_on=["t1"]),
            shell("t4", "echo t4", depends_on=["t2", "t3"]),
        ])
        result = Pipeline(cfg, logger).run()
        assert result.status == TaskStatus.SUCCESS
        assert all(r.status == TaskStatus.SUCCESS for r in result.task_results)

    def test_circular_dependency_raises(self):
        with pytest.raises(DependencyError, match="[Cc]ircular"):
            cfg = pipeline([
                shell("t1", "echo", depends_on=["t2"]),
                shell("t2", "echo", depends_on=["t1"]),
            ])
            Pipeline(cfg, logger)

    def test_unknown_dependency_raises(self):
        with pytest.raises(DependencyError, match="unknown"):
            cfg = pipeline([
                shell("t1", "echo", depends_on=["ghost"]),
            ])
            Pipeline(cfg, logger)


class TestParallelPipeline:
    def test_parallel_all_success(self):
        cfg = pipeline([
            shell("p1", "sleep 0.1 && echo p1"),
            shell("p2", "sleep 0.1 && echo p2"),
            shell("p3", "sleep 0.1 && echo p3"),
        ], mode=ExecutionMode.PARALLEL, max_workers=3)
        result = Pipeline(cfg, logger).run()
        assert result.status == TaskStatus.SUCCESS
        assert len(result.task_results) == 3

    def test_parallel_with_dependency(self):
        import tempfile, os
        flag = tempfile.mktemp()
        cfg = pipeline([
            shell("init", f"touch {flag}"),
            shell("check1", f"test -f {flag}", depends_on=["init"]),
            shell("check2", f"test -f {flag}", depends_on=["init"]),
        ], mode=ExecutionMode.PARALLEL, max_workers=3)
        result = Pipeline(cfg, logger).run()
        assert result.status == TaskStatus.SUCCESS
        os.unlink(flag)

    def test_parallel_partial_failure(self):
        cfg = pipeline([
            shell("ok1", "echo ok1"),
            shell("bad", "exit 1", on_failure=FailureStrategy.SKIP),
            shell("ok2", "echo ok2"),
        ], mode=ExecutionMode.PARALLEL, max_workers=3)
        result = Pipeline(cfg, logger).run()
        names = {r.task_name: r.status for r in result.task_results}
        assert names["ok1"] == TaskStatus.SUCCESS
        assert names["bad"] == TaskStatus.SKIPPED
        assert names["ok2"] == TaskStatus.SUCCESS


class TestReporter:
    def test_text_report_generated(self):
        from taskpipe.scheduler.reporter import generate_text_report
        cfg = pipeline([shell("t1", "echo hi")])
        result = Pipeline(cfg, logger).run()
        report = generate_text_report(result)
        assert "test-pipeline" in report
        assert "t1" in report
        assert "success" in report.lower()

    def test_json_report_structure(self):
        from taskpipe.scheduler.reporter import generate_json_report
        cfg = pipeline([shell("t1", "echo hi")])
        result = Pipeline(cfg, logger).run()
        report = generate_json_report(result)
        assert "pipeline" in report
        assert "tasks" in report
        assert report["summary"]["total"] == 1
        assert report["summary"]["success"] == 1

    def test_save_report_creates_files(self, tmp_path):
        from taskpipe.scheduler.reporter import save_report
        cfg = pipeline([shell("t1", "echo hi")])
        result = Pipeline(cfg, logger).run()
        saved = save_report(result, report_dir=str(tmp_path), fmt="both")
        assert "text" in saved
        assert "json" in saved
        from pathlib import Path
        assert Path(saved["text"]).exists()
        assert Path(saved["json"]).exists()
