"""Every window other than the timer widget itself: logging a session, adding
or editing time by hand, browsing the log, and settings."""

import os
import tkinter as tk
from datetime import date, datetime, timedelta

import wt_core as core
import wt_theme as theme


# --------------------------------------------------------------------------
# small themed building blocks
# --------------------------------------------------------------------------

def styled_entry(parent, width=34):
    return tk.Entry(
        parent, width=width, bg=theme.c("panel"), fg=theme.c("fg"),
        insertbackground=theme.c("fg"), relief="flat", font=theme.ui(11),
        disabledbackground=theme.c("panel"), highlightthickness=0,
    )


def caption(parent, text, pady=(0, 0), padx=18, **kwargs):
    label = tk.Label(parent, text=text, bg=theme.c("bg"), fg=theme.c("dim"),
                     font=theme.ui(8), justify="left", **kwargs)
    label.pack(padx=padx, pady=pady, anchor="w")
    return label


def styled_dropdown(parent, variable, options, command=None):
    menu = tk.OptionMenu(parent, variable, *options, command=command)
    menu.configure(
        bg=theme.c("panel"), fg=theme.c("fg"), activebackground=theme.c("panel"),
        activeforeground=theme.c("fg"), relief="flat", highlightthickness=0,
        font=theme.ui(10), indicatoron=True, cursor="hand2", anchor="w",
    )
    menu["menu"].configure(
        bg=theme.c("panel"), fg=theme.c("fg"), activebackground=theme.c("accent"),
        activeforeground=theme.c("accent_fg"), relief="flat", font=theme.ui(10),
    )
    return menu


def small_button(parent, text, command, kind="quiet"):
    colours = {
        "primary": (theme.c("accent"), theme.c("accent_fg"), "bold"),
        "danger": (theme.c("danger"), "#ffffff", "bold"),
        "quiet": (theme.c("panel"), theme.c("dim"), "normal"),
    }[kind]
    return tk.Button(
        parent, text=text, command=command, bg=colours[0], fg=colours[1],
        activebackground=colours[0], activeforeground=colours[1], relief="flat",
        font=theme.ui(9, colours[2]), padx=12, pady=4, cursor="hand2",
        highlightthickness=0,
    )


class IdField:
    """The External ID input: a box, the full list of IDs, and live feedback.

    Totals are grouped by ID, so a typo silently creates a second line on the
    invoice. Three things guard against that: buttons for recent IDs, a menu of
    every ID already used, and a note under the box saying what will actually be
    saved - "will be saved as Admin" when the spelling differs, or "new ID" when
    nothing matches, which is what a typo looks like.
    """

    def __init__(self, parent, exclude_uid=None, on_pick=None, current=None):
        self.exclude_uid = exclude_uid
        self.on_pick = on_pick
        # The ID this entry already carries. Left alone it needs no commentary;
        # without this an edit would open saying "new ID" about an ID in use,
        # since the entry is excluded from voting on its own spelling.
        self.current = core.tidy_id(current) if current else None

        caption(parent, "External ID", pady=(10, 0))
        row = tk.Frame(parent, bg=theme.c("bg"))
        row.pack(padx=18, pady=(3, 0), fill="x")

        self.entry = styled_entry(row, width=28)
        self.entry.pack(side="left", ipady=5)
        self.entry.bind("<KeyRelease>", lambda _e: self.update_hint())

        self.all_button = tk.Label(
            row, text="  All IDs ▾  ", bg=theme.c("panel"), fg=theme.c("dim"),
            font=theme.ui(8), cursor="hand2")
        self.all_button.pack(side="left", padx=(6, 0), ipady=6)
        self.all_button.bind("<Button-1>", self._show_all)
        self.all_button.bind("<Enter>", lambda _e: self.all_button.configure(fg=theme.c("fg")))
        self.all_button.bind("<Leave>", lambda _e: self.all_button.configure(fg=theme.c("dim")))

        self.hint = caption(parent, "", pady=(3, 0))

        recents = core.recent_ids()
        if recents:
            shortcuts = tk.Frame(parent, bg=theme.c("bg"))
            shortcuts.pack(padx=18, pady=(4, 0), anchor="w")
            tk.Label(shortcuts, text="Recent:", bg=theme.c("bg"), fg=theme.c("dim"),
                     font=theme.ui(8)).pack(side="left", padx=(0, 6))
            for value in recents:
                tk.Button(
                    shortcuts, text=value, bg=theme.c("panel"), fg=theme.c("fg"),
                    relief="flat", font=theme.ui(8), padx=7, pady=1, cursor="hand2",
                    highlightthickness=0, command=lambda v=value: self.set(v),
                ).pack(side="left", padx=2)

    def _show_all(self, event):
        known = core.all_ids()
        menu = tk.Menu(self.entry, tearoff=0, bg=theme.c("panel"), fg=theme.c("fg"),
                       activebackground=theme.c("accent"),
                       activeforeground=theme.c("accent_fg"),
                       font=theme.ui(9), relief="flat", borderwidth=0)
        if not known:
            menu.add_command(label="Nothing logged yet", state="disabled")
        for name, seconds in known:
            menu.add_command(label=f"{name}    {core.to_hours(seconds)} h",
                             command=lambda v=name: self.set(v))
        menu.tk_popup(event.x_root, event.y_root)

    def get(self):
        return self.entry.get().strip()

    def set(self, value):
        self.entry.delete(0, "end")
        self.entry.insert(0, value)
        self.update_hint()
        if self.on_pick:
            self.on_pick()

    def update_hint(self):
        typed = self.get()
        if not typed or typed == self.current:
            self.hint.configure(text="", fg=theme.c("dim"))
            return
        canonical = core.canonical_id(typed, exclude_uid=self.exclude_uid)
        if core.is_new_id(typed, exclude_uid=self.exclude_uid):
            self.hint.configure(text="New ID - nothing logged under this before",
                                fg=theme.c("dim"))
        elif canonical != typed:
            self.hint.configure(text=f"Will be saved as \"{canonical}\"",
                                fg=theme.c("accent"))
        else:
            self.hint.configure(text="", fg=theme.c("dim"))


