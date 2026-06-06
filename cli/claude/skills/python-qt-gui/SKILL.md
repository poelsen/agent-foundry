---
name: python-qt-gui
description: Python/Qt-specific implementations for multithreaded GUI applications using PySide6, QThreadPool, frozen dataclasses, and QDockWidget layouts.
extends: gui-threading
---

# Python/Qt GUI Patterns

Python/Qt-specific implementations extending the base `gui-threading` skill.

**Prerequisite:** Read `.claude/skills/gui-threading/SKILL.md` first.

## Key References

- KDAB "Eight Rules of Multithreaded Qt": https://www.kdab.com/the-eight-rules-of-multithreaded-qt/
- Qt 6 QThreadPool: https://doc.qt.io/qt-6/qthreadpool.html
- Python dataclasses: https://docs.python.org/3/library/dataclasses.html
- Qt Reentrancy: https://doc.qt.io/qt-6/threads-reentrancy.html

---

## Pattern 1: QThreadPool + QRunnable

**Reference:** Qt 6 docs, KDAB Rule #7

### Structure

```python
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class JobSignals(QObject):
    """Signals for thread-safe communication from worker to UI."""
    finished = Signal(object)  # Emits result
    error = Signal(str)        # Emits error message
    progress = Signal(int)     # Emits percentage (0-100)


class BackgroundJob(QRunnable):
    """Base class for background work."""

    def __init__(self) -> None:
        super().__init__()
        self.signals = JobSignals()
        self._cancelled = False
        self.setAutoDelete(True)  # Qt cleans up after completion

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        """Called by QThreadPool. Override execute(), not this."""
        if self.is_cancelled:
            return

        try:
            result = self.execute()
            if not self.is_cancelled:
                self.signals.finished.emit(result)
        except Exception as e:
            if not self.is_cancelled:
                self.signals.error.emit(str(e))

    def execute(self) -> object:
        """Subclasses implement this. Returns result or raises."""
        raise NotImplementedError


# Usage
class FetchDataJob(BackgroundJob):
    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def execute(self) -> dict:
        import urllib.request
        with urllib.request.urlopen(self.url) as response:
            return json.loads(response.read())


# In controller
job = FetchDataJob("https://api.example.com/data")
job.signals.finished.connect(self._on_data_received)
job.signals.error.connect(self._on_error)
QThreadPool.globalInstance().start(job)
```

### KDAB Rule #7: Worker Objects

*"Avoid adding slots to QThread subclasses - use worker objects."*

- Do NOT subclass QThread
- Use QRunnable (worker objects) + QThreadPool
- Workers have no thread affinity issues

---

## Pattern 2: Controller with Debounce Timer

### Structure

```python
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication


class RepoController(QObject):
    """Single controller owns all state and coordinates jobs."""

    # Signals for views to connect
    status_changed = Signal(object)  # Emits RepoStatusSnapshot
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        # Cached state
        self._status: RepoStatusSnapshot | None = None
        self._pending_job: BackgroundJob | None = None

        # Debounce timer for filesystem events
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(100)  # 100ms debounce
        self._debounce_timer.timeout.connect(self._do_refresh)

    @property
    def status(self) -> RepoStatusSnapshot | None:
        """Current cached status. Views read this."""
        return self._status

    def request_refresh(self) -> None:
        """Request a refresh. Debounced to prevent flooding."""
        self._debounce_timer.start()

    def _do_refresh(self) -> None:
        """Actually perform refresh. Cancel-before-new pattern."""
        # Cancel pending job
        if self._pending_job is not None:
            self._pending_job.cancel()

        # Start new job
        job = StatusJob(self._repo_path)
        job.signals.finished.connect(self._on_status_received)
        job.signals.error.connect(self._on_error)

        self._pending_job = job
        QThreadPool.globalInstance().start(job)

    def _on_status_received(self, snapshot: RepoStatusSnapshot) -> None:
        """Handle result from background job."""
        self._status = snapshot
        self._pending_job = None
        self.status_changed.emit(snapshot)

    def _on_error(self, message: str) -> None:
        self._pending_job = None
        self.error_occurred.emit(message)
```

