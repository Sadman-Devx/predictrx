"""Celery entry point for an evaluation run. All logic lives in runner.execute_run (claim -> predict -> persist).

A duplicate delivery finds status != queued and returns 'skipped'. soft_time_limit stays below CELERY_TASK_TIME_LIMIT
(300 s) so the runner can still mark the run `failed` with error 'timeout'.
"""
from celery import shared_task

from . import runner


@shared_task(soft_time_limit=270)
def run_evaluation(run_id: int) -> str:
    return runner.execute_run(run_id)