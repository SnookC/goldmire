"""
Goldmire on your phone, from anywhere, through Tailscale.

Tailscale links your PC and your phone into a small private network that only
your own devices can join. This script asks Tailscale to share the Goldmire town
page (which the bot serves on this PC only) with those devices, over HTTPS.
Nobody else on the internet can reach it, and your Alpaca keys are never shared.

Run it once (4_phone_access.bat). The sharing keeps working after restarts.
To stop sharing:  4_phone_access.bat stop
"""

import json
import os
import shutil
import subprocess
import sys
import webbrowser

PORT = 8777                      # must match WORLD_PORT in bot.py
TARGET = f"http://127.0.0.1:{PORT}"
HERE = os.path.dirname(os.path.abspath(__file__))
LINK_FILE = os.path.join(HERE, "phone_link.txt")
PAGE_FILE = os.path.join(HERE, "phone_link.html")


def say(msg=""):
    print(msg, flush=True)


def find_tailscale():
    exe = shutil.which("tailscale")
    if exe:
        return exe
    for p in (r"C:\Program Files\Tailscale\tailscale.exe", r"C:\Program Files (x86)\Tailscale\tailscale.exe",
              "/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        if os.path.exists(p):
            return p
    return None


def tailscale_status(ts):
    r = subprocess.run([ts, "status", "--json"], capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {}


def qr_page(url):
    """A small page with a QR code your phone camera can scan, plus the link and how to add the icon."""
    svg = ""
    try:
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
        svg = img.to_string(encoding="unicode")
    except Exception:
        pass
    html = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Goldmire on your phone</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;background:#0c120e;color:#efe6cf;margin:0;padding:24px;display:grid;justify-items:center;gap:14px}}
h1{{font-family:Georgia,serif;color:#f7dc95;margin:0}} .qr{{background:#fff;padding:14px;border-radius:12px;width:min(320px,80vw)}} .qr svg{{width:100%;height:auto;display:block}}
a{{color:#f7dc95;word-break:break-all}} ol{{max-width:520px}} .note{{color:#a9ae97;max-width:520px;font-size:14px}}</style>
<h1>Goldmire on your phone</h1>
<p>1. Make sure the <b>Tailscale</b> app on your phone is signed in to the same account as this PC.</p>
<div class="qr">{svg or "(QR code unavailable: type the link below into your phone)"}</div>
<p>2. Point your phone's camera at the code, or open: <a href="{url}">{url}</a></p>
<ol><li><b>iPhone (Safari):</b> tap the Share button, then <b>Add to Home Screen</b>, then <b>Add</b>.</li>
<li><b>Android (Chrome):</b> tap the ⋮ menu, then <b>Add to Home screen</b> (or <b>Install app</b>), then <b>Install</b>.</li></ol>
<p class="note">Your PC has to be on with Goldmire running for live numbers. If it isn't, the app shows the last report it got.</p>"""
    with open(PAGE_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def start():
    ts = find_tailscale()
    if not ts:
        say("Tailscale isn't installed on this PC yet.")
        say("  1. Go to https://tailscale.com/download and install it for Windows.")
        say("  2. Sign in (a free personal account is fine).")
        say("  3. Install the Tailscale app on your phone and sign in with the SAME account.")
        say("  4. Then run this again.")
        return 1
    st = tailscale_status(ts)
    if st.get("BackendState") != "Running":
        say("Tailscale is installed but not connected.")
        say("Open Tailscale (bottom-right of the taskbar, near the clock), sign in / Connect, then run this again.")
        return 1
    dns = (st.get("Self") or {}).get("DNSName", "").rstrip(".")
    if not dns:
        say("Tailscale didn't report this PC's name. Make sure MagicDNS is on (Tailscale admin console > DNS), then run this again.")
        return 1
    say("Asking Tailscale to share Goldmire with your devices (private, HTTPS)...")
    say("If Tailscale prints a link asking you to enable something, open it, click Enable, and come back here.")
    say()
    r = subprocess.run([ts, "serve", "--bg", "--https=443", TARGET])
    if r.returncode != 0:
        say()
        say("Tailscale couldn't turn on sharing (see the message above). Fix that, then run this again.")
        return 1
    url = f"https://{dns}/world.html"
    with open(LINK_FILE, "w", encoding="utf-8") as f:
        f.write(url + "\n")
    qr_page(url)
    say()
    say("=" * 64)
    say(" SUCCESS - Goldmire is shared with your own devices only.")
    say(f" Phone link:  {url}")
    say("=" * 64)
    try:
        import qrcode
        q = qrcode.QRCode(border=1)
        q.add_data(url)
        q.print_ascii(invert=True)
    except Exception:
        pass
    say("A page with a QR code for your phone just opened in your browser.")
    say("Keep Goldmire running on this PC (the Goldmire icon) so the app has live numbers.")
    webbrowser.open("file:///" + PAGE_FILE.replace("\\", "/"))
    return 0


def stop():
    ts = find_tailscale()
    if not ts:
        say("Tailscale isn't installed, so nothing is being shared.")
        return 0
    subprocess.run([ts, "serve", "--https=443", TARGET, "off"])
    for p in (LINK_FILE, PAGE_FILE):
        if os.path.exists(p):
            os.remove(p)
    say("Stopped sharing Goldmire with your phone.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(stop() if "stop" in sys.argv[1:] else start())
