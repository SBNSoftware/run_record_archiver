import logging
import socket
import time
from typing import Optional

class CarbonClient:

    def __init__(self, host: Optional[str]=None, port: Optional[int]=None, metric_prefix: Optional[str]=None, enabled: bool=False):
        self.enabled = enabled
        self.host = host
        self.port = port or 2003
        self.metric_prefix = metric_prefix
        self._logger = logging.getLogger(__name__)
        if self.enabled and (not (self.host and self.port and self.metric_prefix)):
            self._logger.warning('Carbon client enabled but missing required configuration.')
            self.enabled = False

    def post_metric(self, metric_path: str, value: float, timestamp: Optional[float]=None) -> None:
        if not self.enabled:
            return
        ts = int(timestamp if timestamp is not None else time.time())
        full_metric_path = f'{self.metric_prefix}.{metric_path}'
        message = f'{full_metric_path} {value} {ts}\n'.encode('utf-8')
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2.0)
                sock.connect((self.host, self.port))
                sock.sendall(message)
            self._logger.debug('Posted metric to Carbon: %s', message.strip().decode())
        except (socket.error, socket.timeout) as e:
            self._logger.warning("Could not post metric '%s' to Carbon at %s:%d. Reason: %s", full_metric_path, self.host, self.port, e)