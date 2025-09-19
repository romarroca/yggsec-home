import time
import threading
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class BackgroundScheduler:
    def __init__(self):
        self.tasks = []
        self.running = False
        self.thread = None

    def add_task(self, func, interval_hours=24, run_immediately=False):
        """Add a periodic task

        Args:
            func: Function to execute
            interval_hours: How often to run (in hours)
            run_immediately: Whether to run once immediately
        """
        task = {
            'func': func,
            'interval': timedelta(hours=interval_hours),
            'next_run': datetime.now() if run_immediately else datetime.now() + timedelta(hours=interval_hours),
            'name': func.__name__
        }
        self.tasks.append(task)
        logger.info(f"Scheduled task '{task['name']}' to run every {interval_hours} hours")

    def start(self):
        """Start the scheduler"""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info("Background scheduler started")

    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        logger.info("Background scheduler stopped")

    def _run_scheduler(self):
        """Main scheduler loop"""
        while self.running:
            try:
                now = datetime.now()

                for task in self.tasks:
                    if now >= task['next_run']:
                        try:
                            logger.info(f"Executing scheduled task: {task['name']}")
                            task['func']()
                            task['next_run'] = now + task['interval']
                            logger.info(f"Task '{task['name']}' completed. Next run: {task['next_run']}")
                        except Exception as e:
                            logger.error(f"Error executing task '{task['name']}': {e}")
                            # Still update next run time even if task failed
                            task['next_run'] = now + task['interval']

                # Sleep for 1 minute before checking again
                time.sleep(60)

            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(60)

    def get_status(self):
        """Get status of all scheduled tasks"""
        status = {
            'running': self.running,
            'tasks': []
        }

        for task in self.tasks:
            task_status = {
                'name': task['name'],
                'interval_hours': task['interval'].total_seconds() / 3600,
                'next_run': task['next_run'].isoformat(),
                'time_until_next': str(task['next_run'] - datetime.now())
            }
            status['tasks'].append(task_status)

        return status