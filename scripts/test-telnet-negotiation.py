#!/usr/bin/env python
"""Smoke-test the installed inetutils telnetd over an isolated loopback socket."""

from __future__ import print_function

import socket
import subprocess


def main():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client = socket.create_connection(listener.getsockname(), 5)
    connection, _ = listener.accept()
    daemon = None
    try:
        # telnetd is an inetd-style service, so pass the accepted connection
        # as its standard input/output without enabling the systemd socket.
        daemon = subprocess.Popen(
            ["/usr/libexec/telnetd"], stdin=connection,
            stdout=connection, stderr=connection,
        )
        client.settimeout(5)
        first = client.recv(8)
        if not first.startswith(b"\xff"):
            raise RuntimeError("telnetd did not start TELNET option negotiation: %r" % first)
        print("telnetd negotiated over loopback")
    finally:
        client.close()
        connection.close()
        listener.close()
        if daemon is not None:
            daemon.terminate()
            daemon.communicate()


if __name__ == "__main__":
    main()
