import socket
import random
import logging
from contextlib import closing

logger = logging.getLogger(__name__)


class PortManager:
    DEFAULT_PORT = 5005
    MAX_PORT = 5100

    def __init__(self):
        self._port = None
        self._is_ciento_instance = False

    @staticmethod
    def is_port_available(port):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            return result != 0

    @staticmethod
    def is_ciento_server(port):
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(2)
                if sock.connect_ex(('127.0.0.1', port)) == 0:
                    sock.send(b'GET /health HTTP/1.0\r\nHost: localhost\r\n\r\n')
                    response = sock.recv(1024)
                    return b'OK' in response
        except Exception:
            pass
        return False

    def find_free_port(self, preferred=None):
        port = preferred or self.DEFAULT_PORT
        if self.is_port_available(port):
            logger.info(f'Port {port} is available')
            self._port = port
            return port

        if self.is_ciento_server(port):
            logger.info(f'CIENTO already running on port {port}')
            self._port = port
            self._is_ciento_instance = True
            return port

        for test_port in range(port + 1, self.MAX_PORT + 1):
            if self.is_port_available(test_port):
                logger.info(f'Found free port: {test_port}')
                self._port = test_port
                return test_port

        fallback = random.randint(10500, 65535)
        while not self.is_port_available(fallback):
            fallback = random.randint(10500, 65535)
        logger.warning(f'Using fallback port: {fallback}')
        self._port = fallback
        return fallback

    @property
    def port(self):
        return self._port

    @property
    def is_already_running(self):
        return self._is_ciento_instance
