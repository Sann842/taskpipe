"""
Data models for pipeline and task configuration.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskType(str, Enum):
    SHELL = "shell"
    PYTHON = "python"


class FailureStrategy(str, Enum):
    RETRY = "retry"
    SKIP = "skip"
    STOP = "stop"


class ExecutionMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


@dataclass
class RetryConfig:
    max_attempts: int = 3
    backoff_seconds: float = 5.0
    backoff_multiplier: float = 2.0  # exponential backoff


@dataclass
class TaskConfig:
    name: str
    type: TaskType
    command: Optional[str] = None        # for shell tasks
    script: Optional[str] = None         # for python tasks
    function: Optional[str] = None       # module:function for python tasks
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)
    timeout: Optional[float] = None      # seconds
    on_failure: FailureStrategy = FailureStrategy.STOP
    retry: RetryConfig = field(default_factory=RetryConfig)
    depends_on: List[str] = field(default_factory=list)
    working_dir: Optional[str] = None
    enabled: bool = True


@dataclass
class PipelineConfig:
    name: str
    description: str = ""
    schedule: Optional[str] = None       # cron expression e.g. "0 9 * * 1-5"
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    tasks: List[TaskConfig] = field(default_factory=list)
    max_workers: int = 4                 # for parallel mode
    log_dir: str = "logs"
    log_level: str = "INFO"
    timeout: Optional[float] = None      # pipeline-level timeout


@dataclass
class TaskResult:
    task_name: str
    status: TaskStatus
    start_time: float
    end_time: float
    attempt: int = 1
    stdout: str = ""
    stderr: str = ""
    return_code: Optional[int] = None
    error: Optional[str] = None

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


@dataclass
class PipelineResult:
    pipeline_name: str
    status: TaskStatus
    start_time: float
    end_time: float
    task_results: List[TaskResult] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def failed_tasks(self) -> List[TaskResult]:
        return [r for r in self.task_results if r.status == TaskStatus.FAILED]

    @property
    def skipped_tasks(self) -> List[TaskResult]:
        return [r for r in self.task_results if r.status == TaskStatus.SKIPPED]
