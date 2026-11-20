"""Authenticated loopback IPC. Endpoint secrets stay in the user's AppData."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socket


def runtime_paths(database):
    from .store import default_database
    root = default_database().parent / 'session'
    root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(os.path.normcase(str(Path(database).resolve())).encode()).hexdigest()[:12]
    return root / (key + '.sock'), root / (key + '.lock')


def create_server(path):
    from .firmware import atomic_json
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(('127.0.0.1', 0))
        server.listen(4)
        server.settimeout(.5)
        secret = secrets.token_hex(32)
        atomic_json(path, {'port': server.getsockname()[1], 'token': secret})
        return server, secret
    except BaseException:
        server.close()
        raise


def authenticate(parsed, secret):
    token = parsed.get('token')
    if not isinstance(token, str) or not hmac.compare_digest(token, secret):
        raise ValueError('Session OpenInk non autorisée.')


def request_path(path, command, timeout=2, **payload):
    try:
        endpoint = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ConnectionError('Session OpenInk indisponible.') from exc
    port = endpoint.get('port')
    token = endpoint.get('token')
    if not isinstance(port, int) or not 1 <= port <= 65535 or not isinstance(token, str):
        raise ConnectionError('Session OpenInk invalide.')
    with socket.create_connection(('127.0.0.1', port), timeout=timeout) as sock:
        sock.sendall((json.dumps({**payload, 'command': command, 'token': token}) + '\n').encode())
        raw = b''
        while b'\n' not in raw and len(raw) < 16384:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk
        result = json.loads(raw)
        if not isinstance(result, dict) or not result.get('ok'):
            raise ConnectionError('Commande OpenInk refusée.')
        return result


def tray_request(database, command='Version', **payload):
    path, _ = runtime_paths(database)
    return request_path(path.with_suffix('.tray'), command, **payload)
