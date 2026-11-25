import importlib.util
import ipaddress
import json
from pathlib import Path
import socket
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from rpi_assistant.app.config import ControlsConfig
from rpi_assistant.app.control_listener import ControlListeners, lan_addresses
from rpi_assistant.app.control_server import ControlServer

ROOT = Path(__file__).resolve().parents[1]


class ControlListenerTests(unittest.TestCase):
    def discover(self, devices, addresses):
        with patch('rpi_assistant.app.control_listener.subprocess.run') as run:
            run.side_effect = [SimpleNamespace(stdout=devices), SimpleNamespace(stdout=json.dumps(addresses))]
            result = lan_addresses()
            for call in run.call_args_list:
                self.assertEqual(call.kwargs['timeout'], 2)
            return result

    def test_only_connected_physical_private_addresses_without_internet_check(self):
        def address(name, ip, prefix=24):
            return {'ifname':name, 'addr_info':[{'local':ip, 'prefixlen':prefix, 'scope':'global'}]}
        result = self.discover('wlan0:wifi:connected:Home\\: network\neth0:ethernet:connected:wired\n'
                               'tun0:tun:connected:vpn\nwlan1:wifi:disconnected:--',
                               [address('wlan0','192.168.2.3'), address('eth0','203.0.113.5'),
                                address('tun0','10.0.0.1'), address('wlan1','192.168.4.1')])
        self.assertEqual(result, {'192.168.2.3':ipaddress.ip_network('192.168.2.0/24')})

    def test_hotspot_suppresses_even_concurrent_ethernet_and_custom_ap_address(self):
        result = self.discover('wlan0:wifi:connected:piwifi-hotspot\neth0:ethernet:connected:wired', [])
        self.assertEqual(result, {})

    def test_rebinding_revokes_existing_listener_then_closes_and_returns(self):
        manager = ControlListeners.__new__(ControlListeners)
        manager.config = ControlsConfig()
        manager.controls = Mock()
        manager.servers = {}
        networks = {'192.168.2.3':ipaddress.ip_network('192.168.2.0/24')}
        with patch('rpi_assistant.app.control_listener.ControlServer') as factory:
            factory.side_effect = lambda *args, **kw: Mock(allowed_network=kw['allowed_network'])
            manager._reconcile(networks)
            server = manager.servers['192.168.2.3']
            server.close.side_effect = lambda: self.assertIsNone(server.allowed_network)
            manager._reconcile({})  # Setup or a failed network-status query.
            server.close.assert_called_once()
            self.assertEqual(manager.servers, {})
            manager._reconcile(networks)
            self.assertEqual(factory.call_count, 2)

    def test_network_failure_closes_administration_and_keeps_retrying(self):
        manager = ControlListeners.__new__(ControlListeners)
        manager.servers, manager.last_problem = {}, None
        manager.stopping = Mock()
        manager.stopping.is_set.side_effect = [False, False, True]
        manager._targets = Mock(side_effect=[OSError('no nmcli'), {}])
        manager._reconcile = Mock()
        with patch('builtins.print'):
            manager._run()
        self.assertEqual(manager._reconcile.call_count, 3)
        self.assertTrue(all(call.args == ({},) for call in manager._reconcile.call_args_list))

    def test_port_conflict_does_not_escape_and_retries_until_port_is_free(self):
        blocker = socket.socket()
        blocker.bind(('127.0.0.1', 0)); blocker.listen()
        self.addCleanup(blocker.close)
        config = ControlsConfig(host='127.0.0.1', port=blocker.getsockname()[1])
        controls = Mock()
        controls.status.return_value = {'ready':True}
        controls.command.return_value = 'Stopped.'
        with patch('builtins.print') as log:
            manager = ControlListeners(config, controls)
            self.addCleanup(manager.close)
            deadline = time.monotonic()+3
            while manager.last_problem is None and time.monotonic()<deadline:
                time.sleep(.02)
            self.assertIn('port occupied', manager.last_problem)
            self.assertTrue(manager.thread.is_alive())
            blocker.close()
            deadline = time.monotonic()+7
            while not manager.servers and time.monotonic()<deadline:
                time.sleep(.02)
            self.assertIn('127.0.0.1', manager.servers)
            with urlopen(f'http://127.0.0.1:{config.port}/status', timeout=3) as response:
                self.assertEqual(json.load(response), {'ready':True})

    def test_http_subnet_revocation_host_and_origin_checks(self):
        controls = Mock()
        controls.status.return_value = {'ready':True}
        controls.command.return_value = 'Stopped.'
        server = ControlServer(SimpleNamespace(host='127.0.0.1', port=0), controls,
                               allowed_network=ipaddress.ip_network('127.0.0.0/8'))
        self.addCleanup(server.close)
        url = f'http://127.0.0.1:{server.server_port}'
        with urlopen(url, timeout=3) as response:
            self.assertEqual(response.status, 200)
        for headers in ({'Host':'192.168.4.1'}, {'Host':'evil.example'}):
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url, headers=headers), timeout=3)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
        for headers in ({}, {'X-Assistant-Control':'1', 'Origin':'http://192.168.4.1'}):
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url+'/control', data=b'{"action":"stop"}', headers=headers), timeout=3)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
        with urlopen(Request(url+'/control', data=b'{"action":"stop"}',
                             headers={'X-Assistant-Control':'1', 'Origin':url}), timeout=3):
            pass
        controls.command.assert_called_once_with('stop', None)
        for network in (ipaddress.ip_network('192.168.11.0/24'), None):
            server.allowed_network = network
            with self.assertRaises(HTTPError) as error:
                urlopen(url+'/status', timeout=3)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()


class ServiceInstallerTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('installer', ROOT/'scripts/install-control-service.py')
        self.installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.installer)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root/'project'
        (self.project/'systemd').mkdir(parents=True)
        (self.project/'rpi_assistant').mkdir()
        (self.project/'systemd/rpi-assistant.service').write_text((ROOT/'systemd/rpi-assistant.service').read_text())
        self.unit = self.root/'etc/systemd/system/rpi-assistant.service'
        self.unit.parent.mkdir(parents=True)
        self.unit.write_text('[Service]\nUser=maker\nExecStart=/old/python\n')
        self.config = self.project/'rpi_assistant/config.ini'
        self.original = '# Preserve comments\n[controls]\nhost = 0.0.0.0\nport = 8767\nenabled = false\n[openai]\napi_key = synthetic-only\n'
        self.config.write_text(self.original)

    def test_upgrade_is_private_idempotent_and_preserves_user_and_other_settings(self):
        backup = self.installer.install(self.project, Path('/opt/test/bin/python'), root=self.root)
        self.assertIn('host = lan\nport = 80', self.config.read_text())
        self.assertIn('enabled = false', self.config.read_text())
        self.assertIn('# Preserve comments', self.config.read_text())
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual((backup/'1-config.ini').read_text(), self.original)
        unit = self.unit.read_text()
        self.assertIn('User=maker', unit)
        self.assertIn('AmbientCapabilities=CAP_NET_BIND_SERVICE', unit)
        before = self.config.read_text()
        self.installer.install(self.project, Path('/opt/test/bin/python'), root=self.root)
        self.assertEqual(self.config.read_text(), before)

    def test_custom_host_port_and_loopback_preference_survive(self):
        text = '[controls]\nhost=127.0.0.1\nport=9999\n'
        self.assertEqual(self.installer.migrate_config(text), text)

    def test_bad_config_does_not_change_service_and_write_failure_restores_it(self):
        original_unit = self.unit.read_text()
        self.config.write_text('[controls]\n[controls]\n')
        with self.assertRaises(Exception):
            self.installer.install(self.project, Path('/opt/test/bin/python'), root=self.root)
        self.assertEqual(self.unit.read_text(), original_unit)
        self.config.write_text(self.original)
        original_replace = Path.replace
        def failing_replace(path, destination):
            if destination == self.config:
                raise OSError('synthetic write failure')
            return original_replace(path, destination)
        with patch.object(Path, 'replace', failing_replace):
            with self.assertRaises(OSError):
                self.installer.install(self.project, Path('/opt/test/bin/python'), root=self.root)
        self.assertEqual(self.unit.read_text(), original_unit)
        self.assertEqual(self.config.read_text(), self.original)


if __name__ == '__main__':
    unittest.main()
