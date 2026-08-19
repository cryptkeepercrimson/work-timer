"""Everything that isn't user interface: settings, stored entries, periods,
input parsing, and writing the markdown logs.

No tkinter in here, so it can be tested on its own.
"""

import calendar
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

def _install_dir():
    """Where the app lives, as a place to keep data next to.

    Running as a script that is simply the folder holding the source. Packaged
    into an .exe it must be the folder holding the .exe: PyInstaller unpacks a
    one-file build into a temporary directory that Windows deletes on exit, so
    anything written relative to this file would silently disappear when the
    user closed the app.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _writable(folder):
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def _data_dir():
    """Where logs and settings go: beside the app, or a per-user folder.

    Keeping data beside the app makes it portable - copy the folder, keep your
    history. That fails in places like Program Files, where a normal account
    cannot write, so fall back to the user's own app data.
    """
    beside = _install_dir()
    if _writable(beside):
        return beside
    fallback = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Work Timer"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


# Bump this with every release, before building the .exe - it is what someone
# reports when they tell you something is broken. See RELEASING.md.
__version__ = "1.2.1"

# Shown in the app's About panel. The licence asks that copies keep the credit,
# so it has to be somewhere a copy actually carries.
AUTHOR = "CryptKeeperCrimson"
HOMEPAGE = "github.com/cryptkeepercrimson/work-timer"

APP_DIR = _data_dir()
INSTALL_DIR = _install_dir()
LOG_DIR = APP_DIR / "Time Logs"
DATA_FILE = LOG_DIR / "entries.json"
SETTINGS_FILE = APP_DIR / "settings.json"

# How often a fresh log file starts. Anything driven by a fixed number of days
# is measured in steps from `anchor`; monthly follows the calendar instead.
FREQUENCIES = {
    "none": "No periods - one ongoing log",
    "daily": "Daily",
    "weekly": "Weekly",
    "biweekly": "Every 2 weeks",
    "monthly": "Monthly",
}
STEP_DAYS = {"daily": 1, "weekly": 7, "biweekly": 14}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"]

# Footer stamped on every generated file. Regrouping deletes files carrying it,
# so it doubles as proof that a file is ours to delete.
GENERATED_MARKER = (
    "*Rebuilt automatically by Work Timer whenever an entry is added - "
    "edits made here by hand will be lost. Source data: `entries.json`.*"
)

BACKUP_DAYS = 60          # how long daily snapshots of entries.json are kept
HEARTBEAT_SECONDS = 30    # how often a running timer records that it's alive
INSTANCE_TIMEOUT = 90     # a lock older than this belongs to a dead instance
INSTANCE_POLL_MS = 2000   # how often the live instance refreshes and checks in

def default_anchor():
    """The most recent Monday - a sensible period start for someone new.

    Whatever the user picks in settings replaces this; it only decides where
    periods fall before anyone has said.
    """
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


DEFAULTS = {
    "frequency": "biweekly",
    "anchor": None,           # filled in with default_anchor() when unset
    "month_start_day": 1,
    "position": "+120+120",
    "theme": "midnight",
    "ui_font": "Segoe UI",
    "clock_font": "Consolas",
    "start_with_windows": False,
    "sort_by": "date",        # which column the log window is ordered by
    "sort_desc": True,
    "log_view": "summary",   # log window opens on totals, not every entry
    "groups": {},             # {group name: [id keys]} reported as one line
}


# --------------------------------------------------------------------------
# settings / storage
# --------------------------------------------------------------------------

def load_settings():
    settings = dict(DEFAULTS)
    stored = {}
    try:
        loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            stored = loaded
            settings.update(loaded)
    except Exception:
        pass
    # Earlier versions called the anchor "pay_period_anchor". Check what was on
    # disk, not the merged result - the default always supplies "anchor".
    if "anchor" not in stored and "pay_period_anchor" in stored:
        settings["anchor"] = stored["pay_period_anchor"]
    if not settings.get("anchor"):
        settings["anchor"] = default_anchor()
    if settings.get("frequency") not in FREQUENCIES:
        settings["frequency"] = DEFAULTS["frequency"]
    return settings


def is_first_run():
    """True before anything has been configured or logged."""
    return not SETTINGS_FILE.exists() and not DATA_FILE.exists()


def save_settings(**changes):
    """Merge changes into the settings file, leaving everything else alone."""
    settings = load_settings()
    settings.update(changes)
    settings.pop("pay_period_anchor", None)
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_entries():
    """Every stored entry, each guaranteed to carry a stable uid."""
    try:
        entries = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            return []
    except Exception:
        return []

    # Entries written before editing existed have no uid; give them one so the
    # log viewer can refer to them.
    missing = [e for e in entries if not e.get("uid")]
    for entry in missing:
        entry["uid"] = uuid.uuid4().hex[:12]
    if missing:
        save_entries(entries)
    return entries


def backup_dir():
    return LOG_DIR / "backups"


def keep_backup():
    """Preserve the current entries file before it gets overwritten.

    Two layers, because they fail differently:

    * `entries.previous.json` - the state immediately before the most recent
      change. Undoes one bad edit or delete.
    * `backups/entries-YYYY-MM-DD.json` - written once per day, the first time
      anything changes that day, so it holds the state as it was *before* that
      day's work. A mistake noticed a week later is still recoverable.

    Never allowed to interrupt the save it precedes - a failed backup is worth
    reporting, but not worth refusing to record the user's time over.
    """
    if not DATA_FILE.exists():
        return
    try:
        existing = DATA_FILE.read_text(encoding="utf-8")
        if not existing.strip():
            return                       # nothing worth keeping
        (LOG_DIR / "entries.previous.json").write_text(existing, encoding="utf-8")

        daily = backup_dir() / f"entries-{date.today():%Y-%m-%d}.json"
        if not daily.exists():
            backup_dir().mkdir(parents=True, exist_ok=True)
            daily.write_text(existing, encoding="utf-8")
            prune_backups()
    except Exception:
        pass


def prune_backups(keep_days=BACKUP_DAYS):
    """Drop daily snapshots older than the retention window."""
    cutoff = date.today() - timedelta(days=keep_days)
    if not backup_dir().exists():
        return
    for path in backup_dir().glob("entries-*.json"):
        try:
            stamp = date.fromisoformat(path.stem.replace("entries-", ""))
        except ValueError:
            continue                     # not one of ours; leave it alone
        if stamp < cutoff:
            try:
                path.unlink()
            except Exception:
                pass


def save_entries(entries):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    keep_backup()
    tmp = DATA_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    tmp.replace(DATA_FILE)  # atomic, so a crash mid-write can't lose the log


# --------------------------------------------------------------------------
# periods
# --------------------------------------------------------------------------

def anchor_date(settings=None):
    settings = settings or load_settings()
    try:
        return date.fromisoformat(str(settings.get("anchor")))
    except Exception:
        return date.fromisoformat(default_anchor())


def month_start_day(settings=None):
    settings = settings or load_settings()
    try:
        return min(max(int(settings.get("month_start_day", 1)), 1), 28)
    except Exception:
        return 1


def period_for(day, settings=None):
    """Return (start, end) dates of the period containing `day`.

    Returns None when periods are switched off - everything lives in one log.
    """
    settings = settings or load_settings()
    frequency = settings.get("frequency", "biweekly")

    if frequency == "none":
        return None

    if frequency == "monthly":
        start_day = month_start_day(settings)
        year, month = day.year, day.month
        if day.day < start_day:            # still inside the period that began last month
            year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        start = date(year, month, start_day)
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        return start, date(next_year, next_month, start_day) - timedelta(days=1)

    step = STEP_DAYS.get(frequency, 14)
    if step == 1:
        return day, day
    offset = (day - anchor_date(settings)).days // step  # floors, so past dates work
    start = anchor_date(settings) + timedelta(days=offset * step)
    return start, start + timedelta(days=step - 1)


def period_filename(period, settings=None):
    if period is None:
        return "All Time.md"
    start, end = period
    settings = settings or load_settings()
    frequency = settings.get("frequency", "biweekly")
    if frequency == "daily":
        return f"{start:%Y-%m-%d}.md"
    if frequency == "monthly" and month_start_day(settings) == 1:
        return f"{start:%Y-%m} {calendar.month_name[start.month]}.md"
    return f"{start:%Y-%m-%d} to {end:%Y-%m-%d}.md"


def period_heading(period, settings=None):
    if period is None:
        return "Work Log - All Time"
    start, end = period
    settings = settings or load_settings()
    frequency = settings.get("frequency", "biweekly")
    if frequency == "daily":
        return f"{start:%A, %B %d, %Y}"
    if frequency == "monthly" and month_start_day(settings) == 1:
        return f"{calendar.month_name[start.month]} {start.year}"
    label = {"weekly": "Week", "biweekly": "Pay Period", "monthly": "Month"}.get(
        frequency, "Period")
    return f"{label}: {start:%Y-%m-%d} to {end:%Y-%m-%d}"


def period_short_label(period, settings=None):
    """The one-line description shown on the widget itself."""
    if period is None:
        return "All time"
    start, end = period
    settings = settings or load_settings()
    if settings.get("frequency") == "daily":
        return f"{start:%b %d}"
    if settings.get("frequency") == "monthly" and month_start_day(settings) == 1:
        return f"{start:%B}"
    return f"{start:%b %d}-{end:%b %d}"


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------

def format_elapsed(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def to_hours(seconds):
    return round(seconds / 3600, 2)


def to_minutes(seconds):
    return round(seconds / 60, 1)


def clean_cell(text):
    """Keep a value safe to drop into a markdown table cell."""
    return text.strip().replace("|", "\\|").replace("\n", " ")


# --------------------------------------------------------------------------
# forgiving date/time parsing, for entries typed by hand
# --------------------------------------------------------------------------

class ParseError(ValueError):
    """Raised when typed input can't be understood."""


