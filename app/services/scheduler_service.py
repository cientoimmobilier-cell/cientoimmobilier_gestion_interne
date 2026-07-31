"""
Planificateur des sauvegardes cloud automatiques.

Thread de fond demonique demarre une fois par processus. Verifie chaque
30 secondes si une sauvegarde est due (frequency : hourly/daily/weekly/monthly)
puis lance l'orchestrateur en arriere-plan.
"""
import calendar
import threading
from datetime import datetime, timedelta, timezone

from app import db
from app.models import CloudBackupSchedule
from app.services.backup_service import BackupService

BACKUP_TYPE_BY_FREQUENCY = {
    'hourly': 'Daily',
    'daily': 'Daily',
    'weekly': 'Weekly',
    'monthly': 'Monthly',
}


def compute_next_run(frequency, hour=2, minute=0, day_of_week=1,
                     day_of_month=1, from_time=None):
    """Prochaine echeance d'une sauvegarde planifiee (UTC)."""
    now = from_time or datetime.now(timezone.utc)
    hour = int(hour or 0) % 24
    minute = int(minute or 0) % 60

    if frequency == 'hourly':
        return (now + timedelta(hours=1)).replace(
            minute=0, second=0, microsecond=0)

    if frequency == 'daily':
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if frequency == 'weekly':
        dow = int(day_of_week or 0) % 7  # 0=lundi
        days_ahead = (dow - now.weekday()) % 7
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        candidate += timedelta(days=days_ahead)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate

    if frequency == 'monthly':
        dom = max(1, min(int(day_of_month or 1), 28))
        year, month = now.year, now.month
        last_day = calendar.monthrange(year, month)[1]
        candidate = datetime(year, month, min(dom, last_day), hour, minute,
                             tzinfo=timezone.utc)
        if candidate <= now:
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
            last_day = calendar.monthrange(year, month)[1]
            candidate = datetime(year, month, min(dom, last_day), hour, minute,
                                 tzinfo=timezone.utc)
        return candidate

    raise ValueError(f'Fréquence inconnue : {frequency}')


class BackupScheduler:
    def __init__(self):
        self._thread = None
        self._stop = threading.Event()

    def start(self, app):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._loop, args=(app,), daemon=True,
            name='cloud-backup-scheduler')
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self, app):
        while not self._stop.wait(30):
            try:
                with app.app_context():
                    self._tick(app)
            except Exception:
                db.session.rollback()
                continue

    def _tick(self, app):
        schedule = CloudBackupSchedule.get()
        if not schedule.enabled:
            return
        now = datetime.now(timezone.utc)
        if not schedule.next_run_at or schedule.next_run_at > now:
            return

        schedule.last_run_at = now
        schedule.next_run_at = compute_next_run(
            schedule.frequency, schedule.hour, schedule.minute,
            schedule.day_of_week, schedule.day_of_month, from_time=now)
        db.session.commit()

        backup_type = BACKUP_TYPE_BY_FREQUENCY.get(
            schedule.frequency, 'Daily')
        service = app.extensions.get('backup_service')
        if service is None:
            service = BackupService(app)
            app.extensions['backup_service'] = service
        service.run_manual_backup('Planificateur', backup_type,
                                  schedule.include_data)
