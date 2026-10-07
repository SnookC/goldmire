"""
Goldmire updates.

Goldmire checks for a newer version now and then. When one is out, an
"Update ready" button appears in the town (and in the tray icon's menu).
Pressing it:
  1. downloads the new version,
  2. checks every file in it before touching anything,
  3. installs any new Python packages it needs,
  4. backs up the files it is about to replace (in the "backups" folder),
  5. swaps the files in, and puts the old ones back if anything goes wrong,
  6. restarts Goldmire.

Never touched by an update: your Alpaca keys (.env), your heroes (bots.json),
their gold, savings and levels (bot_state.json), the log, and your phone link.

Where updates come from is set in update.json:
  {"repo": "your-github-name/goldmire", "branch": "main"}
An empty "repo" means updates are switched off.
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(HERE, "version.json")
SOURCE_FILE = os.path.join(HERE, "update.json")
BACKUP_DIR = os.path.join(HERE, "backups")
KEEP_BACKUPS = 3
TIMEOUT = 30

# Yours, never replaced by an update.
PROTECTED = {".env", "bots.json", "bot_state.json", "bot_log.txt", "phone_link.txt", "phone_link.html",
             "goldmire.pid", "world/status.json"}
SKIP_DIRS = {".venv", "backups", ".git", "__pycache__", ".github"}
# An update must contain these, or it is not a real Goldmire.
REQUIRED = ("bot.py", "goldmire_tray.py", "updater.py", "version.json", "requirements.txt", "world/world.html")


class UpdateError(Exception):
    pass


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def current_version():
    return str(_read_json(VERSION_FILE, {}).get("version", "0.0.0"))


def vtuple(v):
    out = []
    for part in str(v).strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple((out + [0, 0, 0])[:3])


def source():
    """Where to look: {'version_url', 'zip_url', 'label'} or None when updates are switched off."""
    cfg = _read_json(SOURCE_FILE, {})
    base = (cfg.get("base_url") or "").rstrip("/")           # used for testing
    if base:
        return {"version_url": f"{base}/version.json", "zip_url": f"{base}/goldmire.zip", "label": base}
    repo = (cfg.get("repo") or "").strip().strip("/")
    if repo.count("/") != 1:
        return None
    branch = (cfg.get("branch") or "main").strip()
    return {"version_url": f"https://raw.githubusercontent.com/{repo}/{branch}/version.json",
            "zip_url": f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}",
            "label": f"github.com/{repo}"}


def _get(url, limit=50 * 1024 * 1024):
    req = urllib.request.Request(url, headers={"User-Agent": "Goldmire-updater", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("the download is far bigger than a Goldmire update should be")
    return data


def check():
    """Returns {'version', 'notes'} if a newer version is out, else None. Raises UpdateError if it can't look."""
    src = source()
    if not src:
        return None
    try:
        info = json.loads(_get(src["version_url"] + f"?t={int(time.time())}", 64 * 1024).decode("utf-8"))
    except UpdateError:
        raise
    except Exception as e:  # noqa: BLE001 - no internet, GitHub down, file missing...
        raise UpdateError(f"couldn't check for updates ({type(e).__name__}: {e})") from e
    latest = str(info.get("version", ""))
    if not latest or vtuple(latest) <= vtuple(current_version()):
        return None
    notes = info.get("notes") or []
    return {"version": latest, "notes": [str(n) for n in notes][:12] if isinstance(notes, list) else [str(notes)]}


# ---------------------------------------------------------------------------
# installing
# ---------------------------------------------------------------------------
def _norm(rel):
    return rel.replace("\\", "/").lstrip("/")


def _wanted(rel):
    rel = _norm(rel)
    parts = rel.split("/")
    return rel not in PROTECTED and not any(p in SKIP_DIRS for p in parts[:-1]) and not rel.endswith((".pyc", ".tmp"))


