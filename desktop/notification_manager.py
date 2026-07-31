import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class WindowsToastNotifier:
    def __init__(self):
        self._enabled = False
        self._app_id = 'CientoImmobilier.EnterpriseDesktop.1.0.0'

    def initialize(self):
        try:
            from win32api import SetCurrentProcessExplicitAppUserModelID
            SetCurrentProcessExplicitAppUserModelID(self._app_id)
            self._enabled = True
            logger.info('Windows toast notifications initialized')
        except Exception as e:
            logger.warning(f'Toast notifications unavailable: {e}')
            self._enabled = False

    def notify(self, title, body, duration=5):
        if not self._enabled:
            logger.info(f'[NOTIFICATION] {title}: {body}')
            return
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, body, duration=duration, threaded=True)
        except Exception as e:
            logger.warning(f'Failed to send notification: {e}')

    def notify_important(self, title, body):
        self.notify(title, body, duration=10)


class NotificationManager:
    def __init__(self):
        self.toaster = WindowsToastNotifier()
        self._reminder_threads = []
        self._running = False

    def start(self):
        self.toaster.initialize()
        self._running = True

    def stop(self):
        self._running = False

    def send(self, category, title, body):
        mapping = {
            'info': self.toaster.notify,
            'warning': self.toaster.notify,
            'error': lambda t, b, d=8: self.toaster.notify(t, b, d),
            'success': self.toaster.notify,
        }
        handler = mapping.get(category, self.toaster.notify)
        handler(title, body)
        logger.info(f'Notification [{category}]: {title} — {body}')
