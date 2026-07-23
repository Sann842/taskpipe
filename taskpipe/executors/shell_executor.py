"""
Shell executor: runs Bash/shell commands as subprocesses.
"""
from __future__ import annotations
import os
import subprocess
import time
from logging import Logger

from ..models import TaskConfig, TaskResult, TaskStatus


def execute_shell(
    task: TaskConfig,
    attempt: int,
    logger: Logger,
) -> TaskResult:
    """Execute a shell/bash command and return a TaskResult."""
    start = time.time()
    logger.info(f"  [shell] Running: {task.command!r}  (attempt {attempt})")

    env = {**os.environ, **task.env}
    cwd = task.working_dir or None

    try:
        proc = subprocess.run(
            task.command,
            shell=True,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=task.timeout,
        )
        end = time.time()

        if proc.stdout.strip():
            for line in proc.stdout.strip().splitlines():
                logger.info(f"    stdout | {line}")
        if proc.stderr.strip():
            for line in proc.stderr.strip().splitlines():
                logger.warning(f"    stderr | {line}")

        success = proc.returncode == 0
        status = TaskStatus.SUCCESS if success else TaskStatus.FAILED

        if not success:
            logger.error(f"  [shell] Task '{task.name}' exited with code {proc.returncode}")

        return TaskResult(
            task_name=task.name,
            status=status,
            start_time=start,
            end_time=end,
            attempt=attempt,
            stdout=proc.stdout,
            stderr=proc.stderr,
            return_code=proc.returncode,
        )

    except subprocess.TimeoutExpired as e:
        end = time.time()
        msg = f"Task '{task.name}' timed out after {task.timeout}s"
        logger.error(f"  [shell] {msg}")
        return TaskResult(
            task_name=task.name,
            status=TaskStatus.FAILED,
            start_time=start,
            end_time=end,
            attempt=attempt,
            stdout=e.stdout or "",
            stderr=e.stderr or "",
            error=msg,
        )

    except Exception as e:
        end = time.time()
        logger.error(f"  [shell] Unexpected error in task '{task.name}': {e}")
        return TaskResult(
            task_name=task.name,
            status=TaskStatus.FAILED,
            start_time=start,
            end_time=end,
            attempt=attempt,
            error=str(e),
        )