class Dialog(tk.Toplevel):
    """Shared frame: themed, on top, positioned near its parent, modal."""

    def __init__(self, master, title):
        super().__init__(master)
        self.result = None
        self.title(title)
        self.configure(bg=theme.c("bg"))
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _buttons(self, cancel_text, confirm_text, confirm_kind="primary"):
        row = tk.Frame(self, bg=theme.c("bg"))
        row.pack(padx=18, pady=16, fill="x")
        small_button(row, cancel_text, self._cancel).pack(side="left")
        small_button(row, confirm_text, self._save, confirm_kind).pack(side="right")
        return row

    def _place(self, master):
        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + master.winfo_height() + 10
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()

    def _flash(self, widget):
        widget.configure(bg=theme.c("invalid"))
        widget.focus_set()
        self.after(400, lambda: widget.configure(bg=theme.c("panel")))

    def _save(self):
        raise NotImplementedError

    def _cancel(self):
        self.result = None
        self.destroy()


class ConfirmDialog(Dialog):
    """A yes/no question, themed to match everything else."""

    def __init__(self, master, title, message, confirm_text="Delete",
                 confirm_kind="danger", cancel_text="Cancel"):
        super().__init__(master, title)
        tk.Label(
            self, text=message, bg=theme.c("bg"), fg=theme.c("fg"),
            font=theme.ui(10), justify="left", wraplength=340,
        ).pack(padx=18, pady=(18, 4), anchor="w")
        self._buttons(cancel_text, confirm_text, confirm_kind)
        self._place(master)

    def _save(self):
        self.result = True
        self.destroy()


# --------------------------------------------------------------------------
# logging a timed session
# --------------------------------------------------------------------------

class EntryDialog(Dialog):
    """Asks for the external ID and description of a finished session."""

    def __init__(self, master, elapsed_text):
        super().__init__(master, "Log this work session")

        tk.Label(
            self, text=f"Worked {elapsed_text}", bg=theme.c("bg"), fg=theme.c("fg"),
            font=theme.ui(11, "bold"),
        ).pack(padx=18, pady=(16, 12), anchor="w")

        self.id_field = IdField(self, on_pick=lambda: self.desc_entry.focus_set())
        self.id_field.entry.focus_set()

        caption(self, "Description (optional)", pady=(12, 0))
        self.desc_entry = styled_entry(self)
        self.desc_entry.pack(padx=18, pady=(3, 0), ipady=5)

        self._buttons("Discard", "Save")
        self._place(master)

    def _save(self):
        entry_id = self.id_field.get()
        if not entry_id:
            self._flash(self.id_field.entry)
            return
        self.result = (entry_id, self.desc_entry.get().strip())
        self.destroy()


# --------------------------------------------------------------------------
# adding or editing time by hand
# --------------------------------------------------------------------------

