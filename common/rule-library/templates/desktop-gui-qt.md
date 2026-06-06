# Template: Desktop GUI (PySide6/Qt)

PySide6/PyQt desktop application development. Covers style, threading architecture, state management, persistence, and testing.

## Sources

- KDAB: https://www.kdab.com/the-eight-rules-of-multithreaded-qt/
- MIT 6.005: https://web.mit.edu/6.005/www/fa14/classes/18-thread-safety/
- Flux: https://facebookarchive.github.io/flux/docs/in-depth-overview/

## Style

- Use **PySide6** over PyQt6 (LGPL vs GPL licensing)
- Add `from __future__ import annotations` to all modules
- Type hints on all public functions
- Use `@dataclass(frozen=True)` for snapshot/immutable data
- Line length: 100 characters (compatible with Qt naming)

## Threading Rules

Non-negotiable rules for multithreaded GUI applications. Violations cause race conditions, UI freezes, and crashes.

### Rule 1: UI Thread Does Zero Backend Work

The UI thread ONLY renders data and responds to user input. It NEVER runs subprocesses, performs file I/O, makes network requests, executes heavy computations, or blocks waiting for results.

**Violation = UI freeze / "not responding"**

### Rule 2: Single Controller Owns All State

One controller instance owns all cached state, coordinates all background jobs, receives all command requests, and emits all state change signals. Views and models read from controller's cached state — they never call backend directly.

**Violation = State inconsistency / race conditions**

### Rule 3: One-Way Data Flow

```
Backend -> Controller -> Models -> Views
```

Data flows in ONE direction. Views never write to backend or models directly. User actions create commands: `View -> Command -> Controller -> Backend`.

**Violation = Cascading updates / unpredictable state**

### Rule 4: Refresh is Event-Driven

Refresh triggers: user action, filesystem watcher event (debounced), or post-operation signal. NEVER refresh on timer/interval for main data.

**Violation = Wasted resources / timing bugs**

### Rule 5: Cancel Before New

Before starting a new background job: cancel any pending job of same type, discard stale results if they arrive.

**Violation = Stale data displayed / race conditions**

### Rule 6: Immutable Snapshots

Data passed between threads MUST be immutable: frozen dataclasses, tuples (not lists), named tuples. NEVER pass mutable collections across threads.

**Violation = Race conditions / crashes / corrupted state**

### Threading Quick Reference

| Rule | What | Why |
|------|------|-----|
| #1 | UI = render + react only | Prevents freezes |
| #2 | One controller owns state | Single source of truth |
| #3 | One-way data flow | Predictable updates |
| #4 | Event-driven refresh | No wasted polling |
| #5 | Cancel before new | No stale data |
| #6 | Immutable snapshots | Thread safety |

### Deviation Protocol

If you believe a rule should be violated: **STOP**, explain the proposed deviation, wait for explicit approval. If approved, document the exception.

## Threading Checklist

- [ ] **KDAB #2**: No GUI operations off main thread
- [ ] **KDAB #3**: Main thread never blocks (no subprocess.run, no sleep)
- [ ] **KDAB #7**: Using QRunnable workers, not QThread subclasses
- [ ] **MIT**: Cross-thread data is immutable (frozen dataclass + tuple)
- [ ] Cancel pending jobs before starting new ones
- [ ] JobSignals inherits QObject for signal support
- [ ] Worker sets `setAutoDelete(True)`

## Data Patterns

- [ ] Snapshots use `@dataclass(frozen=True)`
- [ ] Collections use `tuple`, not `list`
- [ ] Type hints: `tuple[X, ...]` for variable-length tuples
- [ ] No mutable types inside frozen dataclasses
- [ ] Change detection via identity: `old is not new`

```python
@dataclass(frozen=True)
class StatusSnapshot:
    files: tuple[FileEntry, ...] = ()  # NOT list!
```

## QDockWidget

- [ ] Call `setDockNestingEnabled(True)` on main window
- [ ] Assign corners with `setCorner()`
- [ ] Set `setObjectName()` on each dock (required for state persistence)
- [ ] Use `splitDockWidget()` for resize handles between docks
- [ ] Use hidden central widget for dock-only layouts
- [ ] Bump `LAYOUT_VERSION` when changing dock structure

## Persistence

- [ ] Use `QSettings` for state persistence
- [ ] Save geometry with `saveGeometry()`
- [ ] Save state with `saveState()`
- [ ] Track layout version number
- [ ] Skip restore if version mismatch
- [ ] Save on `closeEvent()`

## Signal/Slot Rules

- [ ] Use new-style connections: `signal.connect(slot)`
- [ ] Use `blockSignals(True)` to prevent feedback loops
- [ ] Create signals in `__init__` body or class body
- [ ] Lambda slots need explicit capture of referenced variables
- [ ] Prefer direct slot methods over lambdas for debuggability

## UX

- [ ] Loading states for async operations
- [ ] Error states with recovery actions
- [ ] Keyboard navigation support
- [ ] Focus management
- [ ] Single source of truth for app state
- [ ] Derived state computed, not stored

## Testing

### Unit Tests

Test workers in isolation without Qt event loop:
```python
def test_worker_execute():
    job = MyJob(input_data)
    result = job.execute()  # Direct call, no threading
    assert result == expected
```

### Integration Tests

Use `pytest-qt` for Qt testing:
```python
def test_controller_refresh(qtbot):
    controller = RepoController()
    with qtbot.waitSignal(controller.status_changed):
        controller.request_refresh()
```

### What to Test

- [ ] Worker execute() logic (no Qt dependency)
- [ ] Controller state transitions
- [ ] View updates on signal emission
- [ ] Cancellation behavior
- [ ] Error handling paths

## Known Platform Issues

### WSL2 / X11
- Floating docks may freeze application
- Workaround: Disable `DockWidgetFloatable` feature

### macOS
- High-DPI and title bar unification quirks
- Test with `Qt::AA_UseHighDpiPixmaps`

### Windows
- Path separators: use `pathlib.Path`, not string concat
- Long paths: may need registry key for >260 char paths

## Quick Reference

| Pattern | Implementation |
|---------|----------------|
| Background work | `QThreadPool` + `QRunnable` |
| Thread signals | `QObject` with `Signal()` |
| Immutable data | `@dataclass(frozen=True)` |
| Debounce | `QTimer(singleShot=True)` |
| State persistence | `QSettings` |
| Prevent feedback | `blockSignals(True)` |
