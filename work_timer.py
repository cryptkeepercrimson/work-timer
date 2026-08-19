"""Work Timer - a small floating desktop stopwatch that logs work to markdown.

Press START to begin tracking and STOP to finish, use "+ Add" for work you
forgot to time, and "Log" to review or correct anything already recorded. Each
entry is tagged with an external ID and filed into a markdown log for its period
- daily, weekly, fortnightly, monthly, or one ongoing log - inside the
"Time Logs" folder next to this script.

The real data lives in "Time Logs/entries.json". The markdown files are rebuilt
from it whenever anything changes, so totals are always correct - but hand edits
to the markdown will be overwritten.
"""

import re
import tkinter as tk
from datetime import date, datetime

import wt_core as core
import wt_dialogs as dialogs
import wt_theme as theme


class WorkTimer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.started_at = None      # when the session began
        self.paused_at = None       # when the current break began, if on a break
        self.paused_seconds = 0     # breaks taken so far this session
        self.tick_job = None
        self.last_heartbeat = None
        self.recovery_job = None
        self.lock_job = None
        self.drag_origin = (0, 0)
        self.viewer = None

        settings = core.load_settings()
        theme.apply_settings(settings)

        self.title("Work Timer")
        self.overrideredirect(True)  # frameless, so it sits on the desktop like a widget
        self.attributes("-topmost", True)
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}"
                      f"{self.usable_position(settings.get('position'))}")
        self.build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close)
        # Once the window is actually on screen, so the prompt has a parent to
        # sit under.
        self.recovery_job = self.after(
            300, self.welcome if core.is_first_run() else self.check_recovered_timer)
        core.claim_lock()
        self.hold_lock()

    WIDTH, HEIGHT = 300, 170

    def usable_position(self, position):
        """Keep the window reachable.

        It has no title bar and no taskbar button, so a position saved on a
        monitor that is no longer attached would leave it stranded offscreen
        with no way to get it back. Fall back to the default in that case.
        """
        default = core.DEFAULTS["position"]
        # Saved as "+x+y"; either number can be negative on a monitor sitting
        # to the left of or above the primary one, giving "+-1200+100".
        match = re.fullmatch(r"\+(-?\d+)\+(-?\d+)", str(position or ""))
        if not match:
            return default
        x, y = int(match.group(1)), int(match.group(2))

        left, top = self.winfo_vrootx(), self.winfo_vrooty()
        right, bottom = left + self.winfo_vrootwidth(), top + self.winfo_vrootheight()
        visible_w = min(x + self.WIDTH, right) - max(x, left)
        visible_h = min(y + self.HEIGHT, bottom) - max(y, top)
        if visible_w < 80 or visible_h < 40:
            return default
        return f"+{x}+{y}"

    # ----------------------------------------------------------------
    # building the window - re-run whenever the theme or font changes
    # ----------------------------------------------------------------
    def build_ui(self):
        for child in self.winfo_children():
            child.destroy()
        self.configure(bg=theme.c("bg"))

        bar = tk.Frame(self, bg=theme.c("panel"), height=26)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="  Work Timer", bg=theme.c("panel"), fg=theme.c("dim"),
                 font=theme.ui(8, "bold")).pack(side="left")

        self._bar_button(bar, "  ✕  ", self.close, theme.ui(9))
        self._bar_button(bar, " ⚙ ", self.edit_settings, theme.ui(9))
        self._bar_button(bar, " Log ", self.show_log, theme.ui(8))
        self._bar_button(bar, " + Add ", self.add_manual, theme.ui(8))

        body = tk.Frame(self, bg=theme.c("bg"))
        body.pack(fill="both", expand=True)

        self.clock = tk.Label(body, text="00:00:00", bg=theme.c("bg"), fg=theme.c("fg"),
                              font=theme.clock(24))
        self.clock.pack(pady=(10, 0))

        self.status = tk.Label(body, text="", bg=theme.c("bg"), fg=theme.c("dim"),
                               font=theme.ui(8))
        self.status.pack()

        running = self.started_at is not None
        buttons = tk.Frame(body, bg=theme.c("bg"))
        buttons.pack(pady=8)
        self.button = tk.Button(
            buttons, text="STOP" if running else "START", command=self.toggle,
            bg=theme.c("danger") if running else theme.c("accent"),
            fg="#ffffff" if running else theme.c("accent_fg"),
            activebackground=theme.c("danger") if running else theme.c("accent"),
            relief="flat", font=theme.ui(11, "bold"), width=11, pady=4,
            cursor="hand2", highlightthickness=0,
        )
        self.button.pack(side="left")

        # Only meaningful mid-session, so it isn't shown otherwise.
        self.pause_button = tk.Button(
            buttons, text="Resume" if self.paused_at else "Pause",
            command=self.toggle_pause, bg=theme.c("panel"), fg=theme.c("fg"),
            activebackground=theme.c("panel"), activeforeground=theme.c("fg"),
            relief="flat", font=theme.ui(9), width=7, pady=4, cursor="hand2",
            highlightthickness=0,
        )
        if running:
            self.pause_button.pack(side="left", padx=(6, 0))

        self.period_label = tk.Label(body, text="", bg=theme.c("bg"), fg=theme.c("dim"),
                                     font=theme.ui(8))
        self.period_label.pack()

        for widget in (self, bar, body, self.clock, self.status, self.period_label):
            widget.bind("<Button-1>", self.start_drag)
            widget.bind("<B1-Motion>", self.do_drag)

        self.refresh_period_total()
        if running:
            self.tick()

    def _bar_button(self, bar, text, command, font):
        label = tk.Label(bar, text=text, bg=theme.c("panel"), fg=theme.c("dim"),
                         font=font, cursor="hand2")
        label.pack(side="right")
        label.bind("<Button-1>", lambda _e: command())
        label.bind("<Enter>", lambda _e: label.configure(fg=theme.c("fg")))
        label.bind("<Leave>", lambda _e: label.configure(fg=theme.c("dim")))
        return label

    def hold_lock(self):
        """Keep the lock warm, and answer anyone who tried to launch a second copy."""
        core.claim_lock()
        if core.focus_requested():
            self.show_yourself()
        self.lock_job = self.after(core.INSTANCE_POLL_MS, self.hold_lock)

    def show_yourself(self):
        """Come to the front - the answer to a second launch attempt."""
        # Re-asserting topmost is what actually raises it above the window the
        # user was looking at when they double-clicked the launcher.
        self.attributes("-topmost", False)
        self.lift()
        self.attributes("-topmost", True)
        self.status.configure(text="Already running")

    def refresh_period_total(self):
        period = core.period_for(date.today())
        total = core.to_hours(core.period_total_seconds())
        self.period_label.configure(text=f"{core.period_short_label(period)}:  {total} h")

    # --- dragging the window around the desktop ---
    def start_drag(self, event):
        self.drag_origin = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def do_drag(self, event):
        self.geometry(
            f"+{event.x_root - self.drag_origin[0]}+{event.y_root - self.drag_origin[1]}")

    # --- timing ---
    def toggle(self):
        if self.started_at is None:
            self.start()
        else:
            self.stop()

    def worked_now(self, now=None):
        """Seconds worked so far this session, breaks excluded."""
        if self.started_at is None:
            return 0
        upto = self.paused_at or (now or datetime.now())
        return max((upto - self.started_at).total_seconds() - self.paused_seconds, 0)

    def start(self):
        self.started_at = datetime.now()
        self.paused_at = None
        self.paused_seconds = 0
        self.last_heartbeat = self.started_at
        core.mark_running(self.started_at)
        self.button.configure(text="STOP", bg=theme.c("danger"),
                              activebackground=theme.c("danger"), fg="#ffffff")
        self.pause_button.configure(text="Pause")
        self.pause_button.pack(side="left", padx=(6, 0))
        self.status.configure(text=f"Started {self.started_at:%H:%M}")
        self.tick()

    def toggle_pause(self):
        """Step out of a session without ending it, so one event stays one entry."""
        if self.started_at is None:
            return
        now = datetime.now()
        if self.paused_at is None:
            self.paused_at = now
            self.pause_button.configure(text="Resume")
            self.status.configure(text=f"Paused at {now:%H:%M}")
        else:
            self.paused_seconds += (now - self.paused_at).total_seconds()
            self.paused_at = None
            self.pause_button.configure(text="Pause")
            self.status.configure(
                text=f"Resumed - {core.to_minutes(self.paused_seconds)} min on break")
        self.last_heartbeat = now
        core.mark_running(self.started_at, now, self.paused_seconds, self.paused_at)
        self.refresh_clock(now)

    def refresh_clock(self, now=None):
        self.clock.configure(text=core.format_elapsed(self.worked_now(now)))
        # Dimmed while paused, so a glance tells you the clock isn't counting.
        self.clock.configure(fg=theme.c("dim") if self.paused_at else theme.c("fg"))

    def tick(self):
        now = datetime.now()
        self.refresh_clock(now)     # frozen automatically while paused
        # Re-stamp the on-disk marker now and then, so that if this process is
        # killed the recovery prompt knows roughly when the work stopped.
        if (now - self.last_heartbeat).total_seconds() >= core.HEARTBEAT_SECONDS:
            self.last_heartbeat = now
            core.mark_running(self.started_at, now, self.paused_seconds, self.paused_at)
        self.tick_job = self.after(500, self.tick)

    def stop(self):
        if self.tick_job:
            self.after_cancel(self.tick_job)
            self.tick_job = None

        # Stopping while paused: the work really ended when the break began.
        ended_at = self.paused_at or datetime.now()
        started_at, self.started_at = self.started_at, None
        paused_seconds = int(self.paused_seconds)
        self.paused_at, self.paused_seconds = None, 0

        self.button.configure(text="START", bg=theme.c("accent"),
                              activebackground=theme.c("accent"), fg=theme.c("accent_fg"))
        self.pause_button.pack_forget()
        self.clock.configure(text="00:00:00", fg=theme.c("fg"))

        worked = core.worked_seconds(started_at, ended_at, paused_seconds)
        summary = core.format_elapsed(worked)
        if paused_seconds:
            summary += f" (excluding {core.to_minutes(paused_seconds)} min of breaks)"
        dialog = dialogs.EntryDialog(self, summary)
        self.wait_window(dialog)
        if dialog.result is None:
            core.clear_running()   # settled, even though nothing was recorded
            self.status.configure(text="Discarded")
            return

        entry_id, description = dialog.result
        core.log_session(entry_id, description, started_at, ended_at, paused_seconds)
        core.clear_running()
        self.status.configure(text=f"Logged to {entry_id}")
        self.after_change()

    # --- other actions ---
    def welcome(self):
        """First run: get the user's own pay period set before they log anything.

        Otherwise they silently inherit whatever the default happens to be and
        find out a fortnight later that their periods start on the wrong day.
        """
        self.recovery_job = None
        dialog = dialogs.ConfirmDialog(
            self, "Welcome to Work Timer",
            "Press START when you begin working and STOP when you finish, and "
            "your hours are totalled into a markdown file you can invoice from."
            "\n\nFirst, check how your time should be grouped - by default, "
            "fortnightly from this Monday.",
            confirm_text="Choose my settings", confirm_kind="primary",
            cancel_text="Use the defaults")
        self.wait_window(dialog)
        core.save_settings(anchor=core.load_settings()["anchor"])   # stop asking
        if dialog.result:
            self.edit_settings()

    def check_recovered_timer(self):
        """Offer to keep time from a timer that was running when the app died.

        The user can correct both times before saving. Cancelling asks for
        confirmation and, if they decline, leaves the marker in place so the
        offer comes back next launch rather than quietly dropping the time.
        """
        self.recovery_job = None
        found = core.recovered_session()
        if not found:
            return
        started, ended = found["started"], found["ended"]
        breaks = found["paused_seconds"]
        elapsed = core.format_elapsed(core.worked_seconds(started, ended, breaks))

        note = (f"Started {started:%b %d at %H:%M}, still going at "
                f"{ended:%H:%M} ({elapsed}).\n")
        if breaks:
            note += f"A break of {core.to_minutes(breaks)} min is already taken off.\n"
        note += "Correct the times if needed, then give it an ID to keep it."

        dialog = dialogs.ManualDialog(
            self,
            entry={"start": started.isoformat(), "end": ended.isoformat(),
                   "id": "", "description": "", "paused_seconds": breaks},
            title="Recovered timer",
            headline="A timer was still running when the app closed",
            note=note,
            confirm_text="Keep it",
        )
        self.wait_window(dialog)

        if dialog.result is None:
            confirm = dialogs.ConfirmDialog(
                self, "Discard recovered time",
                f"Throw away the {elapsed} from {started:%b %d at %H:%M}?\n\n"
                "Choose Cancel to be asked again next time you open the app.",
                confirm_text="Discard")
            self.wait_window(confirm)
            if confirm.result:
                core.clear_running()
                self.status.configure(text="Recovered time discarded")
            return

        entry_id, description, recovered_start, recovered_end, recovered_break = dialog.result
        core.log_session(entry_id, description, recovered_start, recovered_end,
                         recovered_break)
        core.clear_running()
        self.status.configure(text=f"Recovered to {entry_id}")
        self.after_change()

    def add_manual(self):
        dialog = dialogs.ManualDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        entry_id, description, started_at, ended_at, breaks = dialog.result
        core.log_session(entry_id, description, started_at, ended_at, breaks)
        hours = core.to_hours(core.worked_seconds(started_at, ended_at, breaks))
        self.status.configure(text=f"Added {hours} h to {entry_id}")
        self.after_change()

    def show_log(self):
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.lift()
            self.viewer.focus_force()
            return
        self.viewer = dialogs.LogViewer(self, on_change=self.after_change)

    def edit_settings(self):
        dialog = dialogs.SettingsDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        chosen = dialog.result
        before = core.load_settings()
        core.save_settings(
            frequency=chosen["frequency"], anchor=chosen["anchor"],
            month_start_day=chosen["month_start_day"], theme=chosen["theme"],
            ui_font=chosen["ui_font"], clock_font=chosen["clock_font"],
            start_with_windows=chosen["start_with_windows"],
            groups=chosen["groups"],
        )
        wanted = chosen["start_with_windows"]
        if wanted != core.startup_enabled() and not core.set_startup(wanted):
            self.status.configure(text="Couldn't change the startup setting")

        theme.apply_settings(chosen)
        self.build_ui()   # colours and fonts are read when widgets are built

        # Groups change the totals tables, so the markdown has to be rewritten
        # for them too - not just when the period shape changes.
        regrouped = any(before.get(key) != chosen.get(key)
                        for key in ("frequency", "anchor", "month_start_day", "groups"))
        if regrouped:
            files = core.rebuild_all()
            self.status.configure(
                text=f"Rebuilt {files} file{'' if files == 1 else 's'}")
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.destroy()   # it was built with the old colours
            self.viewer = dialogs.LogViewer(self, on_change=self.after_change)
        self.refresh_period_total()

    def after_change(self):
        """Anything that alters stored entries lands here."""
        self.refresh_period_total()
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.reload_periods()

    def close(self):
        for job in ("recovery_job", "lock_job"):
            pending = getattr(self, job)
            if pending is not None:
                self.after_cancel(pending)     # may still be queued
                setattr(self, job, None)
        if self.started_at is not None:
            self.stop()
        core.save_settings(position=f"+{self.winfo_x()}+{self.winfo_y()}")
        core.release_lock()
        self.destroy()


def main():
    # A second copy would write entries.json behind the first one's back, and
    # the later save would erase the earlier one's work. Hand over instead.
    if core.another_instance_running():
        core.request_focus()
        return
    app = WorkTimer()
    try:
        app.mainloop()
    finally:
        core.release_lock()


if __name__ == "__main__":
    main()