class ManualDialog(Dialog):
    """Adds time you forgot to track, or edits an entry that's already logged."""

    def __init__(self, master, entry=None, title=None, headline=None,
                 note=None, confirm_text=None):
        editing = entry is not None
        super().__init__(
            master, title or ("Edit entry" if editing else "Add time manually"))
        self.entry = entry

        tk.Label(
            self,
            text=headline or ("Edit this entry" if editing
                              else "Add time you forgot to track"),
            bg=theme.c("bg"), fg=theme.c("fg"), font=theme.ui(11, "bold"),
        ).pack(padx=18, pady=(16, 4 if note else 12), anchor="w")
        if note:
            caption(self, note, pady=(0, 10))

        when = tk.Frame(self, bg=theme.c("bg"))
        when.pack(padx=18, anchor="w")
        self.date_entry = self._when_field(when, "Date", 12, 0, "today")
        self.start_entry = self._when_field(when, "Start", 8, 1)
        self.end_entry = self._when_field(when, "End", 8, 2)

        # Shown only when there is a break to account for, so adding ordinary
        # time by hand stays a three-field job.
        existing_break = int((entry or {}).get("paused_seconds", 0))
        self.break_entry = None
        if existing_break:
            self.break_entry = self._when_field(when, "Break (min)", 9, 3)
            self._fill(self.break_entry, f"{core.to_minutes(existing_break):g}")

        self.preview = caption(self, "", pady=(8, 0))

        self.id_field = IdField(
            self, exclude_uid=(entry or {}).get("uid"),
            current=(entry or {}).get("id"),
            on_pick=lambda: self.desc_entry.focus_set())

        caption(self, "Description (optional)", pady=(12, 0))
        self.desc_entry = styled_entry(self)
        self.desc_entry.pack(padx=18, pady=(3, 0), ipady=5)

        if editing:
            started = datetime.fromisoformat(entry["start"])
            ended = datetime.fromisoformat(entry["end"])
            self._fill(self.date_entry, started.strftime("%Y-%m-%d"))
            self._fill(self.start_entry, started.strftime("%H:%M"))
            self._fill(self.end_entry, ended.strftime("%H:%M"))
            self._fill(self.id_field.entry, entry["id"])
            self._fill(self.desc_entry, entry.get("description", ""))
            self.id_field.update_hint()

        self._buttons("Cancel", confirm_text or ("Save" if editing else "Add"))
        self.date_entry.focus_set()
        self._place(master)
        self._update_preview()

    @staticmethod
    def _fill(entry, value):
        entry.delete(0, "end")
        entry.insert(0, value)

    def _when_field(self, parent, label, width, column, initial=""):
        tk.Label(parent, text=label, bg=theme.c("bg"), fg=theme.c("dim"),
                 font=theme.ui(8)).grid(row=0, column=column, sticky="w", padx=(0, 6))
        entry = styled_entry(parent, width=width)
        entry.grid(row=1, column=column, sticky="w", padx=(0, 6), ipady=5)
        entry.insert(0, initial)
        entry.bind("<KeyRelease>", lambda _e: self._update_preview())
        return entry

    def _read_break(self):
        """Break minutes as typed. Blank means none; anything else must be a number."""
        if self.break_entry is None:
            return 0
        raw = self.break_entry.get().strip()
        if not raw:
            return 0
        try:
            minutes = float(raw)
        except ValueError:
            raise core.ParseError(f"Can't read the break '{raw}' - use minutes, e.g. 20")
        if minutes < 0:
            raise core.ParseError("A break can't be negative")
        return int(round(minutes * 60))

    def _read(self):
        started, ended, crossed = core.build_span(
            self.date_entry.get(), self.start_entry.get(), self.end_entry.get())
        breaks = self._read_break()
        if breaks > (ended - started).total_seconds():
            raise core.ParseError("The break is longer than the session")
        return started, ended, crossed, breaks

    def _update_preview(self):
        """Show the computed duration live, so a typo is obvious before saving."""
        try:
            started, ended, crossed, breaks = self._read()
        except core.ParseError as problem:
            blank = not (self.start_entry.get().strip() and self.end_entry.get().strip())
            self.preview.configure(
                text="e.g. 9:30 and 11am, or 14:00 and 15:30" if blank else str(problem),
                fg=theme.c("dim") if blank else theme.c("danger"))
            return
        seconds = core.worked_seconds(started, ended, breaks)
        note = "  (overnight, ends next day)" if crossed else ""
        if breaks:
            note = f"  (break of {core.to_minutes(breaks)} min removed){note}"
        self.preview.configure(
            text=f"= {core.to_hours(seconds)} h  ({core.to_minutes(seconds)} min){note}",
            fg=theme.c("fg"))

    def _save(self):
        try:
            started, ended, _, breaks = self._read()
        except core.ParseError as problem:
            self.preview.configure(text=str(problem), fg=theme.c("danger"))
            if self.break_entry is not None and "break" in str(problem).lower():
                self._flash(self.break_entry)
            else:
                self._flash(
                    self.end_entry if self.start_entry.get().strip() else self.start_entry)
            return
        entry_id = self.id_field.get()
        if not entry_id:
            self._flash(self.id_field.entry)
            return
        self.result = (entry_id, self.desc_entry.get().strip(), started, ended, breaks)
        self.destroy()