def parse_date(text, today=None):
    """Accept 'today', 'yesterday', '2026-08-09', '8/9', '8/9/2026', 'Aug 9'."""
    today = today or date.today()
    raw = text.strip().lower()
    if not raw or raw in ("today", "t"):
        return today
    if raw in ("yesterday", "y"):
        return today - timedelta(days=1)

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    # Formats with no year: assume the current one, but if that lands more than a
    # week ahead it was almost certainly last year (logging late in December).
    for fmt in ("%m/%d", "%m-%d", "%b %d", "%B %d"):
        try:
            parsed = datetime.strptime(raw, fmt).date().replace(year=today.year)
        except ValueError:
            continue
        if parsed > today + timedelta(days=7):
            parsed = parsed.replace(year=today.year - 1)
        return parsed
    raise ParseError(f"Can't read the date '{text.strip()}'")


def parse_time(text):
    """Accept '9', '9:30', '930', '0930', '9.30', '9:30 am', '2pm', '14:00'."""
    raw = text.strip().lower().replace(" ", "")
    if not raw:
        raise ParseError("Enter a time")

    meridiem = None
    for suffix in ("am", "a.m.", "a"):
        if raw.endswith(suffix):
            meridiem, raw = "am", raw[: -len(suffix)]
            break
    else:
        for suffix in ("pm", "p.m.", "p"):
            if raw.endswith(suffix):
                meridiem, raw = "pm", raw[: -len(suffix)]
                break
    raw = raw.rstrip(":.")

    if ":" in raw or "." in raw:
        head, _, tail = raw.replace(".", ":").partition(":")
        hour_text, minute_text = head, tail or "0"
    elif len(raw) in (3, 4) and raw.isdigit():   # 930 / 0930
        hour_text, minute_text = raw[:-2], raw[-2:]
    else:
        hour_text, minute_text = raw, "0"

    if not (hour_text.isdigit() and minute_text.isdigit()):
        raise ParseError(f"Can't read the time '{text.strip()}'")
    hour, minute = int(hour_text), int(minute_text)

    if meridiem == "am":
        if not 1 <= hour <= 12:
            raise ParseError(f"'{text.strip()}' isn't a valid am time")
        hour = 0 if hour == 12 else hour
    elif meridiem == "pm":
        if not 1 <= hour <= 12:
            raise ParseError(f"'{text.strip()}' isn't a valid pm time")
        hour = hour if hour == 12 else hour + 12

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ParseError(f"'{text.strip()}' isn't a valid time")
    return hour, minute