---

## Pattern 3: Immutable Snapshots with Frozen Dataclasses

**Reference:** Python docs, MIT thread safety

### Structure

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class StatusEntry:
    """Single file status. Immutable."""
    path: str
    status: str  # 'M', 'A', 'D', '?', etc.


@dataclass(frozen=True)
class RepoStatusSnapshot:
    """Complete repository status at a point in time. Immutable."""
    head: str = ""
    branch: str = ""
    staged: tuple[StatusEntry, ...] = ()      # tuple, not list!
    unstaged: tuple[StatusEntry, ...] = ()
    untracked: tuple[StatusEntry, ...] = ()
    timestamp: float = 0.0

    @classmethod
    def empty(cls) -> RepoStatusSnapshot:
        return cls()
```

### Key Rules

1. **`frozen=True`** - Prevents attribute modification
2. **`tuple`** - Use tuples, not lists (lists are mutable)
3. **Type hints** - Use `tuple[X, ...]` for variable-length tuples

### Caveats

From Python docs:
> *"It is not possible to create truly immutable Python objects"*

- Enforcement is runtime only (no compile-time checks)
- If dataclass contains mutable types, those can still change
- Small performance penalty (~2.4x slower instantiation)

---

## Pattern 4: QFileSystemWatcher with Debounce

### Structure

```python
from PySide6.QtCore import QFileSystemWatcher, QTimer


class FileWatcher(QObject):
    """Watches filesystem with debounced notifications."""

    changed = Signal()

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

        # Debounce timer
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._emit_changed)

        # Filesystem watcher
        self._watcher = QFileSystemWatcher()
        self._watcher.addPath(path)
        self._watcher.directoryChanged.connect(self._on_change)
        self._watcher.fileChanged.connect(self._on_change)

    def _on_change(self, path: str) -> None:
        """Debounce rapid changes."""
        self._timer.start()

        # Re-add path (QFileSystemWatcher removes on some changes)
        if path not in self._watcher.files() + self._watcher.directories():
            self._watcher.addPath(path)

    def _emit_changed(self) -> None:
        self.changed.emit()
```

### Important: Re-add Paths

QFileSystemWatcher may remove paths after certain changes. Always re-add:
```python
if path not in self._watcher.files() + self._watcher.directories():
    self._watcher.addPath(path)
```

---

## Pattern 5: QDockWidget Layout

### Structure

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QDockWidget, QWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        # Enable dock nesting
        self.setDockNestingEnabled(True)

        # Assign corners to dock areas
        self.setCorner(Qt.Corner.TopLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)

        # Hidden central widget for dock-only layout
        placeholder = QWidget()
        placeholder.hide()
        self.setCentralWidget(placeholder)

        # Create dock widgets
        self._setup_docks()

    def _setup_docks(self) -> None:
        # Create panels
        files_panel = FilesPanel()
        changes_panel = ChangesPanel()
        commit_panel = CommitPanel()

        # Create docks
        files_dock = self._create_dock(files_panel, "files", "Files")
        changes_dock = self._create_dock(changes_panel, "changes", "Changes")
        commit_dock = self._create_dock(commit_panel, "commit", "Commit")

        # Add first dock
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, files_dock)

        # Split to add more docks with proper resize handles
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, changes_dock)
        self.splitDockWidget(files_dock, changes_dock, Qt.Orientation.Vertical)

        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, commit_dock)
        self.splitDockWidget(files_dock, commit_dock, Qt.Orientation.Horizontal)

    def _create_dock(
        self, widget: QWidget, name: str, title: str
    ) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)  # Required for state persistence
        dock.setWidget(widget)
        return dock
```

### Why Hidden Central Widget?

When using only dock widgets (no central content):
- Set a hidden placeholder as central widget
- This allows docks to fill the entire window
- Proper splitter handles appear between docks

### Why splitDockWidget?

