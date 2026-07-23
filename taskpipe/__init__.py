"""
taskpipe
========
Cron-like pipeline scheduler with sequential/parallel task execution,
failure recovery, and structured logging.
"""

from .scheduler.pipeline import Pipeline
from .scheduler.runner import PipelineRunner

__version__ = "0.1.0"
__all__ = ["Pipeline", "PipelineRunner"]
