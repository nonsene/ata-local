"""Deny outbound Python connections during inference, in addition to offline model flags."""
import ipaddress
import socket


def restrict_network():
    if getattr(socket, "_ata_restricted", False):
        return
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_resolve = socket.getaddrinfo

    def allowed(address):
        host = address[0]
        if host == "localhost":
            return
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except ValueError:
            pass
        raise OSError("Ata Local bloqueou uma conexão externa durante a execução")

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            allowed(address)
        return original_connect(self, address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            allowed(address)
        return original_connect_ex(self, address)

    def resolve(host, port, *args, **kwargs):
        if host is not None:
            allowed((host, port))
        return original_resolve(host, port, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = resolve
    socket._ata_restricted = True
