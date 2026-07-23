# taskpipe

A cron-like pipeline scheduler for orchestrating **shell** and **Python** tasks with sequential/parallel execution, structured logging, and configurable failure recovery.

---

## Features

| Feature | Details |
|---|---|
| **Task types** | Shell/Bash commands, Python scripts, Python functions |
| **Execution modes** | Sequential (with dep ordering) or Parallel (ThreadPoolExecutor) |
| **Failure strategies** | `stop` · `skip` · `retry` with exponential backoff — per task |
| **Dependency resolution** | Topological sort + DAG validation (cycle & missing dep detection) |
| **Cron scheduling** | Standard 5-field cron expressions via `croniter` |
| **Logging** | Colour console + rotating file logs, one file per run |
| **Reports** | Text and JSON status reports saved per run |
| **CLI** | `taskpipe run / validate / report` |

---

## Installation

```bash
pip install taskpipe

# For scheduled (cron) runs:
pip install "taskpipe[scheduled]"
```

---

## Quick Start

### 1. Write a pipeline YAML

```yaml
# my_pipeline.yaml
name: My First Pipeline
execution_mode: sequential
log_dir: logs

tasks:
  - name: say_hello
    type: shell
    command: echo "Hello from taskpipe!"

  - name: run_script
    type: python
    script: process.py
    args: ["--input", "data.csv"]
    depends_on: [say_hello]
    on_failure: retry
    retry:
      max_attempts: 3
      backoff_seconds: 5

  - name: cleanup
    type: shell
    command: rm -f /tmp/scratch
    depends_on: [run_script]
    on_failure: skip
```

### 2. Run it

```bash
# One-shot run
taskpipe run my_pipeline.yaml

# Validate config without running
taskpipe validate my_pipeline.yaml

# View a saved report
taskpipe report logs/My_First_Pipeline_20240524_090000_report.json

# Run on cron schedule (requires taskpipe[scheduled])
taskpipe run my_pipeline.yaml --schedule
```

### 3. Use as a Python library

```python
from taskpipe import PipelineRunner

runner = PipelineRunner.from_file("my_pipeline.yaml")
result = runner.run_once()

print(result.status)           # TaskStatus.SUCCESS / FAILED
print(result.failed_tasks)     # list of TaskResult
```

---

## Pipeline YAML Reference

### Top-level fields

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | **required** | Pipeline name |
| `description` | string | `""` | Human description |
| `schedule` | string | `null` | Cron expression e.g. `"0 9 * * 1-5"` |
| `execution_mode` | `sequential` \| `parallel` | `sequential` | Task execution strategy |
| `max_workers` | int | `4` | Thread pool size (parallel mode only) |
| `log_dir` | string | `"logs"` | Directory for logs and reports |
| `log_level` | string | `"INFO"` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `timeout` | float | `null` | Pipeline-level timeout in seconds |

### Task fields

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | **required** | Unique task name |
| `type` | `shell` \| `python` | **required** | Task executor type |
| `command` | string | — | Shell command (type: shell) |
| `script` | string | — | Python script path (type: python) |
| `function` | string | — | `module:function` to call (type: python) |
| `args` | list | `[]` | Positional args (scripts/functions) |
| `kwargs` | dict | `{}` | Keyword args (functions only) |
| `env` | dict | `{}` | Extra environment variables |
| `timeout` | float | `null` | Task timeout in seconds |
| `on_failure` | `stop` \| `skip` \| `retry` | `stop` | Failure strategy |
| `retry.max_attempts` | int | `3` | Max retry attempts |
| `retry.backoff_seconds` | float | `5.0` | Initial wait before retry |
| `retry.backoff_multiplier` | float | `2.0` | Exponential backoff multiplier |
| `depends_on` | list[str] | `[]` | Task names that must succeed first |
| `working_dir` | string | `null` | Working directory for the task |
| `enabled` | bool | `true` | Set `false` to skip without removing |

---

## Failure Strategies

```
on_failure: stop    → Abort the entire pipeline immediately (default)
on_failure: skip    → Log the failure, mark as skipped, continue
on_failure: retry   → Retry with exponential backoff up to max_attempts
                      If all attempts fail, the pipeline aborts
```

---

## Execution Modes

### Sequential
Tasks run one at a time in dependency order. If task B `depends_on` task A, B runs only after A succeeds.

### Parallel
Tasks run concurrently (thread pool). Dependencies are still respected — a task is only submitted once all its `depends_on` tasks have completed successfully.

---

## Examples

See the `examples/` directory:

- `etl_pipeline.yaml` — Sequential ETL with retries and a Python transform step
- `parallel_checks.yaml` — Parallel system health checks

```bash
taskpipe run examples/etl_pipeline.yaml
taskpipe run examples/parallel_checks.yaml
```

---

## Development

```bash
git clone https://github.com/Sann842/taskpipe
cd taskpipe

pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=taskpipe --cov-report=term-missing
```

---

## Project Structure

```
taskpipe/
├── __init__.py
├── models.py                  # Dataclasses: PipelineConfig, TaskConfig, TaskResult…
├── cli.py                     # CLI entry point
├── executors/
│   ├── shell_executor.py      # Runs shell/bash commands
│   └── python_executor.py     # Runs .py scripts or module:function calls
├── scheduler/
│   ├── pipeline.py            # Orchestrator: dependency resolution + execution
│   ├── task_runner.py         # Retry/backoff/failure strategy wrapper
│   ├── runner.py              # PipelineRunner: one-shot + cron entry points
│   └── reporter.py            # Text + JSON report generation
└── utils/
    ├── config_loader.py       # YAML → PipelineConfig parser
    └── logger.py              # Colour console + rotating file logger
```

---

## License

MIT
