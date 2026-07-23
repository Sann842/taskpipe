"""
Pipeline orchestrator: resolves task dependencies, runs tasks sequentially
or in parallel (ThreadPoolExecutor), aggregates results.
"""
from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger
from typing import Dict, List, Optional

from ..models import (
    ExecutionMode,
    PipelineConfig,
    PipelineResult,
    TaskConfig,
    TaskResult,
    TaskStatus,
)
from .task_runner import TaskAbortError, run_task


class DependencyError(Exception):
    """Raised when task dependency graph has issues (cycles, missing deps)."""


class Pipeline:
    """
    Orchestrates a PipelineConfig: validates deps, runs tasks, returns results.
    """

    def __init__(self, config: PipelineConfig, logger: Logger):
        self.config = config
        self.logger = logger
        self._validate_dependencies()

    def run(self) -> PipelineResult:
        cfg = self.config
        self.logger.info(f"{'='*60}")
        self.logger.info(f"  Pipeline : {cfg.name}")
        self.logger.info(f"  Mode     : {cfg.execution_mode.value}")
        self.logger.info(f"  Tasks    : {len(cfg.tasks)}")
        self.logger.info(f"{'='*60}")

        start = time.time()

        if cfg.execution_mode == ExecutionMode.SEQUENTIAL:
            results = self._run_sequential()
        else:
            results = self._run_parallel()

        end = time.time()

        failed = [r for r in results if r.status == TaskStatus.FAILED]
        pipeline_status = TaskStatus.FAILED if failed else TaskStatus.SUCCESS

        pipeline_result = PipelineResult(
            pipeline_name=cfg.name,
            status=pipeline_status,
            start_time=start,
            end_time=end,
            task_results=results,
        )

        self._log_summary(pipeline_result)
        return pipeline_result

    def _run_sequential(self) -> List[TaskResult]:
        results: List[TaskResult] = []
        completed: Dict[str, TaskStatus] = {}

        ordered = self._topological_sort()

        for task in ordered:
            skip_reason = self._check_dependencies(task, completed)
            if skip_reason:
                self.logger.warning(
                    f"Skipping task '{task.name}': dependency failed — {skip_reason}"
                )
                now = time.time()
                result = TaskResult(
                    task_name=task.name,
                    status=TaskStatus.SKIPPED,
                    start_time=now,
                    end_time=now,
                    error=skip_reason,
                )
                results.append(result)
                completed[task.name] = TaskStatus.SKIPPED
                continue

            self.logger.info(f"\n→ Task [{task.name}]")
            try:
                result = run_task(task, self.logger)
            except TaskAbortError as e:
                results.append(e.result)
                completed[task.name] = TaskStatus.FAILED
                self.logger.error(f"Pipeline aborted at task '{task.name}'.")
                remaining_names = {t.name for t in ordered} - set(completed.keys())
                for name in remaining_names:
                    now = time.time()
                    results.append(TaskResult(
                        task_name=name,
                        status=TaskStatus.SKIPPED,
                        start_time=now,
                        end_time=now,
                        error="Pipeline aborted by upstream failure.",
                    ))
                break

            results.append(result)
            completed[task.name] = result.status

        return results

    def _run_parallel(self) -> List[TaskResult]:
        completed: Dict[str, TaskStatus] = {}
        results: List[TaskResult] = []
        pending = list(self.config.tasks)

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as pool:
            futures = {}

            while pending or futures:
                still_pending = []
                for task in pending:
                    skip_reason = self._check_dependencies(task, completed)
                    if skip_reason is not None:
                        self.logger.warning(f"Skipping task '{task.name}': {skip_reason}")
                        now = time.time()
                        r = TaskResult(
                            task_name=task.name,
                            status=TaskStatus.SKIPPED,
                            start_time=now,
                            end_time=now,
                            error=skip_reason,
                        )
                        results.append(r)
                        completed[task.name] = TaskStatus.SKIPPED
                    elif all(d in completed for d in task.depends_on):
                        self.logger.info(f"\n→ Task [{task.name}] (parallel)")
                        fut = pool.submit(run_task, task, self.logger)
                        futures[fut] = task
                    else:
                        still_pending.append(task)

                pending = still_pending

                if not futures:
                    if pending:
                        time.sleep(0.1)
                    continue

                done_futures = [f for f in futures if f.done()]
                if not done_futures:
                    done_set = set()
                    for fut in as_completed(futures, timeout=1):
                        done_set.add(fut)
                        break
                    done_futures = list(done_set)

                for fut in done_futures:
                    task = futures.pop(fut)
                    try:
                        result = fut.result()
                    except TaskAbortError as e:
                        result = e.result
                        self.logger.error(
                            f"Task '{task.name}' aborted pipeline (on_failure=stop)."
                        )
                    except Exception as e:
                        now = time.time()
                        result = TaskResult(
                            task_name=task.name,
                            status=TaskStatus.FAILED,
                            start_time=now,
                            end_time=now,
                            error=str(e),
                        )
                    results.append(result)
                    completed[task.name] = result.status

        return results

    def _check_dependencies(
        self, task: TaskConfig, completed: Dict[str, TaskStatus]
    ) -> Optional[str]:
        for dep in task.depends_on:
            status = completed.get(dep)
            if status is None:
                return None
            if status in (TaskStatus.FAILED, TaskStatus.SKIPPED):
                return f"dependency '{dep}' has status '{status.value}'"
        return None

    def _topological_sort(self) -> List[TaskConfig]:
        tasks = {t.name: t for t in self.config.tasks}
        in_degree = {name: 0 for name in tasks}
        graph: Dict[str, List[str]] = {name: [] for name in tasks}

        for task in self.config.tasks:
            for dep in task.depends_on:
                graph[dep].append(task.name)
                in_degree[task.name] += 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        ordered: List[TaskConfig] = []

        while queue:
            name = queue.pop(0)
            ordered.append(tasks[name])
            for neighbour in graph[name]:
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if len(ordered) != len(tasks):
            raise DependencyError("Circular dependency detected in pipeline tasks.")

        return ordered

    def _validate_dependencies(self) -> None:
        names = {t.name for t in self.config.tasks}
        for task in self.config.tasks:
            for dep in task.depends_on:
                if dep not in names:
                    raise DependencyError(
                        f"Task '{task.name}' depends on unknown task '{dep}'."
                    )
        self._topological_sort()

    def _log_summary(self, result: PipelineResult) -> None:
        logger = self.logger
        logger.info(f"\n{'='*60}")
        logger.info(f"  Pipeline Summary: {result.pipeline_name}")
        logger.info(f"  Status   : {result.status.value.upper()}")
        logger.info(f"  Duration : {result.duration:.2f}s")
        logger.info(f"  Tasks    : {len(result.task_results)}")
        logger.info(f"{'='*60}")
        for r in result.task_results:
            icon = {"success": "✓", "failed": "✗", "skipped": "–"}.get(r.status.value, "?")
            logger.info(
                f"  {icon}  {r.task_name:<30} {r.status.value:<10} {r.duration:.2f}s"
                + (f"  [attempt {r.attempt}]" if r.attempt > 1 else "")
            )
        logger.info(f"{'='*60}\n")
