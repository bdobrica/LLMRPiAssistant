from contextlib import redirect_stderr, redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rpi_assistant.piwifi import credentials, network, webapp


SECRET = 'SYNTHETIC_WIFI_SECRET_794'
ROOT = Path(__file__).resolve().parents[1]


class FakeJob:
    busy = False
    message = ''

    def __init__(self): self.calls = []
    def start(self, ssid, password):
        network.validate(ssid, password)
        self.calls.append((ssid, password))
        self.busy = True


class WiFiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.code = credentials.initialize(self.root/'private/setup.json')
        self.job = FakeJob()
        self.app = webapp.create_app(host='localhost', setup_network='127.0.0.0/8', job=self.job)
        self.client = self.app.test_client()
        self.scan = patch.object(network, 'scan', return_value=['home', 'colon: network', '<b>escaped</b>'])
        self.scan.start(); self.addCleanup(self.scan.stop)

    def token(self):
        page = self.client.get('/')
        return re.search(r'name="csrf" value="([a-f0-9]+)"', page.text)[1]

    def form(self):
        return self.token()

    def test_device_codes_are_private_unique_stable_and_fail_closed(self):
        path = self.root/'private/setup.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(credentials.initialize(path), self.code)
        self.assertNotEqual(credentials.initialize(self.root/'other.json')['code'], self.code['code'])
        path.chmod(0o644)
        with self.assertRaises(ValueError): credentials.load(path)
        link = self.root/'link'; link.symlink_to(path)
        with self.assertRaises(OSError): credentials.load(link)

    def test_protected_network_is_the_only_login_and_changes_require_csrf_and_same_origin(self):
        token = self.token()
        self.assertIn('Join your Wi-Fi', self.client.get('/').text)
        self.assertNotIn('Unlock', self.client.get('/').text)
        self.assertEqual(self.client.get('/',environ_overrides={'REMOTE_ADDR':'192.168.11.2'}).status_code,403)
        self.assertEqual(self.client.post('/connect', data={'ssid':'home','password':SECRET}).status_code,403)
        data={'csrf':token, 'ssid':'home', 'password':SECRET}
        self.assertEqual(self.client.post('/connect',data={**data,'csrf':'0'*64}).status_code,403)
        self.assertEqual(self.client.post('/connect',data=data,headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)
        self.assertEqual(self.client.post('/connect',data=data,headers={'Origin':'http://evil.invalid'}).status_code,403)
        self.assertEqual(self.client.post('/connect',data=data,headers={'Origin':'null'}).status_code,403)
        self.assertFalse(self.job.calls)
        response = self.client.post('/connect',data=data,headers={'Origin':'http://localhost'})
        self.assertEqual(response.status_code,202)
        self.assertEqual(self.job.calls,[('home',SECRET)])
        self.assertNotIn(SECRET,response.text)
        self.assertNotIn(self.code['code'],response.text)

    def test_no_secret_echo_or_traceback_on_network_failure(self):
        token = self.form()
        output=io.StringIO()
        with patch.object(self.job,'start',side_effect=RuntimeError(SECRET)), redirect_stdout(output), redirect_stderr(output):
            response=self.client.post('/connect',data={'csrf':token,'ssid':'home','password':SECRET})
        self.assertEqual(response.status_code,503)
        self.assertNotIn(SECRET,response.text+output.getvalue())
        with patch('rpi_assistant.piwifi.network.subprocess.run',return_value=subprocess.CompletedProcess(['nmcli',SECRET],10,SECRET,SECRET)):
            with self.assertRaises(network.NetworkError) as caught: network.run(['test',SECRET])
        self.assertNotIn(SECRET,str(caught.exception))
        with patch('rpi_assistant.piwifi.network.subprocess.run',side_effect=subprocess.TimeoutExpired(['nmcli',SECRET],1,SECRET)):
            with self.assertRaises(network.NetworkError) as caught: network.run(['test',SECRET])
        self.assertNotIn(SECRET,str(caught.exception))

    def test_malformed_inputs_and_secret_urls_never_start_a_join(self):
        token=self.form()
        for ssid,password in [('',SECRET),('x'*33,SECRET),('é'*17,SECRET),('bad\nssid',SECRET),('home','short'),('home','bad\npassword')]:
            response=self.client.post('/connect',data={'csrf':token,'ssid':ssid,'password':password})
            self.assertEqual(response.status_code,400)
            self.assertNotIn(SECRET,response.text)
        self.assertEqual(self.client.post('/connect',data={'csrf':token,'ssid':'home','password':SECRET,'extra':'x'}).status_code,400)
        self.assertEqual(self.client.post('/connect',data='x'*5000,content_type='application/x-www-form-urlencoded').status_code,413)
        self.assertEqual(self.client.get('/?password='+SECRET).status_code,400)
        self.assertEqual(self.client.get('/',headers={'Host':'evil.invalid'}).status_code,400)
        self.assertFalse(self.job.calls)
        self.assertEqual(network.fields(r'colon\:slash\\name:field'),['colon:slash\\name','field'])

    def test_expired_and_previous_process_forms_require_refresh(self):
        token=self.form()
        page=self.client.get('/')
        self.assertIn('&lt;b&gt;escaped&lt;/b&gt;',page.text)
        cookie=self.client.get_cookie('piwifi_setup')
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site,'Strict')
        data={'csrf':token,'ssid':'home','password':SECRET}
        with patch('itsdangerous.timed.time.time',return_value=__import__('time').time()+901):
            response=self.client.post('/connect',data=data)
            self.assertEqual(response.status_code,403)
            self.assertIn('Refresh',response.text)
        other=webapp.create_app(host='localhost',setup_network='127.0.0.0/8',job=self.job).test_client()
        other.set_cookie('piwifi_setup',cookie.value)
        self.assertEqual(other.post('/connect',data=data).status_code,403)
        self.assertFalse(self.job.calls)
        # The policy must preserve Origin for same-origin HTML form submissions.
        self.assertEqual(page.headers['Referrer-Policy'],'same-origin')

    def test_private_profile_keeps_password_out_of_process_args(self):
        template='[connection]\nid=test\nuuid=00000000-0000-0000-0000-000000000001\ntype=wifi\nautoconnect=false\n[wifi]\nssid=home\n[ipv4]\nmethod=auto\n'
        with patch.object(network,'run',side_effect=[template,'']) as run:
            identifier,path=network.create_profile('home',SECRET,'wlan0',directory=self.root)
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        self.assertIn(SECRET,path.read_text())
        self.assertNotIn(SECRET,repr(run.call_args_list))
        self.assertIn('autoconnect=false',path.read_text())
        self.scan.stop()
        with patch('rpi_assistant.piwifi.network.subprocess.run',return_value=subprocess.CompletedProcess([],0,'  home  \n','')):
            self.assertEqual(network.scan('wlan0'),['  home  '])

    def test_failed_join_removes_only_candidate_and_restores_setup(self):
        path=self.root/'candidate';path.write_text(SECRET)
        preserved=self.root/'existing';preserved.write_text('keep')
        with patch.object(network,'create_profile',return_value=('candidate-id',path)), patch.object(network,'run',side_effect=[network.NetworkError(SECRET),'']) as run:
            with self.assertRaises(network.NetworkError) as caught: network.connect('home',SECRET,'wlan0')
        self.assertNotIn(SECRET,str(caught.exception))
        self.assertFalse(path.exists());self.assertEqual(preserved.read_text(),'keep')
        self.assertEqual(run.call_args_list[-1].args[0],['connection','delete','uuid','candidate-id'])
        job=webapp.ConnectionJob('wlan0',self.root/'connecting')
        job.marker.write_text('123');job.busy=True
        with patch.object(network,'connect',side_effect=network.NetworkError(SECRET)), patch.object(network,'client_connected',return_value=False), patch.object(network,'run') as run, patch.object(webapp.time,'sleep'):
            job._connect('home',SECRET)
        self.assertFalse(job.busy);self.assertFalse(job.marker.exists())
        self.assertNotIn(SECRET,job.message)
        run.assert_called_once_with(['connection','up','id',network.HOTSPOT])

    def test_connection_is_acknowledged_only_after_worker_setup_and_duplicate_is_refused(self):
        job=webapp.ConnectionJob('wlan0',self.root/'connecting')
        with patch.object(webapp.threading,'Thread') as thread:
            job.start('home',SECRET)
            self.assertTrue(job.busy)
            self.assertEqual(job.marker.stat().st_mode & 0o777,0o600)
            thread.return_value.start.assert_called_once()
            with self.assertRaises(ValueError):job.start('home',SECRET)
        job.busy=False;job.marker.unlink()
        with patch.object(webapp.threading,'Thread') as thread:
            thread.return_value.start.side_effect=RuntimeError()
            with self.assertRaises(RuntimeError):job.start('home',SECRET)
        self.assertFalse(job.busy);self.assertFalse(job.marker.exists())

    def test_installer_preserves_code_and_private_backup_removes_legacy_password_fields(self):
        spec=spec_from_file_location('configure_piwifi',ROOT/'scripts/configure-piwifi.py')
        module=module_from_spec(spec);spec.loader.exec_module(module)
        old=self.root/'etc/default/piwifi';old.parent.mkdir(parents=True)
        old.write_text('AP_PASSWORD='+SECRET+'\nAP_SSID=OwnerSetup\nAP_NO_CLIENT_TIMEOUT=30\nFLASK_PORT=8080\n')
        backup=module.configure(ROOT,Path('/opt/venvs/rpi-assistant'),root=self.root,environment={})
        self.assertEqual(backup.stat().st_mode & 0o777,0o700)
        self.assertIn(SECRET,(backup/'etc/default/piwifi').read_text())
        self.assertNotIn(SECRET,old.read_text())
        self.assertEqual(old.stat().st_mode & 0o777,0o600)
        self.assertIn('OwnerSetup',old.read_text())
        self.assertIn('FLASK_PORT="80"',old.read_text())
        code=credentials.load(self.root/'etc/piwifi/setup.json')
        module.configure(ROOT,Path('/opt/venvs/rpi-assistant'),root=self.root,environment={})
        self.assertEqual(code,credentials.load(self.root/'etc/piwifi/setup.json'))
        before=old.read_text()
        with patch.object(module.os,'fsync',side_effect=OSError()):
            with self.assertRaises(OSError):module.configure(ROOT,Path('/opt/venvs/rpi-assistant'),root=self.root,environment={'AP_SSID':'changed'})
        self.assertEqual(old.read_text(),before)

    def test_manager_closes_ui_without_internet_and_counts_actual_clients(self):
        script='''source scripts/piwifi-manager.sh
nmcli() {
 case "$*" in
  '-g GENERAL.STATE device show wlan0') echo '100 (connected)';;
  '-g GENERAL.CONNECTION device show wlan0') echo 'home';;
 esac
}
systemctl() { printf '%s\\n' "$*"; }
is_connected || exit 2
stop_hotspot
iw() { echo 'Station 00:11:22:33:44:55'; }
has_hotspot_clients || exit 3
iw() { return 0; }
if has_hotspot_clients; then exit 4; fi
'''
        result=subprocess.run(['bash','-c',script],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        manager=(ROOT/'scripts/piwifi-manager.sh').read_text()
        self.assertNotIn('AP_PASSWORD',manager)
        self.assertNotIn('internet_ok',manager)
        self.assertNotIn('Wants=NetworkManager.service piwifi-flask.service',(ROOT/'systemd/piwifi-manager.service').read_text())


if __name__ == '__main__': unittest.main()
