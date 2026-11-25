"""Small LAN listener supervisor; no proxy, root process, or Internet probes."""

from dataclasses import replace
import errno
import ipaddress
import json
import os
import subprocess
import threading

from .control_server import ControlServer
from ..piwifi.network import fields, HOTSPOT

PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def lan_addresses():
    """Return connected physical IPv4 addresses and their directly attached subnets.

    Fail closed when NetworkManager cannot confirm the network. The setup profile
    suppresses administration on *all* interfaces, including concurrent Ethernet.
    No SSIDs, command output or credentials are logged.
    """
    def run(args):
        return subprocess.run(args, check=True, capture_output=True, text=True,
                              timeout=2, env={**os.environ, "LC_ALL": "C"}).stdout
    devices = [fields(line) for line in run(
        ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"]).splitlines()]
    if any(len(row) == 4 and row[3] == HOTSPOT for row in devices):
        return {}
    interfaces = {row[0] for row in devices if len(row) == 4
                  and row[1] in ("wifi", "ethernet") and row[2] == "connected"}
    result = {}
    for device in json.loads(run(["ip", "-j", "-4", "address", "show"])):
        if device["ifname"] not in interfaces:
            continue
        for item in device.get("addr_info", []):
            if item.get("scope") != "global":
                continue
            address = ipaddress.ip_interface(f"{item['local']}/{item['prefixlen']}")
            if (any(address.ip in network for network in PRIVATE_NETWORKS)
                    and address.network.prefixlen >= 8):
                result[str(address.ip)] = address.network
    return result


class ControlListeners:
    """Rebind after DHCP/setup changes and retry failures without stopping voice."""

    def __init__(self, config, controls):
        self.config, self.controls = config, controls
        self.servers = {}
        self.stopping = threading.Event()
        self.last_problem = None
        self.thread = threading.Thread(target=self._run, name="control-listeners", daemon=True)
        self.thread.start()

    def _targets(self):
        if self.config.host == "127.0.0.1":
            return {"127.0.0.1": ipaddress.ip_network("127.0.0.0/8")}
        addresses = lan_addresses()
        if self.config.host in ("lan", "0.0.0.0"):
            return addresses
        return {host: network for host, network in addresses.items() if host == self.config.host}

    def _reconcile(self, targets):
        # Revoke admission before closing, including on still-open HTTP connections.
        for host in list(self.servers):
            server = self.servers[host]
            if host not in targets or server.allowed_network != targets[host]:
                server.allowed_network = None
                server.close()
                del self.servers[host]
        for host, network in targets.items():
            if host not in self.servers:
                server = ControlServer(replace(self.config, host=host), self.controls,
                                       allowed_network=network)
                self.servers[host] = server
                port = "" if server.server_port == 80 else f":{server.server_port}"
                print(f"Phone controls ready at http://{host}{port}/", flush=True)

    def _run(self):
        try:
            while not self.stopping.is_set():
                try:
                    targets = self._targets()
                except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
                    targets = {}
                    self._problem("Network status unavailable; phone controls closed. Check NetworkManager.")
                else:
                    if not targets:
                        self._problem("Phone controls waiting for a private LAN; unavailable during Wi-Fi setup.")
                try:
                    self._reconcile(targets)
                    if targets:
                        self.last_problem = None
                except OSError as exc:
                    detail = ("port occupied; check ss -ltnp" if exc.errno == errno.EADDRINUSE else
                              "permission denied; reinstall the systemd service" if exc.errno in (errno.EACCES, errno.EPERM) else
                              "address unavailable; check network and controls configuration")
                    self._problem(f"Phone controls unavailable ({detail}); retrying. Voice remains available.")
                self.stopping.wait(5)
        finally:
            self._reconcile({})

    def _problem(self, message):
        if message != self.last_problem:
            print(message, flush=True)
            self.last_problem = message

    def close(self):
        self.stopping.set()
        self.thread.join(timeout=12)
