import os
import subprocess
import time
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

IFACE = os.environ.get("IFACE", "wlan0")


def run(cmd: list[str], check: bool = True) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(
            f"Command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout}"
        )
    return p.stdout.strip()


def wifi_state() -> str:
    try:
        return run(["nmcli", "-t", "-f", "WIFI", "g"], check=False)
    except Exception as e:
        return f"error: {e}"


def active_conn() -> list[str]:
    out = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev"], check=False)
    lines: list[str] = []
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 4 and parts[0] == IFACE:
            lines.append(line)
    return lines or ["(none)"]


def scan_ssids() -> list[str]:
    run(["nmcli", "dev", "wifi", "rescan"], check=False)
    out = run(
        ["nmcli", "-t", "-f", "SSID,SECURITY,SIGNAL", "dev", "wifi", "list", "ifname", IFACE],
        check=False,
    )
    ssids: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        ssid = line.split(":")[0]
        if ssid and ssid not in ssids:
            ssids.append(ssid)
    return ssids


def saved_wifi_profiles() -> list[str]:
    out = run(["nmcli", "-t", "-f", "NAME,TYPE", "con", "show"], check=False)
    names: list[str] = []
    for line in out.splitlines():
        if line.endswith(":wifi"):
            names.append(line.split(":")[0])
    return names


def create_app() -> Flask:
    # Ensure templates are found when running as module
    pkg_dir = Path(__file__).resolve().parent
    templates_dir = pkg_dir / "templates"
    app = Flask(__name__, template_folder=str(templates_dir))

    @app.get("/")
    def index():
        ssids = scan_ssids()
        return render_template(
            "index.html",
            iface=IFACE,
            wifi_state=wifi_state(),
            active=active_conn(),
            ssids=ssids if ssids else ["(no networks found)"],
            saved=saved_wifi_profiles(),
        )

    @app.post("/connect")
    def connect():
        ssid = request.form.get("ssid", "").strip()
        password = request.form.get("password", "")

        if not ssid or ssid == "(no networks found)":
            return redirect(url_for("index"))

        # Stop hotspot; manager will also do this, but it helps.
        run(["nmcli", "con", "down", "piwifi-hotspot"], check=False)

        con_name = ssid

        existing = saved_wifi_profiles()
        if con_name not in existing:
            run(
                ["nmcli", "con", "add", "type", "wifi", "ifname", IFACE, "con-name", con_name, "ssid", ssid],
                check=True,
            )

        if password:
            run(["nmcli", "con", "modify", con_name, "wifi-sec.key-mgmt", "wpa-psk"], check=True)
            run(["nmcli", "con", "modify", con_name, "wifi-sec.psk", password], check=True)
        else:
            run(["nmcli", "con", "modify", con_name, "wifi-sec.key-mgmt", ""], check=False)

        run(["nmcli", "con", "modify", con_name, "connection.autoconnect", "yes"], check=False)
        run(["nmcli", "con", "up", con_name], check=False)

        time.sleep(2)
        return redirect(url_for("index"))

    return app


def main() -> None:
    port = int(os.environ.get("FLASK_PORT", "8080"))
    app = create_app()
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()