def build_span(date_text, start_text, end_text):
    """Turn typed date/start/end into datetimes. Returns (start, end, crossed_midnight)."""
    day = parse_date(date_text)
    start_h, start_m = parse_time(start_text)
    end_h, end_m = parse_time(end_text)

    started = datetime(day.year, day.month, day.day, start_h, start_m)
    ended = datetime(day.year, day.month, day.day, end_h, end_m)
    if ended == started:
        raise ParseError("Start and end are the same time")
    crossed = ended < started
    if crossed:
        ended += timedelta(days=1)   # an overnight session
    return started, ended, crossed


# --------------------------------------------------------------------------
# writing the log files
# --------------------------------------------------------------------------

def entries_in_period(entries, period):
    if period is None:
        return list(entries)
    start, end = period
    return [e for e in entries if start.isoformat() <= e["start"][:10] <= end.isoformat()]


def render_period(entries, period, settings=None):
    settings = settings or load_settings()
    rows = sorted(entries_in_period(entries, period), key=lambda e: e["start"])

    grand = sum(e["seconds"] for e in rows)
    totals = grouped_totals(rows, load_groups(settings))

    out = [
        f"# {period_heading(period, settings)}",
        "",
        f"**{to_hours(grand)} hours ({to_minutes(grand)} minutes) across "
        f"{len(rows)} {'entry' if len(rows) == 1 else 'entries'}.**",
        "",
        "## Totals by ID",
        "",
        "| ID | Hours (decimal) | Minutes | Entries |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in totals:
        if row["kind"] == "group":
            # The group is the figure to submit; its parts sit underneath in
            # case anyone asks what made it up.
            out.append(
                f"| **{clean_cell(row['label'])}** | **{to_hours(row['seconds'])}** | "
                f"**{to_minutes(row['seconds'])}** | **{row['count']}** |")
            for member in row["members"]:
                out.append(
                    f"| &nbsp;&nbsp;↳ {clean_cell(member['label'])} | "
                    f"{to_hours(member['seconds'])} | {to_minutes(member['seconds'])} | "
                    f"{member['count']} |")
        else:
            out.append(
                f"| {clean_cell(row['label'])} | {to_hours(row['seconds'])} | "
                f"{to_minutes(row['seconds'])} | {row['count']} |")
    # A Break column would be noise in the usual case, so it only appears when
    # something in this period actually has one.
    any_breaks = any(e.get("paused_seconds") for e in rows)
    out += [
        f"| **Total** | **{to_hours(grand)}** | **{to_minutes(grand)}** | **{len(rows)}** |",
        "",
        "## Entries",
        "",
        "| Date | Start | End | ID | Description | "
        + ("Break | " if any_breaks else "")
        + "Hours (decimal) | Minutes |",
        "| --- | --- | --- | --- | --- | " + ("---: | " if any_breaks else "")
        + "---: | ---: |",
    ]
    for e in rows:
        started = datetime.fromisoformat(e["start"])
        ended = datetime.fromisoformat(e["end"])
        paused = e.get("paused_seconds", 0)
        break_cell = ""
        if any_breaks:
            break_cell = f"{to_minutes(paused)} min | " if paused else " | "
        out.append(
            f"| {started:%Y-%m-%d} | {started:%H:%M} | {ended:%H:%M} | "
            f"{clean_cell(e['id'])} | {clean_cell(e.get('description', ''))} | "
            f"{break_cell}{to_hours(e['seconds'])} | {to_minutes(e['seconds'])} |"
        )
    out += ["", "---", "", GENERATED_MARKER, ""]
    return "\n".join(out)


def write_period(entries, period, settings=None):
    """Write one period's markdown file."""
    settings = settings or load_settings()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / period_filename(period, settings)
    path.write_text(render_period(entries, period, settings), encoding="utf-8")
    return path


def is_generated(path):
    """True only for markdown this app wrote, identified by its footer.

    Regrouping deletes the old files, so this has to be certain - anything the
    user wrote or dropped into the folder themselves must never match.
    """
    if path.suffix.lower() != ".md":
        return False
    try:
        return GENERATED_MARKER in path.read_text(encoding="utf-8")
    except Exception:
        return False


def rebuild_all(settings=None):
    """Regenerate every log file from scratch under the current settings."""
    settings = settings or load_settings()
    if LOG_DIR.exists():
        for path in LOG_DIR.iterdir():
            if path.is_file() and is_generated(path):
                path.unlink()

    entries = load_entries()
    if not entries:
        return 0
    periods = {period_for(date.fromisoformat(e["start"][:10]), settings) for e in entries}
    for period in periods:
        write_period(entries, period, settings)
    return len(periods)


# --------------------------------------------------------------------------
# adding, changing and removing entries
# --------------------------------------------------------------------------

def worked_seconds(started_at, ended_at, paused_seconds=0):
    """Time actually worked: the span, less any breaks, never below zero."""
    span = (ended_at - started_at).total_seconds()
    return max(int(span) - int(paused_seconds or 0), 0)


def make_entry(entry_id, description, started_at, ended_at, paused_seconds=0):
    entry = {
        "uid": uuid.uuid4().hex[:12],
        "id": tidy_id(entry_id),
        "description": description.strip(),
        "start": started_at.replace(microsecond=0).isoformat(),
        "end": ended_at.replace(microsecond=0).isoformat(),
        "seconds": worked_seconds(started_at, ended_at, paused_seconds),
    }
    # Only recorded when there was one, so entries without breaks - the vast
    # majority - keep the shape they have always had.
    if paused_seconds:
        entry["paused_seconds"] = int(paused_seconds)
    return entry


def log_session(entry_id, description, started_at, ended_at, paused_seconds=0):
    """Record one session and rebuild its log file. Returns the file path."""
    entries = load_entries()
    entry_id = canonical_id(entry_id, entries)   # fold "admin" into "Admin"
    entries.append(
        make_entry(entry_id, description, started_at, ended_at, paused_seconds))
    save_entries(entries)
    return write_period(entries, period_for(started_at.date()))


def update_entry(uid, entry_id, description, started_at, ended_at, paused_seconds=None):
    """Change an existing entry, then rebuild every log file.

    A full rebuild is the simple correct answer: an edited date can move the
    entry into a different period, emptying one file and filling another.
    """
    entries = load_entries()
    # This entry is left out of the vote, so its own spelling can be changed.
    entry_id = canonical_id(entry_id, entries, exclude_uid=uid)
    for entry in entries:
        if entry.get("uid") == uid:
            # Left alone, an existing break is preserved rather than silently
            # turning into billable time.
            breaks = (entry.get("paused_seconds", 0) if paused_seconds is None
                      else int(paused_seconds))
            entry.update({
                "id": entry_id,
                "description": description.strip(),
                "start": started_at.replace(microsecond=0).isoformat(),
                "end": ended_at.replace(microsecond=0).isoformat(),
                "seconds": worked_seconds(started_at, ended_at, breaks),
            })
            if breaks:
                entry["paused_seconds"] = int(breaks)
            else:
                entry.pop("paused_seconds", None)
            break
    else:
        return False
    save_entries(entries)
    rebuild_all()
    return True


def delete_entry(uid):
    entries = load_entries()
    remaining = [e for e in entries if e.get("uid") != uid]
    if len(remaining) == len(entries):
        return False
    save_entries(remaining)
    rebuild_all()
    return True


# --------------------------------------------------------------------------
# surviving a crash while the timer is running
# --------------------------------------------------------------------------

def running_file():
    return LOG_DIR / "running.json"


def mark_running(started_at, last_seen=None, paused_seconds=0, paused_at=None):
    """Record that a timer is going, and that the app was alive just now.

    `last_seen` is refreshed every few seconds while the timer runs. If the app
    dies, it is the best available estimate of when the work stopped - far
    closer to the truth than "whenever the app is next opened", which could be
    days later.

    Breaks are recorded too, so a crash can't turn a pause into billable time.
    `paused_at` is set only while a break is actually open.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        state = {
            "started": started_at.replace(microsecond=0).isoformat(),
            "last_seen": (last_seen or datetime.now()).replace(microsecond=0).isoformat(),
            "paused_seconds": int(paused_seconds or 0),
        }
        if paused_at is not None:
            state["paused_at"] = paused_at.replace(microsecond=0).isoformat()
        running_file().write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def clear_running():
    """Called once a running timer has been dealt with, one way or another."""
    try:
        running_file().unlink(missing_ok=True)
    except Exception:
        pass


def recovered_session():
    """An unfinished timer left behind by a previous run, or None.

    Anything unreadable or nonsensical is treated as absent - a broken file
    must never block the app from opening.
    """
    try:
        data = json.loads(running_file().read_text(encoding="utf-8"))
        started = datetime.fromisoformat(data["started"])
        last_seen = datetime.fromisoformat(data.get("last_seen") or data["started"])
    except Exception:
        return None
    if last_seen < started:
        last_seen = started

    try:
        paused_seconds = max(int(data.get("paused_seconds", 0)), 0)
    except Exception:
        paused_seconds = 0
    try:
        paused_at = datetime.fromisoformat(data["paused_at"])
    except Exception:
        paused_at = None

    # Work stopped when the break began, so that - not the last heartbeat - is
    # the end of the recovered session.
    ended = paused_at if paused_at and started <= paused_at <= last_seen else last_seen
    return {"started": started, "last_seen": last_seen, "ended": ended,
            "paused_seconds": min(paused_seconds, int((ended - started).total_seconds()))}


# --------------------------------------------------------------------------
# only one copy at a time
#
# Two running copies would both write entries.json, and whichever saved last
# would silently erase the other's entry. A lock file names the live instance;
# a second launch hands over to it instead of starting.
# --------------------------------------------------------------------------

def lock_file():
    return APP_DIR / "app.lock"


def focus_file():
    return APP_DIR / "focus.request"


def process_alive(pid):
    """Whether a process with this id exists.

    Deliberately not os.kill(pid, 0) - on Windows that calls TerminateProcess
    and would kill the very instance we are checking for.
    """
    if not pid or pid <= 0:
        return False
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32

        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        # OpenProcess alone is not enough: a pid stays valid while anything
        # still holds a handle to it, so an exited process can still be opened.
        # The exit code is what says whether it is actually running.
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        if not ok:
            return None
        return code.value == STILL_ACTIVE
    except Exception:
        return None       # can't tell; fall back to the heartbeat


def another_instance_running():
    """True when a different, live copy of the app holds the lock."""
    try:
        data = json.loads(lock_file().read_text(encoding="utf-8"))
        pid = int(data["pid"])
        beat = datetime.fromisoformat(data["heartbeat"])
    except Exception:
        return False
    if pid == os.getpid():
        return False

    alive = process_alive(pid)
    if alive is False:
        return False                     # it crashed; the lock is ours to take
    # Either the process is alive, or we couldn't check - trust the heartbeat.
    return (datetime.now() - beat).total_seconds() < INSTANCE_TIMEOUT


def claim_lock():
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        lock_file().write_text(json.dumps({
            "pid": os.getpid(),
            "heartbeat": datetime.now().replace(microsecond=0).isoformat(),
        }, indent=2), encoding="utf-8")
    except Exception:
        pass


def release_lock():
    """Only ever release our own lock, never one held by another instance."""
    try:
        data = json.loads(lock_file().read_text(encoding="utf-8"))
        if int(data.get("pid", -1)) == os.getpid():
            lock_file().unlink(missing_ok=True)
    except Exception:
        pass


def request_focus():
    """Ask the running instance to show itself, then leave it to it."""
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        focus_file().write_text(
            datetime.now().isoformat(), encoding="utf-8")
    except Exception:
        pass


def focus_requested():
    """True once if another launch asked us to come to the front."""
    try:
        if focus_file().exists():
            focus_file().unlink()
            return True
    except Exception:
        pass
    return False


# --------------------------------------------------------------------------
# starting with Windows (opt in)
# --------------------------------------------------------------------------

def startup_folder():
    return Path(os.path.expandvars(
        r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"))


def startup_file():
    return startup_folder() / "Work Timer.vbs"


def startup_enabled():
    return startup_file().exists()


def set_startup(enabled):
    """Add or remove a launcher in the Windows Startup folder.

    A .vbs rather than a shortcut: it needs no COM libraries, and it starts the
    app without a console window flashing up at login. Returns True on success.
    """
    try:
        if not enabled:
            startup_file().unlink(missing_ok=True)
            return True

        if getattr(sys, "frozen", False):
            # Packaged: launch the .exe itself. There is no Python on the
            # machine to point at.
            command = f'""{Path(sys.executable).resolve()}""'
        else:
            runner = Path(sys.executable)
            if runner.name.lower() == "python.exe":    # avoid a console window
                windowless = runner.with_name("pythonw.exe")
                if windowless.exists():
                    runner = windowless
            command = f'""{runner}"" ""{INSTALL_DIR / "work_timer.py"}""'

        startup_folder().mkdir(parents=True, exist_ok=True)
        startup_file().write_text(
            "' Starts Work Timer when you sign in to Windows.\n"
            "' Delete this file, or untick the box in the app's settings, to stop.\n"
            "Set shell = CreateObject(\"WScript.Shell\")\n"
            f"shell.CurrentDirectory = \"{INSTALL_DIR}\"\n"
            f"shell.Run \"{command}\", 0, False\n",
            encoding="utf-8")
        return True
    except Exception:
        return False


def period_total_seconds(day=None):
    period = period_for(day or date.today())
    return sum(e["seconds"] for e in entries_in_period(load_entries(), period))


# --------------------------------------------------------------------------
# keeping external IDs consistent
#
# Totals are grouped by ID, so "Admin" and "admin" would invoice as two
# separate lines - easy to type, easy to miss, wrong on the invoice. IDs that
# differ only in capitalisation or spacing are treated as the same one.
# --------------------------------------------------------------------------

def id_key(text):
    """The comparison form of an ID: no case, no spaces.

    Punctuation is kept, so "SD-4471" and "SD4471" stay distinct - in a ticket
    system those can genuinely be different things.
    """
    if not isinstance(text, str):
        return ""      # never let None become the key "none" and match an ID
    return "".join(text.lower().split())


def tidy_id(text):
    """Trim, and collapse runs of spaces, without changing the spelling."""
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())


def id_spellings(entries=None, exclude_uid=None):
    """Map each ID key to the spelling that should win.

    The most-used spelling, breaking ties towards the most recent - so one
    stray "admin" never renames the "Admin" you've used twenty times.

    `exclude_uid` leaves an entry out of the vote. Editing an entry has to be
    able to change its own spelling; without this, the entry being renamed
    would supply the canonical form and snap itself straight back.
    """
    tally = {}
    for position, entry in enumerate(entries if entries is not None else load_entries()):
        if entry.get("uid") and entry.get("uid") == exclude_uid:
            continue
        key = id_key(entry.get("id", ""))
        if not key:
            continue
        spelling = tidy_id(entry["id"])
        seen = tally.setdefault(key, {})
        count, _ = seen.get(spelling, (0, 0))
        seen[spelling] = (count + 1, position)

    winners = {}
    for key, spellings in tally.items():
        winners[key] = max(spellings.items(), key=lambda item: item[1])[0]
    return winners


def canonical_id(text, entries=None, exclude_uid=None):
    """The spelling this ID will actually be saved under."""
    tidied = tidy_id(text)
    key = id_key(tidied)
    if not key:
        return tidied
    return id_spellings(entries, exclude_uid).get(key, tidied)


def is_new_id(text, entries=None, exclude_uid=None):
    """True when nothing logged so far shares this ID - flags likely typos."""
    key = id_key(text)
    return bool(key) and key not in id_spellings(entries, exclude_uid)


# --------------------------------------------------------------------------
# groups
#
# Several IDs can be reported as one line - a handful of admin categories
# totalled together, or every project for one client. Grouping is stored in
# settings, not on the entries: it is a way of reporting the hours, so changing
# it must never touch what was actually logged.
# --------------------------------------------------------------------------

def load_groups(settings=None):
    """{group name: [id keys]}, cleaned of anything malformed."""
    settings = settings or load_settings()
    raw = settings.get("groups")
    groups = {}
    if isinstance(raw, dict):
        for name, members in raw.items():
            label = tidy_id(name)
            if not label or not isinstance(members, list):
                continue
            keys = []
            for member in members:
                key = id_key(member)
                if key and key not in keys:
                    keys.append(key)
            groups[label] = keys
    return groups


def group_of(entry_id, groups=None):
    """The group an ID reports under, or None. An ID belongs to at most one."""
    groups = load_groups() if groups is None else groups
    key = id_key(entry_id)
    for name, members in groups.items():
        if key in members:
            return name
    return None


def assign_to_group(groups, entry_id, group_name):
    """Put an ID in a group, or take it out entirely when group_name is None.

    Membership is exclusive - an ID counted under two groups would be billed
    twice, so joining one always leaves the other.
    """
    key = id_key(entry_id)
    if not key:
        return groups
    for members in groups.values():
        if key in members:
            members.remove(key)
    if group_name:
        groups.setdefault(tidy_id(group_name), []).append(key)
    return groups


def grouped_totals(entries, groups=None):
    """Totals ready to report, alphabetical, with grouped IDs nested.

    Returns rows of {"kind": "group"|"id", "label", "seconds", "count"} where a
    group row also carries "members" - the same shape, one level down.
    """
    groups = load_groups() if groups is None else groups
    spellings = id_spellings(entries)

    per_id = {}
    for entry in entries:
        key = id_key(entry.get("id", ""))
        if not key:
            continue
        bucket = per_id.setdefault(key, {"seconds": 0, "count": 0})
        bucket["seconds"] += entry["seconds"]
        bucket["count"] += 1

    rows, claimed = [], set()
    for name in sorted(groups, key=str.lower):
        members = [k for k in groups[name] if k in per_id]
        if not members:
            continue          # a group nothing has been logged against yet
        claimed.update(members)
        member_rows = [{
            "kind": "id",
            "label": spellings.get(key, key),
            "seconds": per_id[key]["seconds"],
            "count": per_id[key]["count"],
        } for key in members]
        member_rows.sort(key=lambda r: r["label"].lower())
        rows.append({
            "kind": "group",
            "label": name,
            "seconds": sum(r["seconds"] for r in member_rows),
            "count": sum(r["count"] for r in member_rows),
            "members": member_rows,
        })

    for key, totals in per_id.items():
        if key not in claimed:
            rows.append({"kind": "id", "label": spellings.get(key, key),
                         "seconds": totals["seconds"], "count": totals["count"]})

    rows.sort(key=lambda r: r["label"].lower())
    return rows


def all_ids():
    """Every ID in use, with its total, most hours first."""
    totals = {}
    for entry in load_entries():
        key = id_key(entry.get("id", ""))
        if key:
            totals[key] = totals.get(key, 0) + entry["seconds"]
    spellings = id_spellings()
    return sorted(
        ((spellings[key], seconds) for key, seconds in totals.items()),
        key=lambda item: (-item[1], item[0].lower()))


def recent_ids(limit=3):
    """The last few IDs used, in canonical spelling, without repeats."""
    entries = load_entries()
    spellings = id_spellings(entries)
    seen, keys = [], set()
    for entry in reversed(entries):
        key = id_key(entry.get("id", ""))
        if not key or key in keys:
            continue
        keys.add(key)
        seen.append(spellings.get(key, tidy_id(entry["id"])))
        if len(seen) == limit:
            break
    return seen


def known_periods(settings=None):
    """Every period that currently holds at least one entry, newest first."""
    settings = settings or load_settings()
    periods = {period_for(date.fromisoformat(e["start"][:10]), settings)
               for e in load_entries()}
    if None in periods:
        return [None]
    return sorted(periods, key=lambda p: p[0], reverse=True)