# --------------------------------------------------------------------------
# browsing and correcting the log
# --------------------------------------------------------------------------

class LogViewer(tk.Toplevel):
    """Lists logged entries for one period, with edit and delete on each row."""

    # Description takes whatever space is left; the rest are fixed, and the
    # buttons claim their room first so they can never be clipped away.
    DATE_W, TIME_W, ID_W, HOURS_W, ACTIONS_W = 11, 19, 14, 8, 13

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change
        self.periods = []

        settings = core.load_settings()
        self.sort_key = settings.get("sort_by", "date")
        if self.sort_key not in ("date", "id", "description", "hours"):
            self.sort_key = "date"
        self.sort_desc = bool(settings.get("sort_desc", True))

        self.title("Work log")
        self.configure(bg=theme.c("bg"))
        self.geometry("800x460")
        self.minsize(700, 320)
        self.attributes("-topmost", True)
        self.transient(master)

        header = tk.Frame(self, bg=theme.c("bg"))
        header.pack(fill="x", padx=16, pady=(14, 0))
        tk.Label(header, text="Showing", bg=theme.c("bg"), fg=theme.c("dim"),
                 font=theme.ui(8)).pack(side="left", padx=(0, 8))
        self.period_choice = tk.StringVar()
        self.period_menu = styled_dropdown(
            header, self.period_choice, ["All time"], command=lambda _v: self.refresh())
        self.period_menu.pack(side="left")
        small_button(header, "+ Add time", self.add_entry, "primary").pack(side="right")
        self.copy_button = small_button(header, "Copy totals", self.copy_totals)
        self.copy_button.pack(side="right", padx=(0, 8))

        self.summary = tk.Label(self, text="", bg=theme.c("bg"), fg=theme.c("fg"),
                                font=theme.ui(10, "bold"))
        self.summary.pack(anchor="w", padx=16, pady=(10, 6))

        columns = tk.Frame(self, bg=theme.c("panel"))
        columns.pack(fill="x", padx=16)
        self.headings = {}

        def heading(text, width, key=None, side="left", anchor="w", expand=False):
            label = tk.Label(columns, text=text, bg=theme.c("panel"),
                             fg=theme.c("dim"), font=theme.ui(8, "bold"),
                             anchor=anchor, padx=4, pady=4,
                             **({} if expand else {"width": width}))
            label.pack(side=side, **({"fill": "x", "expand": True} if expand else {}))
            if key:
                label.configure(cursor="hand2")
                label.bind("<Button-1>", lambda _e, k=key: self.sort_by(k))
                # Date and Time both sort on the same value, so a key can own
                # more than one heading.
                self.headings.setdefault(key, []).append((label, text))
            return label

        # Packed in the same order as the rows below, so the columns line up.
        heading("Date", self.DATE_W, "date")
        heading("Time", self.TIME_W, "date")
        heading("ID", self.ID_W, "id")
        heading("", self.ACTIONS_W, side="right")
        heading("Hours", self.HOURS_W, "hours", side="right", anchor="e")
        heading("Description", None, "description", expand=True)

        # Scrollable body: a canvas holding one frame of rows.
        holder = tk.Frame(self, bg=theme.c("bg"))
        holder.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        self.canvas = tk.Canvas(holder, bg=theme.c("bg"), highlightthickness=0)
        scrollbar = tk.Scrollbar(
            holder, orient="vertical", command=self.canvas.yview, relief="flat",
            bg=theme.c("panel"), troughcolor=theme.c("bg"), activebackground=theme.c("dim"),
            borderwidth=0, highlightthickness=0, width=12,
        )
        self.rows = tk.Frame(self.canvas, bg=theme.c("bg"))
        self.window_id = self.canvas.create_window((0, 0), window=self.rows, anchor="nw")

        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.rows.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self.window_id, width=e.width))
        self.bind_all("<MouseWheel>", self._scroll)

        footer = tk.Frame(self, bg=theme.c("bg"))
        footer.pack(fill="x", padx=16, pady=(0, 14))
        self.hint = tk.Label(footer, text="", bg=theme.c("bg"), fg=theme.c("dim"),
                             font=theme.ui(8))
        self.hint.pack(side="left")
        small_button(footer, "Close", self.close).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.reload_periods()
        self.geometry(f"+{master.winfo_rootx()}+{master.winfo_rooty() + 40}")

    # --- data ---
    def reload_periods(self):
        """Rebuild the period dropdown, keeping the current choice if it survives."""
        settings = core.load_settings()
        self.periods = core.known_periods(settings)
        today = core.period_for(date.today(), settings)
        if today is not None and today not in self.periods:
            self.periods.insert(0, today)

        labels = ["All time"] + [
            core.period_heading(p, settings) for p in self.periods if p is not None]
        previous = self.period_choice.get()
        menu = self.period_menu["menu"]
        menu.delete(0, "end")
        for label in labels:
            menu.add_command(label=label,
                             command=lambda v=label: (self.period_choice.set(v), self.refresh()))
        if previous not in labels:
            # Default to the period we are in now, not merely the latest one -
            # they differ as soon as anything is logged with a future date.
            current = core.period_heading(today, settings) if today else None
            previous = (current if current in labels
                        else (labels[1] if len(labels) > 1 else "All time"))
        self.period_choice.set(previous)
        self.refresh()

    def _selected_period(self):
        chosen = self.period_choice.get()
        if chosen == "All time":
            return None, True
        settings = core.load_settings()
        for period in self.periods:
            if period is not None and core.period_heading(period, settings) == chosen:
                return period, False
        return None, True

    # Which way round each column starts when you first click it: newest and
    # longest first, but names A to Z.
    SORT_DEFAULT_DESC = {"date": True, "hours": True, "id": False, "description": False}

    def _sort_value(self, entry):
        """The value to order by. Ties fall back to the start time, so that
        entries sharing an ID stay in a sensible order within their group."""
        if self.sort_key == "id":
            return (entry["id"].lower(), entry["start"])
        if self.sort_key == "description":
            return (entry.get("description", "").lower(), entry["start"])
        if self.sort_key == "hours":
            return (entry["seconds"], entry["start"])
        return (entry["start"],)

    def sort_by(self, key):
        """Clicking a heading sorts by it; clicking the active one reverses."""
        if key == self.sort_key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key = key
            self.sort_desc = self.SORT_DEFAULT_DESC.get(key, True)
        core.save_settings(sort_by=self.sort_key, sort_desc=self.sort_desc)
        self.refresh()

    def _mark_sorted_heading(self):
        arrow = " ▾" if self.sort_desc else " ▴"
        for key, labels in self.headings.items():
            active = key == self.sort_key
            for label, text in labels:
                label.configure(text=text + (arrow if active and text else ""),
                                fg=theme.c("fg") if active else theme.c("dim"))

    def _visible_entries(self):
        period, everything = self._selected_period()
        entries = core.load_entries()
        if not everything:
            entries = core.entries_in_period(entries, period)
        return sorted(entries, key=self._sort_value, reverse=self.sort_desc)

    # --- drawing ---
    def refresh(self):
        for child in self.rows.winfo_children():
            child.destroy()
        self._mark_sorted_heading()

        entries = self._visible_entries()
        total = sum(e["seconds"] for e in entries)
        self.summary.configure(
            text=f"{core.to_hours(total)} hours  ({core.to_minutes(total)} minutes)  -  "
                 f"{len(entries)} {'entry' if len(entries) == 1 else 'entries'}")

        if not entries:
            tk.Label(self.rows, text="Nothing logged here yet.", bg=theme.c("bg"),
                     fg=theme.c("dim"), font=theme.ui(9)).pack(anchor="w", padx=6, pady=14)
            self.hint.configure(text="")
            return

        self.hint.configure(
            text="Click a column heading to sort.  "
                 "Edit fixes a mistake; Delete removes the entry entirely.")
        for index, entry in enumerate(entries):
            self._draw_row(entry, index)

    def _draw_row(self, entry, index):
        started = datetime.fromisoformat(entry["start"])
        ended = datetime.fromisoformat(entry["end"])
        # A shaded band on alternate rows, so long lists stay readable.
        background = theme.c("bg") if index % 2 else theme.c("panel")

        row = tk.Frame(self.rows, bg=background)
        row.pack(fill="x")
        overnight = " +1" if ended.date() > started.date() else ""

        def cell(text, width, side="left", anchor="w"):
            tk.Label(row, text=text, bg=background, fg=theme.c("fg"), font=theme.ui(9),
                     width=width, anchor=anchor, padx=4, pady=5).pack(side=side)

        paused = entry.get("paused_seconds", 0)
        # The span alone would overstate the time, so the break is called out.
        break_note = f" -{core.to_minutes(paused):g}m" if paused else ""
        cell(f"{started:%Y-%m-%d}", self.DATE_W)
        cell(f"{started:%H:%M}-{ended:%H:%M}{overnight}{break_note}", self.TIME_W)
        cell(entry["id"], self.ID_W)

        # Buttons before the flexible description, so a long note can never
        # push them off the edge of the window.
        tk.Button(row, text="Delete", bg=background, fg=theme.c("danger"), relief="flat",
                  font=theme.ui(8), padx=6, cursor="hand2", highlightthickness=0,
                  activebackground=background, activeforeground=theme.c("danger"),
                  command=lambda e=entry: self.delete_entry(e)).pack(side="right", padx=(0, 4))
        tk.Button(row, text="Edit", bg=background, fg=theme.c("dim"), relief="flat",
                  font=theme.ui(8), padx=6, cursor="hand2", highlightthickness=0,
                  activebackground=background, activeforeground=theme.c("fg"),
                  command=lambda e=entry: self.edit_entry(e)).pack(side="right")
        cell(f"{core.to_hours(entry['seconds'])}", self.HOURS_W, "right", "e")

        tk.Label(row, text=entry.get("description", ""), bg=background, fg=theme.c("fg"),
                 font=theme.ui(9), anchor="w", padx=4, pady=5
                 ).pack(side="left", fill="x", expand=True)

    def _scroll(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    # --- actions ---
    def totals_text(self):
        """The shown period's totals per ID, tab separated.

        Tabs so it drops straight into a spreadsheet cell-by-cell, while still
        reading fine if pasted somewhere plain.
        """
        totals = {}
        for entry in self._visible_entries():
            totals[entry["id"]] = totals.get(entry["id"], 0) + entry["seconds"]
        grand = sum(totals.values())

        heading = self.period_choice.get()
        lines = [heading, "", "ID\tHours\tMinutes"]
        for name in sorted(totals, key=lambda n: n.lower()):
            seconds = totals[name]
            lines.append(f"{name}\t{core.to_hours(seconds)}\t{core.to_minutes(seconds)}")
        lines.append(f"Total\t{core.to_hours(grand)}\t{core.to_minutes(grand)}")
        return "\n".join(lines)

    def copy_totals(self):
        text = self.totals_text()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()          # hand it to Windows now, not when the app closes
        self.copy_button.configure(text="Copied")
        self.after(1200, lambda: self.copy_button.configure(text="Copy totals"))

    def add_entry(self):
        dialog = ManualDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        entry_id, description, started, ended, breaks = dialog.result
        core.log_session(entry_id, description, started, ended, breaks)
        self._changed()

    def edit_entry(self, entry):
        dialog = ManualDialog(self, entry=entry)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        entry_id, description, started, ended, breaks = dialog.result
        core.update_entry(entry["uid"], entry_id, description, started, ended, breaks)
        self._changed()

    def delete_entry(self, entry):
        started = datetime.fromisoformat(entry["start"])
        description = entry.get("description") or "no description"
        dialog = ConfirmDialog(
            self, "Delete entry",
            f"Delete {core.to_hours(entry['seconds'])} h on {entry['id']}"
            f" from {started:%b %d}?\n({description})\n\nThis can't be undone.")
        self.wait_window(dialog)
        if dialog.result:
            core.delete_entry(entry["uid"])
            self._changed()

    def _changed(self):
        # The owner refreshes this window as part of its own update, so only
        # reload directly when running without one.
        if self.on_change:
            self.on_change()
        else:
            self.reload_periods()

    def close(self):
        self.unbind_all("<MouseWheel>")
        self.destroy()


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------

class SettingsDialog(Dialog):
    """Two tabs: how time is grouped into files, and how the app looks."""

    def __init__(self, master):
        super().__init__(master, "Settings")
        self.settings = core.load_settings()

        tabs = tk.Frame(self, bg=theme.c("bg"))
        tabs.pack(padx=18, pady=(14, 0), anchor="w")
        self.tab_buttons = {}
        for name in ("Log grouping", "Appearance", "General"):
            button = tk.Label(tabs, text=f"  {name}  ", bg=theme.c("bg"),
                              fg=theme.c("dim"), font=theme.ui(9), cursor="hand2",
                              pady=4)
            button.pack(side="left")
            button.bind("<Button-1>", lambda _e, n=name: self._show_tab(n))
            self.tab_buttons[name] = button

        self.pages = tk.Frame(self, bg=theme.c("bg"))
        self.pages.pack(fill="both", expand=True)
        self.grouping_page = tk.Frame(self.pages, bg=theme.c("bg"))
        self.appearance_page = tk.Frame(self.pages, bg=theme.c("bg"))
        self.general_page = tk.Frame(self.pages, bg=theme.c("bg"))

        # The preview line and buttons are packed before the pages are filled in,
        # so they sit at the bottom and exist for the first preview update.
        self.preview = caption(self, "", pady=(12, 0))
        self._buttons("Cancel", "Save")

        # Appearance and General first: the grouping page's live preview reads
        # values from both while it builds.
        self._build_appearance(self.appearance_page)
        self._build_general(self.general_page)
        self._build_grouping(self.grouping_page)

        self._show_tab("Log grouping")
        self._place(master)

    # --- tabs ---
    def _show_tab(self, name):
        pages = {"Log grouping": self.grouping_page,
                 "Appearance": self.appearance_page,
                 "General": self.general_page}
        for page in pages.values():
            page.pack_forget()
        for label, button in self.tab_buttons.items():
            chosen = label == name
            button.configure(fg=theme.c("fg") if chosen else theme.c("dim"),
                             bg=theme.c("panel") if chosen else theme.c("bg"),
                             font=theme.ui(9, "bold" if chosen else "normal"))
        pages[name].pack(fill="both", expand=True, pady=(10, 0))
        self._update_preview()

    # --- grouping tab ---
    def _build_grouping(self, page):
        caption(page, "New log file starts")
        self.frequency_label = tk.StringVar(
            value=core.FREQUENCIES[self.settings.get("frequency", "biweekly")])
        styled_dropdown(page, self.frequency_label, list(core.FREQUENCIES.values()),
                        command=lambda _v: self._frequency_changed()
                        ).pack(padx=18, pady=(3, 0), fill="x")

        # Only one of these is shown at a time, depending on the frequency.
        self.detail = tk.Frame(page, bg=theme.c("bg"))
        self.detail.pack(pady=(12, 0), fill="x")

        self.weekday_label = tk.StringVar(
            value=core.WEEKDAYS[core.anchor_date(self.settings).weekday()])
        self.anchor_entry = None
        self.month_day_label = tk.StringVar(value=str(core.month_start_day(self.settings)))
        self._frequency_changed()

    def _frequency(self):
        chosen = self.frequency_label.get()
        for key, label in core.FREQUENCIES.items():
            if label == chosen:
                return key
        return "biweekly"

    def _frequency_changed(self):
        for child in self.detail.winfo_children():
            child.destroy()
        frequency = self._frequency()
        self.anchor_entry = None

        if frequency == "none":
            caption(self.detail, "Everything goes into one file, \"All Time.md\",\n"
                                 "until you change this setting.")
        elif frequency == "daily":
            caption(self.detail, "A new file for each day you log time.")
        elif frequency == "weekly":
            caption(self.detail, "Week starts on")
            styled_dropdown(self.detail, self.weekday_label, core.WEEKDAYS,
                            command=lambda _v: self._update_preview()
                            ).pack(padx=18, pady=(3, 0), fill="x")
        elif frequency == "biweekly":
            caption(self.detail, "A period starts on this date")
            self.anchor_entry = styled_entry(self.detail, width=16)
            self.anchor_entry.pack(padx=18, pady=(3, 0), anchor="w", ipady=5)
            self.anchor_entry.insert(0, core.anchor_date(self.settings).isoformat())
            self.anchor_entry.bind("<KeyRelease>", lambda _e: self._update_preview())
            caption(self.detail, "Every other week counts from here, forwards and back.",
                    pady=(4, 0))
        elif frequency == "monthly":
            caption(self.detail, "Month starts on day")
            styled_dropdown(self.detail, self.month_day_label,
                            [str(d) for d in range(1, 29)],
                            command=lambda _v: self._update_preview()
                            ).pack(padx=18, pady=(3, 0), fill="x")

        self._update_preview()

    # --- appearance tab ---
    def _build_appearance(self, page):
        fonts = theme.available_fonts()

        caption(page, "Colours")
        self.theme_label = tk.StringVar(
            value=theme.label_for_key(self.settings.get("theme", theme.DEFAULT_THEME)))
        styled_dropdown(page, self.theme_label, theme.theme_labels(),
                        command=lambda _v: self._update_swatch()
                        ).pack(padx=18, pady=(3, 0), fill="x")

        caption(page, "Interface font", pady=(12, 0))
        self.ui_font_label = tk.StringVar(
            value=self.settings.get("ui_font", theme.DEFAULT_UI_FONT))
        styled_dropdown(page, self.ui_font_label, fonts,
                        command=lambda _v: self._update_swatch()
                        ).pack(padx=18, pady=(3, 0), fill="x")

        caption(page, "Clock font", pady=(12, 0))
        self.clock_font_label = tk.StringVar(
            value=self.settings.get("clock_font", theme.DEFAULT_CLOCK_FONT))
        styled_dropdown(page, self.clock_font_label, fonts,
                        command=lambda _v: self._update_swatch()
                        ).pack(padx=18, pady=(3, 0), fill="x")

        caption(page, "Preview", pady=(14, 0))
        self.swatch = tk.Frame(page, highlightthickness=1)
        self.swatch.pack(padx=18, pady=(4, 0), fill="x")
        self.swatch_clock = tk.Label(self.swatch, text="01:44:30", font=theme.clock(20))
        self.swatch_clock.pack(pady=(10, 0))
        self.swatch_text = tk.Label(self.swatch, text="SD-4471  -  1.74 h", font=theme.ui(9))
        self.swatch_text.pack()
        self.swatch_button = tk.Label(self.swatch, text="  START  ", font=theme.ui(10, "bold"))
        self.swatch_button.pack(pady=(6, 12))
        self._update_swatch()

    def _update_swatch(self):
        chosen = theme.THEMES[theme.key_for_label(self.theme_label.get())]
        ui_font = (self.ui_font_label.get(), 9)
        self.swatch.configure(bg=chosen["bg"], highlightbackground=chosen["panel"])
        self.swatch_clock.configure(bg=chosen["bg"], fg=chosen["fg"],
                                    font=(self.clock_font_label.get(), 20, "bold"))
        self.swatch_text.configure(bg=chosen["bg"], fg=chosen["dim"], font=ui_font)
        self.swatch_button.configure(bg=chosen["accent"], fg=chosen["accent_fg"],
                                     font=(self.ui_font_label.get(), 10, "bold"))

    # --- general tab ---
    def _build_general(self, page):
        caption(page, "Startup")
        self.startup_choice = tk.BooleanVar(value=core.startup_enabled())
        tk.Checkbutton(
            page, text=" Start Work Timer when I sign in to Windows",
            variable=self.startup_choice, bg=theme.c("bg"), fg=theme.c("fg"),
            activebackground=theme.c("bg"), activeforeground=theme.c("fg"),
            selectcolor=theme.c("panel"), relief="flat", font=theme.ui(9),
            highlightthickness=0, borderwidth=0, cursor="hand2", anchor="w",
        ).pack(padx=16, pady=(4, 0), anchor="w")
        caption(page, "Off unless you turn it on. Adds a small launcher to your\n"
                      "Windows Startup folder, and removes it when unticked.",
                pady=(6, 0))

        # The two things anyone asks first when something looks wrong: which
        # version is this, and where does it keep my hours?
        caption(page, "About", pady=(18, 0))
        tk.Label(page, text=f"Work Timer v{core.__version__}", bg=theme.c("bg"),
                 fg=theme.c("fg"), font=theme.ui(9)).pack(padx=18, pady=(3, 0), anchor="w")

        folder = tk.Frame(page, bg=theme.c("bg"))
        folder.pack(padx=18, pady=(6, 0), anchor="w", fill="x")
        tk.Label(folder, text="Your logs are in", bg=theme.c("bg"), fg=theme.c("dim"),
                 font=theme.ui(8)).pack(side="left", padx=(0, 6))
        open_link = tk.Label(folder, text="  Open folder  ", bg=theme.c("panel"),
                             fg=theme.c("dim"), font=theme.ui(8), cursor="hand2")
        open_link.pack(side="left")
        open_link.bind("<Button-1>", lambda _e: self._open_data_folder())
        open_link.bind("<Enter>", lambda _e: open_link.configure(fg=theme.c("fg")))
        open_link.bind("<Leave>", lambda _e: open_link.configure(fg=theme.c("dim")))
        caption(page, str(core.LOG_DIR), pady=(4, 0), wraplength=320)

    def _open_data_folder(self):
        try:
            core.LOG_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(core.LOG_DIR)      # noqa: S606 - opening a folder in Explorer
        except Exception:
            pass

    # --- shared ---
    def _pending(self):
        """The settings as currently filled in, without saving them."""
        frequency = self._frequency()
        settings = dict(self.settings, frequency=frequency,
                        theme=theme.key_for_label(self.theme_label.get()),
                        ui_font=self.ui_font_label.get(),
                        clock_font=self.clock_font_label.get(),
                        start_with_windows=bool(self.startup_choice.get()))

        if frequency == "weekly":
            today = date.today()
            wanted = core.WEEKDAYS.index(self.weekday_label.get())
            settings["anchor"] = (
                today - timedelta(days=(today.weekday() - wanted) % 7)).isoformat()
        elif frequency == "biweekly" and self.anchor_entry is not None:
            settings["anchor"] = core.parse_date(self.anchor_entry.get()).isoformat()
        elif frequency == "monthly":
            settings["month_start_day"] = int(self.month_day_label.get())
        return settings

    def _update_preview(self):
        try:
            settings = self._pending()
        except core.ParseError as problem:
            self.preview.configure(text=str(problem), fg=theme.c("danger"))
            return
        period = core.period_for(date.today(), settings)
        if period is None:
            self.preview.configure(text="Current file:  All Time.md", fg=theme.c("fg"))
        else:
            self.preview.configure(
                text=f"Current period:  {period[0]:%b %d, %Y} to {period[1]:%b %d, %Y}",
                fg=theme.c("fg"))

    def _save(self):
        try:
            settings = self._pending()
        except core.ParseError as problem:
            self._show_tab("Log grouping")
            self.preview.configure(text=str(problem), fg=theme.c("danger"))
            if self.anchor_entry is not None:
                self._flash(self.anchor_entry)
            return
        self.result = settings
        self.destroy()
