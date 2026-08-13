# Releasing a new version

Follow this in order. **Step 1 is the one that gets forgotten** — if the version
isn't bumped, everyone reports the same number and you can't tell whose copy is
which.

### 1. Bump the version

Edit `__version__` in [`wt_core.py`](wt_core.py):

```python
__version__ = "1.0.2"
```

Roughly: last number for fixes and small additions, middle number for a
noticeable new feature, first number if something changes in a way that would
surprise an existing user.

It shows in **⚙ → General → About**, and it's what someone will quote when they
report a problem.

### 2. Run the tests

Whatever test scripts you have to hand — at minimum, open the app, log a
session, and check the markdown it writes.

### 3. Build

```
python build_exe.py
```

Produces `dist/WorkTimer.exe`. The build prints the version it stamped — check
it matches step 1.

### 4. Sanity-check the build

Copy `WorkTimer.exe` on its own into an empty folder, run it, log a short
session, and confirm a `Time Logs` folder appears **next to the .exe** with an
`entries.json` and a markdown file in it.

This catches the packaging mistake that matters: if paths ever break, a packaged
build writes its data into a temporary folder that Windows deletes on exit, and
every entry a user logs disappears silently.

### 5. Tag and publish

```
git tag v1.0.2
git push origin main --tags
gh release create v1.0.2 "dist/WorkTimer.exe" --title "Work Timer v1.0.2" --notes "What changed..."
```

Write the notes for someone upgrading: what's new, and a reminder to keep their
existing `Time Logs` folder when they swap the .exe.

### 6. Check it

Open the [releases page](../../releases/latest) and confirm the new version is
marked **Latest** and the `WorkTimer.exe` asset is attached. That link is what
people follow, so it needs to land on the right thing.

---

**Never commit:** `Time Logs/`, `settings.json`, or `dist/`. They're gitignored —
keep them that way. The logs are working data and would name real clients
publicly; the .exe belongs on a release, not in the repository.
