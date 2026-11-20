"""Nonblocking process locks, using the native OS implementation."""
import os

if os.name != 'nt':
    import fcntl
else:
    import errno
    import msvcrt

    class fcntl:
        LOCK_EX = 2
        LOCK_NB = 4
        LOCK_UN = 8

        @staticmethod
        def flock(handle, operation):
            handle.seek(0)
            if operation == fcntl.LOCK_UN:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                return
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b'\0')
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise BlockingIOError(errno.EAGAIN, 'OpenInk lock already held') from exc