def _unpack(blob, dest):
    """Unzips safely and returns the folder inside that holds Goldmire."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as e:
        raise UpdateError("the download was damaged (not a zip file); try again later") from e
    root = os.path.realpath(dest)
    for m in zf.infolist():
        target = os.path.realpath(os.path.join(dest, m.filename))
        if not (target == root or target.startswith(root + os.sep)):
            raise UpdateError("the download contains a file path that isn't allowed")
    zf.extractall(dest)
    for dirpath, _dirs, files in os.walk(dest):
        if "bot.py" in files and "version.json" in files:
            return dirpath
    raise UpdateError("the download doesn't look like Goldmire (bot.py is missing)")


def _files(top):
    out = []
    for dirpath, dirs, files in os.walk(top):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            rel = _norm(os.path.relpath(os.path.join(dirpath, name), top))
            if _wanted(rel):
                out.append(rel)
    return sorted(out)


def _verify(top):
    for need in REQUIRED:
        if not os.path.isfile(os.path.join(top, need)):
            raise UpdateError(f"the update is incomplete ({need} is missing)")
    for rel in _files(top):
        if rel.endswith(".py"):
            with open(os.path.join(top, rel), "rb") as f:
                src = f.read()
            try:
                compile(src, rel, "exec")
            except SyntaxError as e:
                raise UpdateError(f"the update has a broken file ({rel}, line {e.lineno}); it was not installed") from e
    return str(_read_json(os.path.join(top, "version.json"), {}).get("version", "0.0.0"))


def _same(a, b):
    def digest(p):
        try:
            with open(p, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except OSError:
            return None
    return digest(a) == digest(b)


def _venv_python():
    exe = sys.executable or ""
    if os.path.basename(exe).lower() == "pythonw.exe":
        cand = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(cand):
            return cand
    return exe


def _pip(requirements, say):
    say("Installing new Python packages the update needs...")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run([_venv_python(), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", requirements],
                       capture_output=True, text=True, timeout=900, creationflags=flags)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-3:]
        raise UpdateError("couldn't install the packages the update needs: " + " / ".join(tail))


def _prune_backups():
    try:
        olds = sorted(d for d in os.listdir(BACKUP_DIR) if os.path.isdir(os.path.join(BACKUP_DIR, d)))
    except OSError:
        return
    for d in olds[:-KEEP_BACKUPS]:
        shutil.rmtree(os.path.join(BACKUP_DIR, d), ignore_errors=True)


def install(expected=None, say=print, target=HERE):
    """Downloads and installs the latest version into `target`. Returns the new version.
    If anything fails, Goldmire is left exactly as it was."""
    src = source()
    if not src:
        raise UpdateError("updates are switched off (no source in update.json)")
    old = current_version()
    say(f"Downloading the update from {src['label']}...")
    try:
        blob = _get(src["zip_url"] + f"?t={int(time.time())}")
    except UpdateError:
        raise
    except Exception as e:  # noqa: BLE001
        raise UpdateError(f"couldn't download the update ({type(e).__name__}: {e})") from e

    with tempfile.TemporaryDirectory(prefix="goldmire-update-") as tmp:
        top = _unpack(blob, tmp)
        new = _verify(top)
        if vtuple(new) <= vtuple(old):
            raise UpdateError(f"the download is version {new}, which isn't newer than {old}; try again in a few minutes")
        if expected and vtuple(new) < vtuple(expected):
            raise UpdateError(f"the download is version {new}, not {expected} yet; try again in a few minutes")
        say(f"Checked every file in version {new}.")

        new_req, old_req = os.path.join(top, "requirements.txt"), os.path.join(target, "requirements.txt")
        if not _same(new_req, old_req):
            _pip(new_req, say)            # before any file changes: if this fails, nothing has changed

        changes = [rel for rel in _files(top) if not _same(os.path.join(top, rel), os.path.join(target, rel))]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = os.path.join(BACKUP_DIR if target == HERE else os.path.join(target, "backups"), f"{stamp}-before-{new}")
        added = []
        try:
            for rel in changes:
                dst = os.path.join(target, rel)
                if os.path.exists(dst):
                    os.makedirs(os.path.dirname(os.path.join(backup, rel)), exist_ok=True)
                    shutil.copy2(dst, os.path.join(backup, rel))
                else:
                    added.append(rel)
            for rel in changes:
                dst = os.path.join(target, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                tmpdst = dst + ".tmp"
                shutil.copy2(os.path.join(top, rel), tmpdst)
                os.replace(tmpdst, dst)
        except Exception as e:  # noqa: BLE001 - put everything back the way it was
            for rel in changes:
                saved, dst = os.path.join(backup, rel), os.path.join(target, rel)
                try:
                    if os.path.exists(saved):
                        shutil.copy2(saved, dst)
                    elif rel in added and os.path.exists(dst):
                        os.remove(dst)
                    if os.path.exists(dst + ".tmp"):
                        os.remove(dst + ".tmp")
                except OSError:
                    pass
            raise UpdateError(f"couldn't replace the files ({type(e).__name__}: {e}); the old version was put back") from e
    say(f"Installed version {new} ({len(changes)} files changed). The old files are in the backups folder.")
    if target == HERE:
        _prune_backups()
    return new


if __name__ == "__main__":
    # Double-click helper: python updater.py  -> checks and installs if there is something new.
    print(f"Goldmire {current_version()}")
    try:
        found = check()
        if not found:
            print("You have the latest version." if source() else "Updates are switched off (see update.json).")
        else:
            print(f"Version {found['version']} is out. Installing...")
            install(found["version"])
            print("Done. Start Goldmire again to use the new version.")
    except UpdateError as e:
        print(f"Update didn't happen: {e}")
