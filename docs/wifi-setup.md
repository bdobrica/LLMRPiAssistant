# Take your assistant to another Wi-Fi network

The optional Wi-Fi setup lets you connect the Pi using your phone when none of its
saved networks are available. You enter the device code once, as the setup Wi-Fi
password. There is no second browser login.

## Install it before you travel

After the assistant is installed, run these in the Pi terminal from the repository:

```sh
make install-wifi
sudo piwifi-setup-code
```

Privately save the displayed setup network name and code, for example on a device
label. Each device gets its own code; updates preserve it. Then start the manager:

```sh
sudo systemctl restart piwifi-manager.service
```

If you lose the code, the same `sudo piwifi-setup-code` command shows it again over
SSH or a connected keyboard/screen. Don't share codes or home Wi-Fi passwords in
issues. Restarting the manager doesn't force setup mode if saved Wi-Fi works.

## Connect from your phone

1. When the Pi cannot join saved Wi-Fi, find its `PiAssistant-Setup-…` network.
2. Join with the device code. Stay connected if your phone says “no Internet.”
3. Open **http://192.168.4.1** in your browser.
4. Select your network, or choose **Enter another network…** and type its name.
5. Enter its password. **Show Wi-Fi password** lets you check your typing.
6. Choose **Save & connect**. Setup disconnects while the Pi joins Wi-Fi.
7. Reconnect your phone to that Wi-Fi. Use the Pi's new IP address for its
   [normal controls page](phone-setup.md).

![Wi-Fi setup page with example networks](images/wifi-setup.png)

## If joining fails

Reconnect to the setup network, refresh the page and retry. A stale form may need
refreshing. If the phone saved an old setup password, forget that network and join
again with the current code. Previously working Wi-Fi profiles are preserved.

Use a compatible 2.4 GHz network on the Zero 2 W. The setup supports open and
WPA/WPA2 personal networks. Enterprise sign-in, hidden-network discovery and
WPA3-only networks aren't supported by this flow. For an event, a private router
is easier to control than venue Wi-Fi; normal phone controls have no login.

## What the setup code protects

Anyone with the device code can change Wi-Fi setup. The page is restricted to the
protected setup hotspot and closes after a successful Wi-Fi join, even when that
network has no Internet. An Internet outage alone does not reopen setup.

The private code is stored in `/etc/piwifi/setup.json`; don't copy it between devices.
Network/timing settings live in `/etc/default/piwifi`. Passwords are saved privately
by NetworkManager, not returned on the page or included in command-error messages.
Installation snapshots live under `/var/backups/piwifi/`; keep those private too.

[Back to the guides](README.md)
