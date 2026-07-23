"""Tests for the YAML config loader."""
import pytest
from taskpipe.utils.config_loader import (
    load_pipeline_config_str,
    ConfigError,
)
from taskpipe.models import ExecutionMode, FailureStrategy, TaskType


MINIMAL_YAML = """
name: test-pipeline
tasks:
  - name: hello
    type: shell
    command: echo hello
"""

FULL_YAML = """
name: full-pipeline
description: Full config test
execution_mode: parallel
max_workers: 2
log_dir: /tmp/logs
log_level: DEBUG
schedule: "0 9 * * *"
tasks:
  - name: step1
    type: shell
    command: echo step1
    on_failure: retry
    retry:
      max_attempts: 3
      backoff_seconds: 2.0
      backoff_multiplier: 1.5
  - name: step2
    type: python
    script: myscript.py
    depends_on: [step1]
    on_failure: skip
    timeout: 30
"""


def test_minimal_config():
    cfg = load_pipeline_config_str(MINIMAL_YAML)
    assert cfg.name == "test-pipeline"
    assert len(cfg.tasks) == 1
    assert cfg.tasks[0].type == TaskType.SHELL
    assert cfg.execution_mode == ExecutionMode.SEQUENTIAL


def test_full_config():
    cfg = load_pipeline_config_str(FULL_YAML)
    assert cfg.name == "full-pipeline"
    assert cfg.execution_mode == ExecutionMode.PARALLEL
    assert cfg.max_workers == 2
    assert cfg.schedule == "0 9 * * *"
    assert len(cfg.tasks) == 2

    t1 = cfg.tasks[0]
    assert t1.on_failure == FailureStrategy.RETRY
    assert t1.retry.max_attempts == 3
    assert t1.retry.backoff_multiplier == 1.5

    t2 = cfg.tasks[1]
    assert t2.depends_on == ["step1"]
    assert t2.on_failure == FailureStrategy.SKIP
    assert t2.timeout == 30


def test_missing_name_raises():
    with pytest.raises(ConfigError, match="name"):
        load_pipeline_config_str("tasks: []")


def test_invalid_execution_mode():
    with pytest.raises(ConfigError, match="execution_mode"):
        load_pipeline_config_str("name: p\nexecution_mode: diagonal\ntasks: []")


def test_invalid_task_type():
    yaml = "name: p\ntasks:\n  - name: t\n    type: sql\n    command: x"
    with pytest.raises(ConfigError, match="type"):
        load_pipeline_config_str(yaml)


def test_unknown_dependency_raises():
    yaml = """
name: p
tasks:
  - name: t1
    type: shell
    command: echo hi
    depends_on: [missing_task]
"""
    with pytest.raises(Exception, match="unknown task"):
        load_pipeline_config_str(yaml)
