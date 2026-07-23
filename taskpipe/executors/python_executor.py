"""
Python executor: runs .py scripts via subprocess OR calls importable module:function directly.
"""
from __future__ import annotations
import importlib
import io
import os
import subprocess
import sys
import time
import traceback
from contextlib import redirect_stdout, redirect_stderr
from logging import Logger

from ..models import TaskConfig, TaskResult, TaskStatus


def execute_python(
    task: TaskConfig,
    attempt: int,
    logger: Logger,
) -> TaskResult:
    """
    Execute a Python task.

    - If `task.script` is set  → run as a subprocess (`python task.script`)
    - If `task.function` is set → import and call `module:function` in-process
    """
    if task.script:
        return _run_script(task, attempt, logger)
    elif task.function:
        return _run_function(task, attempt, logger)
    else:
        start = end = time.time()
        msg = f"Task '{task.name}': python task must have 'script' or 'function' set."
        logger.error(f"  [python] {msg}")
        return TaskResult(
            task_name=task.name,
            status=TaskStatus.FAILED,
            start_time=start,
            end_time=end,
            attempt=attempt,
            error=msg,
        )


def _run_script(task: TaskConfig, attempt: int, logger: Logger) -> TaskResult:
    start = time.time()
    script = task.script
    logger.info(f"  [python] Running script: {script!r}  (attempt {attempt})")

    env = {**os.environ, **task.env}
    cwd = task.working_dir or None

    cli_args = [str(a) for a in task.args]
    cmd = [sys.executable, script] + cli_args

    try:
        proc = subprocess.run(
            cmd,
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
        if not success:
            logger.error(f"  [python] Script '{script}' exited with code {proc.returncode}")

        return TaskResult(
            task_name=task.name,
            status=TaskStatus.SUCCESS if success else TaskStatus.FAILED,
            start_time=start,
            end_time=end,
            attempt=attempt,
            stdout=proc.stdout,
            stderr=proc.stderr,
            return_code=proc.returncode,
        )

    except subprocess.TimeoutExpired as e:
        end = time.time()
        msg = f"Script '{script}' timed out after {task.timeout}s"
        logger.error(f"  [python] {msg}")
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

    except Exception as exc:
        end = time.time()
        logger.error(f"  [python] Unexpected error running script: {exc}")
        return TaskResult(
            task_name=task.name,
            status=TaskStatus.FAILED,
            start_time=start,
            end_time=end,
            attempt=attempt,
            error=str(exc),
        )


def _run_function(task: TaskConfig, attempt: int, logger: Logger) -> TaskResult:
    """Import and call module:function in-process, capturing stdout/stderr."""
    start = time.time()
    func_ref = task.function
    logger.info(f"  [python] Calling function: {func_ref!r}  (attempt {attempt})")

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        module_name, func_name = func_ref.rsplit(":", 1)
    except ValueError:
        end = time.time()
        msg = f"'function' must be 'module.path:function_name', got: {func_ref!r}"
        logger.error(f"  [python] {msg}")
        return TaskResult(
            task_name=task.name,
            status=TaskStatus.FAILED,
            start_time=start,
            end_time=end,
            attempt=attempt,
            error=msg,
        )

    try:
        mod = importlib.import_module(module_name)
        func = getattr(mod, func_name)

        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            func(*task.args, **task.kwargs)

        end = time.time()
        out = stdout_buf.getvalue()
        err = stderr_buf.getvalue()

        if out.strip():
            for line in out.strip().splitlines():
                logger.info(f"    stdout | {line}")
        if err.strip():
            for line in err.strip().splitlines():
                logger.warning(f"    stderr | {line}")

        return TaskResult(
            task_name=task.name,
            status=TaskStatus.SUCCESS,
            start_time=start,
            end_time=end,
            attempt=attempt,
            stdout=out,
            stderr=err,
            return_code=0,
        )

    except Exception:
        end = time.time()
        tb = traceback.format_exc()
        out = stdout_buf.getvalue()
        err = stderr_buf.getvalue()
        logger.error(f"  [python] Function '{func_ref}' raised an exception:\n{tb}")
        return TaskResult(
            task_name=task.name,
            status=TaskStatus.FAILED,
            start_time=start,
            end_time=end,
            attempt=attempt,
            stdout=out,
            stderr=err,
            error=tb,
        )
