"""
YAML config parser — converts raw YAML into typed PipelineConfig objects.
"""
from __future__ import annotations
import yaml
from pathlib import Path
from typing import Any, Dict

from ..models import (
    ExecutionMode,
    FailureStrategy,
    PipelineConfig,
    RetryConfig,
    TaskConfig,
    TaskType,
)


class ConfigError(Exception):
    """Raised when a pipeline YAML is invalid or missing required fields."""


def load_pipeline_config(path: str | Path) -> PipelineConfig:
    """Load and validate a pipeline YAML file into a PipelineConfig object."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline config not found: {path}")

    with open(path) as f:
        raw: Dict[str, Any] = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError("Pipeline config must be a YAML mapping.")

    return _parse_pipeline(raw)


def load_pipeline_config_str(yaml_str: str) -> PipelineConfig:
    """Load a pipeline config from a YAML string."""
    raw: Dict[str, Any] = yaml.safe_load(yaml_str)
    if not isinstance(raw, dict):
        raise ConfigError("Pipeline config must be a YAML mapping.")
    return _parse_pipeline(raw)


def _parse_pipeline(raw: Dict[str, Any]) -> PipelineConfig:
    name = _require(raw, "name", "pipeline")

    tasks_raw = raw.get("tasks", [])
    if not isinstance(tasks_raw, list):
        raise ConfigError("'tasks' must be a list.")

    tasks = [_parse_task(t, i) for i, t in enumerate(tasks_raw)]

    # Validate depends_on references before building PipelineConfig
    task_names = {t.name for t in tasks}
    for t in tasks:
        for dep in t.depends_on:
            if dep not in task_names:
                raise ConfigError(
                    f"Task '{t.name}' depends on unknown task '{dep}'."
                )

    execution_mode_str = raw.get("execution_mode", "sequential").lower()
    try:
        execution_mode = ExecutionMode(execution_mode_str)
    except ValueError:
        raise ConfigError(
            f"Invalid execution_mode '{execution_mode_str}'. "
            f"Choose from: {[e.value for e in ExecutionMode]}"
        )

    return PipelineConfig(
        name=name,
        description=raw.get("description", ""),
        schedule=raw.get("schedule"),
        execution_mode=execution_mode,
        tasks=tasks,
        max_workers=int(raw.get("max_workers", 4)),
        log_dir=raw.get("log_dir", "logs"),
        log_level=raw.get("log_level", "INFO").upper(),
        timeout=raw.get("timeout"),
    )


def _parse_task(raw: Dict[str, Any], index: int) -> TaskConfig:
    name = _require(raw, "name", f"tasks[{index}]")

    type_str = _require(raw, "type", f"task '{name}'").lower()
    try:
        task_type = TaskType(type_str)
    except ValueError:
        raise ConfigError(
            f"Task '{name}': invalid type '{type_str}'. "
            f"Choose from: {[e.value for e in TaskType]}"
        )

    on_failure_str = raw.get("on_failure", "stop").lower()
    try:
        on_failure = FailureStrategy(on_failure_str)
    except ValueError:
        raise ConfigError(
            f"Task '{name}': invalid on_failure '{on_failure_str}'. "
            f"Choose from: {[e.value for e in FailureStrategy]}"
        )

    retry_raw = raw.get("retry", {})
    retry = RetryConfig(
        max_attempts=int(retry_raw.get("max_attempts", 3)),
        backoff_seconds=float(retry_raw.get("backoff_seconds", 5.0)),
        backoff_multiplier=float(retry_raw.get("backoff_multiplier", 2.0)),
    )

    return TaskConfig(
        name=name,
        type=task_type,
        command=raw.get("command"),
        script=raw.get("script"),
        function=raw.get("function"),
        args=raw.get("args", []),
        kwargs=raw.get("kwargs", {}),
        env=raw.get("env", {}),
        timeout=raw.get("timeout"),
        on_failure=on_failure,
        retry=retry,
        depends_on=raw.get("depends_on", []),
        working_dir=raw.get("working_dir"),
        enabled=bool(raw.get("enabled", True)),
    )


def _require(raw: Dict[str, Any], key: str, context: str) -> Any:
    if key not in raw:
        raise ConfigError(f"Missing required field '{key}' in {context}.")
    return raw[key]
