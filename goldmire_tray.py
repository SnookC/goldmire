"""
Goldmire without the black window.

Runs the bots quietly in the background and puts a Goldmire icon in the system
tray (by the clock, sometimes behind the ^ arrow).
  * Click the icon            -> opens the Goldmire town
  * Right-click the icon      -> Open Goldmire / Show the log / Update / Stop Goldmire
Everything the bots do still goes into bot_log.txt.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import webbrowser

# Started with pythonw.exe there is no console: give print/logging somewhere harmless to write.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

import bot  # noqa: E402

TOWN = f"http://localhost:{bot.WORLD_PORT}/world.html"


def popup(text, error=True):
    """A plain Windows message box (there is no console window to print to)."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Goldmire", 0x10 if error else 0x40)
    except Exception:
        print(text)


class _LastError(logging.Handler):
    """Remembers the last error the bots logged, to show it if Goldmire can't start."""
    def __init__(self):
        super().__init__(logging.ERROR)
        self.text = ""

    def emit(self, record):
        self.text = record.getMessage()


def tooltip():
    try:
        with open(bot.STATUS_FILE, encoding="utf-8") as f:
            s = json.load(f)
        pl = float(s.get("total_pl", 0))
        return f"Goldmire - heroes {'-' if pl < 0 else '+'}${abs(pl):,.2f}"
    except Exception:
        return "Goldmire - running"


def restart():
    """Starts the freshly updated Goldmire (a new tray icon), quietly."""
    args = [sys.executable, os.path.join(HERE, "goldmire_tray.py"), "--no-browser", "--updated"]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(args, cwd=HERE, creationflags=flags, close_fds=True)


def main():
    last = _LastError()
    logging.getLogger("bot").addHandler(last)
    done = threading.Event()
    outcome = {}

    def run_bots():
        try:
            bot.main()
        except SystemExit as e:
            outcome.update(kind="exit", code=e.code, msg=last.text)
        except Exception as e:  # noqa: BLE001 - anything unexpected must reach the user, not vanish
            bot.log.exception("Goldmire stopped because of an error")
            outcome.update(kind="crash", msg=f"{type(e).__name__}: {e}")
        finally:
            done.set()

    worker = threading.Thread(target=run_bots, name="goldmire-bots", daemon=True)
    worker.start()

    try:
        import pystray
        from PIL import Image
    except ImportError:
        if done.wait(4):
            return report(outcome)
        popup("Goldmire is running in the background, but its tray icon couldn't load.\n\n"
              "Run 1_setup.bat in the Goldmire folder to finish installing, then start Goldmire again.", error=False)
        done.wait()
        if bot.RESTART.is_set():
            restart()
            return 0
        return report(outcome)

    def open_town(icon=None, item=None):
        webbrowser.open(TOWN)

    def open_log(icon=None, item=None):
        try:
            os.startfile(bot.LOG_FILE)
        except Exception:
            pass

    def stop(icon, item):
        bot.STOP.set()
        icon.stop()

    def update_label(item):
        a = bot.UPDATE.get("available")
        if bot.UPDATE.get("state") in ("installing", "restarting"):
            return "Updating Goldmire..."
        return f"Update to version {a['version']}" if a else "Update"

    def update_now(icon, item):
        ok, msg = bot.start_update()
        try:
            icon.notify(msg + (" Goldmire will restart by itself." if ok else ""), "Goldmire")
        except Exception:
            pass

    image = Image.open(os.path.join(HERE, "world", "icon-192.png"))
    icon = pystray.Icon("Goldmire", image, "Goldmire - starting", menu=pystray.Menu(
        pystray.MenuItem("Open Goldmire", open_town, default=True),
        pystray.MenuItem("Show the log", open_log),
        pystray.MenuItem(update_label, update_now, visible=lambda item: bool(bot.UPDATE.get("available"))),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Stop Goldmire", stop),
    ))

    def watch(icon):
        icon.visible = True
        if done.wait(4):            # failed straight away (keys missing, already running, no internet...)
            icon.stop()
            return
        try:
            if "--updated" in sys.argv:
                icon.notify(f"Goldmire is updated to version {bot.updater.current_version()} and running again.", "Goldmire")
            else:
                icon.notify("Goldmire is running in the background. Click this icon to open the town; "
                            "right-click it to stop Goldmire.", "Goldmire")
        except Exception:
            pass
        icon.title = tooltip()
        shown = None
        while not done.wait(20):
            icon.title = tooltip()
            now = (bot.UPDATE.get("available") or {}).get("version"), bot.UPDATE.get("state")
            if now != shown:            # show or hide the Update item
                shown = now
                try:
                    icon.update_menu()
                except Exception:
                    pass
        icon.stop()                 # the bots stopped on their own: don't leave a misleading icon behind

    icon.run(setup=watch)
    bot.STOP.set()
    worker.join(timeout=20)
    if bot.RESTART.is_set():
        restart()
        return 0
    return report(outcome)


def report(outcome):
    kind = outcome.get("kind")
    if kind == "exit" and outcome.get("code") == 2:
        webbrowser.open(TOWN)
        popup("Goldmire is already running.\n\nLook for its icon by the clock (it may be behind the ^ arrow).", error=False)
    elif kind == "exit" and outcome.get("code"):
        popup(f"Goldmire couldn't start:\n\n{outcome.get('msg') or 'See bot_log.txt for details.'}\n\n"
              "Fix that, then start Goldmire again.")
    elif kind == "crash":
        popup(f"Goldmire stopped because of an error:\n\n{outcome.get('msg')}\n\n"
              "Check the internet connection, then start Goldmire again. Details are in bot_log.txt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
