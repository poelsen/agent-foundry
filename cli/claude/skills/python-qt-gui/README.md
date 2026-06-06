# Python/Qt GUI Skill

Python/Qt-specific implementations for multithreaded GUI applications using PySide6.

## Overview

This skill extends `gui-threading` with concrete Python/Qt implementations. It provides code patterns, checklists, and platform-specific guidance for building responsive Qt applications.

## Prerequisites

- Read the base skill: `.claude/skills/gui-threading/SKILL.md`
- Familiarity with PySide6 (or PyQt6)
- Understanding of Python dataclasses

## When to Use

Activate this skill when:
- Building PySide6/PyQt6 desktop applications
- Implementing QThreadPool workers
- Creating QDockWidget-based layouts
- Adding state persistence with QSettings

## Patterns Included

| Pattern | Qt Components | Purpose |
|---------|---------------|---------|
| Worker Jobs | `QThreadPool`, `QRunnable` | Background execution |
| Controller | `QObject`, `QTimer`, `Signal` | State management |
| Immutable Data | `@dataclass(frozen=True)` | Thread-safe snapshots |
| File Watching | `QFileSystemWatcher` | Filesystem events |
| Dock Layout | `QDockWidget`, `splitDockWidget` | Customizable panels |
| Persistence | `QSettings` | Save/restore state |
| Feedback Prevention | `blockSignals()` | Avoid signal loops |

## Quick Start

### Background Worker

```python
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

class JobSignals(QObject):
    finished = Signal(object)
    error = Signal(str)

class MyJob(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = JobSignals()
        self.setAutoDelete(True)

    def run(self):
        result = self.do_work()
        self.signals.finished.emit(result)

# Usage
job = MyJob()
job.signals.finished.connect(self.on_complete)
QThreadPool.globalInstance().start(job)
```

### Immutable Snapshot

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class DataSnapshot:
    items: tuple[Item, ...] = ()  # tuple, not list!
    timestamp: float = 0.0
```

### Dock Layout

```python
self.setDockNestingEnabled(True)
self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)

# Hidden central for dock-only layout
placeholder = QWidget()
placeholder.hide()
self.setCentralWidget(placeholder)

# Split for resize handles
self.splitDockWidget(dock_a, dock_b, Qt.Vertical)
```

## Checklists

### Before Code Review

- [ ] No GUI calls from worker threads
- [ ] No blocking calls on main thread
- [ ] Cross-thread data uses frozen dataclass + tuple
- [ ] Pending jobs cancelled before starting new
- [ ] Dock widgets have `setObjectName()` for persistence
- [ ] Layout version bumped on structural changes

### Common Mistakes

| Mistake | Fix |
|---------|-----|
| `subprocess.run()` on UI thread | Use QRunnable worker |
| `list` in frozen dataclass | Use `tuple` |
| Missing `setAutoDelete(True)` | Add to QRunnable init |
| Signal feedback loop | Use `blockSignals(True)` |
| Floating docks freeze (WSL2) | Disable `DockWidgetFloatable` |

## Related Files

| File | Purpose |
|------|---------|
| `.claude/skills/gui-threading/SKILL.md` | Base patterns (read first) |
| `.claude/rules/gui-threading.md` | Non-negotiable rules |
| `rule-library/lang/python-qt.md` | Full checklists |

## Platform Notes

### WSL2 / X11

Floating dock widgets may freeze. Disable floating:
```python
dock.setFeatures(
    QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable
)
```

### macOS

Test high-DPI and title bar integration carefully.

### Windows

Use `pathlib.Path` for cross-platform paths. Long paths (>260 chars) may need registry configuration.

## References

- [Qt 6 QThreadPool](https://doc.qt.io/qt-6/qthreadpool.html)
- [Qt 6 Reentrancy](https://doc.qt.io/qt-6/threads-reentrancy.html)
- [Python dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [KDAB Multithreading PDF](https://www.kdab.com/documents/multithreading-with-qt.pdf)