`splitDockWidget()` creates proper splitter handles between docks in the same area. Without it, docks stack/tab instead of split.

---

## Pattern 6: State Persistence with QSettings

### Structure

```python
from PySide6.QtCore import QSettings, QByteArray


class MainWindow(QMainWindow):
    LAYOUT_VERSION = 1  # Bump when layout structure changes

    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()
        self._restore_state()

    def _restore_state(self) -> None:
        settings = QSettings("MyCompany", "MyApp")

        # Check version compatibility
        version = settings.value("layout_version", 0, type=int)
        if version != self.LAYOUT_VERSION:
            return  # Use default layout for new version

        # Restore window geometry
        geometry = settings.value("geometry", type=QByteArray)
        if geometry:
            self.restoreGeometry(geometry)

        # Restore dock/toolbar state
        state = settings.value("window_state", type=QByteArray)
        if state:
            self.restoreState(state)

    def closeEvent(self, event) -> None:
        self._save_state()
        super().closeEvent(event)

    def _save_state(self) -> None:
        settings = QSettings("MyCompany", "MyApp")
        settings.setValue("layout_version", self.LAYOUT_VERSION)
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("window_state", self.saveState())
```

### Layout Version

Bump `LAYOUT_VERSION` when:
- Adding/removing dock widgets
- Changing dock object names
- Restructuring layout

Old state data is incompatible with new layouts and causes corruption.

---

## Pattern 7: Signal Feedback Loop Prevention

### Problem

```python
# BAD: Causes infinite loop
def _on_value_changed(self, value: int) -> None:
    self.model.setValue(value)  # Updates model
    # Model emits signal → calls this again → infinite loop
```

### Solution: blockSignals()

```python
def _on_value_changed(self, value: int) -> None:
    self.spinbox.blockSignals(True)
    self.spinbox.setValue(value)
    self.spinbox.blockSignals(False)
```

Or use context manager:
```python
@contextmanager
def blocked_signals(widget: QObject):
    """Temporarily block signals."""
    was_blocked = widget.signalsBlocked()
    widget.blockSignals(True)
    try:
        yield
    finally:
        widget.blockSignals(was_blocked)


# Usage
with blocked_signals(self.spinbox):
    self.spinbox.setValue(value)
```

---

## Do's and Don'ts Checklist

### Threading

- [x] Use QThreadPool + QRunnable for background work
- [x] Use Signal/Slot for cross-thread communication
- [x] Create JobSignals as QObject for signal inheritance
- [x] Set `setAutoDelete(True)` on runnables
- [ ] Never subclass QThread (use worker objects)
- [ ] Never call GUI methods from worker threads
- [ ] Never use `subprocess.run()` on UI thread

### Data

- [x] Use `@dataclass(frozen=True)` for snapshots
- [x] Use `tuple` not `list` for immutable collections
- [x] Add type hints with `tuple[X, ...]`
- [ ] Never pass mutable objects across threads
- [ ] Never modify shared state from workers

### UI

- [x] Use `blockSignals()` to prevent feedback loops
- [x] Set `setObjectName()` on docks for persistence
- [x] Use `splitDockWidget()` for resize handles
- [x] Bump layout version on structural changes
- [ ] Never do I/O in event handlers

### Controller

- [x] Single controller owns all state
- [x] Debounce filesystem events
- [x] Cancel pending jobs before starting new
- [ ] Never call git/backend from views directly

---

## Known Platform Issues

### WSL2 / X11: Floating Dock Freeze

Floating dock widgets may freeze the entire application under WSL2 with X11 forwarding.

**Workaround:** Disable floating:
```python
dock.setFeatures(
    QDockWidget.DockWidgetFeature.DockWidgetMovable |
    QDockWidget.DockWidgetFeature.DockWidgetClosable
    # Omit DockWidgetFloatable
)
```

### macOS: Native Title Bar

Qt's `QDockWidget` may conflict with macOS native title bar unification.

**Workaround:** Test with and without `Qt::AA_UseHighDpiPixmaps`.
