import sys
import logging

logger = logging.getLogger(__name__)


class SingleInstance:
    _instance = None
    _mutex_name = 'CIENTO_IMMOBILIER_Enterprise_Desktop_Instance'

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._mutex = None
            cls._instance._owned = False
        return cls._instance

    def acquire(self):
        try:
            import win32event
            import win32api
            import winerror
        except ImportError:
            logger.warning('pywin32 not available — single instance check disabled')
            self._owned = True
            return True

        try:
            self._mutex = win32event.CreateMutex(None, False, self._mutex_name)
            last_error = win32api.GetLastError()
            if last_error == winerror.ERROR_ALREADY_EXISTS:
                logger.info('Another instance is already running — bringing it to foreground')
                self._owned = False
                self._bring_existing_to_foreground()
                return False
            self._owned = True
            logger.info('Single instance lock acquired')
            return True
        except Exception as e:
            logger.error(f'Failed to acquire single instance lock: {e}')
            self._owned = True
            return True

    def _bring_existing_to_foreground(self):
        try:
            import win32gui
            import win32con
            hwnd = win32gui.FindWindow(None, 'CIENTO IMMOBILIER')
            if hwnd:
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
        except Exception as e:
            logger.warning(f'Could not bring existing window to foreground: {e}')

    def release(self):
        if self._mutex and self._owned:
            try:
                import win32event
                win32event.ReleaseMutex(self._mutex)
                logger.info('Single instance lock released')
            except Exception:
                pass
