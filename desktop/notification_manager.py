import logging

logger = logging.getLogger(__name__)


class NotificationManager:
    """Notifications de l'application (journal local).

    Aucune dépendance externe (win10toast/pystray retirés) : les événements
    sont journalisés dans logs/ pour traçabilité, sans boîte de dialogue
    intrusive dans la fenêtre native.
    """

    def __init__(self):
        self._running = False

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def send(self, category, title, body):
        logger.info('Notification [%s]: %s — %s', category, title, body)

    def notify(self, title, body, duration=5):
        self.send('info', title, body)

    def notify_important(self, title, body):
        self.send('warning', title, body)
