"""
FinBERT: a second news reader, running in SHADOW for now.

The Town Crier (news.py) reads headlines with a word list. FinBERT is a small AI model
trained on financial news (ProsusAI/finbert, free on Hugging Face). It reads each headline
and says how likely it is to be good, neutral or bad news for the company.

In shadow it decides NOTHING: no sales, no blocked buys. It only writes down where it
disagrees with the word list (news_shadow.jsonl and the log), and the replay test
(news_replay.py) checks on real past headlines which reader's bad-news calls were
actually followed by falling prices. FinBERT only gets a vote if it wins that test.

First start: it installs PyTorch and Transformers into Goldmire's Python (about 1 GB on
disk, a few minutes) and downloads the model (about 440 MB) in the background. Trading
carries on while that happens. If anything fails, it says so once and stays off.
"""
import os
import subprocess
import sys
import threading

MODEL = "ProsusAI/finbert"
ALARM_NEG = 0.80          # FinBERT calls it bad news when it's at least this sure (and bad is its top answer)
TIP_POS = 0.80
PACKAGES = ["torch", "transformers"]

_state = {"ready": False, "pipe": None, "error": None, "started": False}
_lock = threading.Lock()


def ready():
    return _state["ready"]


def status():
    return "ready" if _state["ready"] else ("off: " + _state["error"]) if _state["error"] else "starting"


def _installed():
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _install(log):
    log("FinBERT: installing PyTorch and Transformers (one time, about 1 GB, a few minutes; trading carries on)")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q"] + PACKAGES,
                       capture_output=True, text=True, timeout=3600, creationflags=flags)
    if r.returncode != 0:
        tail = " / ".join((r.stderr or r.stdout or "").strip().splitlines()[-2:])
        raise RuntimeError(f"couldn't install the packages ({tail[:300]})")
    import importlib
    importlib.invalidate_caches()


def _load(log, on_ready):
    try:
        if not _installed():
            _install(log)
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        import logging
        for name in ("httpx", "huggingface_hub", "transformers", "urllib3"):
            logging.getLogger(name).setLevel(logging.WARNING)   # keep their chatter out of Goldmire's log
        log("FinBERT: loading the model (the first time it downloads about 440 MB)")
        from transformers import pipeline
        pipe = pipeline("text-classification", model=MODEL, top_k=None, device=-1)
        pipe(["Company beats estimates"])                       # warm up
        _state["pipe"], _state["ready"] = pipe, True
        log("FinBERT: ready (shadow mode: it reads every headline but decides nothing yet)")
        if on_ready:
            on_ready()
    except Exception as e:  # noqa: BLE001
        _state["error"] = str(e)[:300]
        log(f"FinBERT: couldn't start, so the word list carries on alone ({_state['error']})")


def start(log=print, on_ready=None):
    """Install/load in the background. Safe to call more than once."""
    if _state["started"]:
        return
    _state["started"] = True
    threading.Thread(target=_load, args=(log, on_ready), daemon=True, name="finbert").start()


def load_now(log=print):
    """For the replay test: load in this thread. Returns True when ready."""
    if not _state["ready"]:
        _state["started"] = True
        _load(log, None)
    return _state["ready"]


def score(headlines, batch=32):
    """[{"pos": p, "neu": p, "neg": p}, ...] for each headline, or None while not ready."""
    if not _state["ready"]:
        return None
    out, pipe = [], _state["pipe"]
    for i in range(0, len(headlines), batch):
        part = [h or "" for h in headlines[i:i + batch]]
        with _lock:                       # one batch at a time, so the replay never holds up a trading round for long
            res_all = pipe(part, truncation=True, max_length=96)
        for res in res_all:
            out.append({d["label"].lower()[:3]: round(float(d["score"]), 3) for d in res})
    return out


def is_alarm(s):
    return bool(s) and s.get("neg", 0) >= ALARM_NEG and s["neg"] >= max(s.get("pos", 0), s.get("neu", 0))


def is_tip(s):
    return bool(s) and s.get("pos", 0) >= TIP_POS and s["pos"] >= max(s.get("neg", 0), s.get("neu", 0))


def label(s):
    if not s:
        return "?"
    k = max(("pos", "neu", "neg"), key=lambda x: s.get(x, 0))
    return {"pos": "good", "neu": "neutral", "neg": "bad"}[k] + f" {s[k]:.0%}"
