import threading

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler

# Per-thread flag: True only on the APScheduler background thread, inside _process_jobs.
# Keeps the swallow logic isolated to that thread so concurrent delete_job API calls
# on other threads still raise JobLookupError correctly.
_local = threading.local()


class ResilientBackgroundScheduler(BackgroundScheduler):
    """
    BackgroundScheduler that survives JobLookupError during one-shot job
    cleanup in _process_jobs. Prevents the scheduler thread from dying when
    a job is removed externally (e.g. via dispatch/delete API) before
    APScheduler can clean it up after firing.

    Uses threading.local() so the flag is per-thread: only the APScheduler
    thread sees it as True, keeping public delete_job API behavior unchanged.
    """

    def _process_jobs(self):
        _local.in_process_jobs = True
        try:
            return super()._process_jobs()
        finally:
            _local.in_process_jobs = False

    def remove_job(self, job_id, jobstore=None):
        try:
            super().remove_job(job_id, jobstore=jobstore)
        except JobLookupError:
            if getattr(_local, 'in_process_jobs', False):
                self._logger.warning(
                    "One-shot job '%s' already removed from jobstore; skipping cleanup.", job_id
                )
            else:
                raise
