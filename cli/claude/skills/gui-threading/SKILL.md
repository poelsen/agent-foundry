---
name: gui-threading
description: Framework-agnostic patterns for building responsive multithreaded GUI applications with proper thread safety, unidirectional data flow, and immutable state management.
---

# GUI Threading Patterns

Battle-tested, framework-agnostic patterns for building responsive multithreaded GUI applications.

## When to Activate

Use this skill when:
- Building desktop GUI applications with background operations
- Implementing async data fetching in UI applications
- Designing state management for multithreaded GUIs
- Creating responsive interfaces that don't freeze during heavy operations

## Authoritative Sources

These patterns are grounded in well-established industry resources:

| Source | Topic | URL |
|--------|-------|-----|
| **MIT 6.005** | Thread Safety | https://web.mit.edu/6.005/www/fa14/classes/18-thread-safety/ |
| **KDAB** | Qt Multithreading | https://www.kdab.com/the-eight-rules-of-multithreaded-qt/ |
| **Facebook Flux** | Unidirectional Flow | https://facebookarchive.github.io/flux/docs/in-depth-overview/ |
| **Redux** | Immutable State | https://redux.js.org/faq/immutable-data |
| **Martin Fowler** | Event Sourcing | https://martinfowler.com/eaaDev/EventSourcing.html |

---

## Pattern 1: UI Thread Protection

**Source:** KDAB Rules #2, #3

### The Rule

The UI thread has exactly two responsibilities:
1. **Render** - Display data from models
2. **React** - Respond to user input, trigger commands

The UI thread MUST NOT:
- Execute backend operations (file I/O, network, database)
- Perform heavy computations
- Block waiting for results

### Why

From KDAB: *"Never do GUI operations off the main thread"* and *"Don't block the main thread."*

Blocking the main thread freezes the UI, making the app appear unresponsive. The OS may show "not responding" after a few seconds.

### Implementation

```
User clicks "Load" button
    → UI dispatches LoadCommand
    → Controller spawns background job
    → UI remains responsive (shows spinner)
    → Job completes, emits signal
    → Controller receives result
    → Controller updates model
    → UI refreshes from model
```

---

## Pattern 2: One-Way Data Flow

**Source:** Facebook Flux, Redux, Elm Architecture

### The Rule

Data flows in one direction only:

```
Backend → Controller → Models → Views
           ↑                      |
           └── Commands ──────────┘
```

Views NEVER write directly to backend or models. Views emit commands/actions that the controller processes.

### Why

From Facebook's Flux: *"When updates can only change data within a single round, the system as a whole becomes more predictable."*

Two-way bindings cause cascading updates that are hard to debug. One-way flow makes state changes traceable.

### Elm Architecture Analogy

```
Model → Update → View → (message) → Update
```

The View is a pure function of Model. Updates produce new Model, never mutate.

---

## Pattern 3: Worker Job Pattern

**Source:** KDAB Rule #7 (worker objects)

### The Rule

Background work uses worker objects with:
1. **Signals** for thread-safe result delivery
2. **Cancellation flag** for clean termination
3. **Auto-cleanup** after completion

### Structure

```
┌─────────────────────────────────────────┐
│ Worker Job                              │
├─────────────────────────────────────────┤
│ signals:                                │
│   - finished(result)                    │
│   - error(message)                      │
│   - progress(percent)                   │
├─────────────────────────────────────────┤
│ state:                                  │
│   - _cancelled: bool                    │
├─────────────────────────────────────────┤
│ run():                                  │
│   if cancelled: return                  │
│   result = execute()     # subclass     │
│   if not cancelled:                     │
│     signals.finished.emit(result)       │
└─────────────────────────────────────────┘
```

### Why

From KDAB: *"Avoid adding slots to QThread subclasses - use worker objects."*

Worker objects:
- Are easier to test (no thread dependency)
- Can be reused with different thread pools
- Have clear lifecycle (create → submit → complete → destroy)

---

## Pattern 4: Immutable Snapshots

**Source:** MIT 6.005 Strategy #2, Redux, Martin Fowler

### The Rule

Data passed between threads MUST be immutable. Workers create snapshots; UI reads snapshots.

### Why

From MIT 6.005, there are three strategies for thread safety:
1. **Confinement** - Don't share data
2. **Immutability** - Share, but keep immutable
3. **Thread-safe types** - Use synchronized data structures

Immutability is the simplest: no locks needed, no race conditions possible.

From Redux: *"Using immutable states allows us to write code that can quickly tell if the state has changed, without needing to do a recursive comparison."*

### Benefits

| Benefit | Explanation |
|---------|-------------|
| Thread safety | No locks needed - data can't change |
| Race prevention | Can't modify while reading |
| Consistent UI | Snapshot = one coherent moment |
| Change detection | Identity comparison: `old is not new` |
| Time-travel | Keep history of snapshots for undo/debug |

### Anti-Pattern

```
# BAD: Shared mutable state
Worker: status.files.append(new_file)   # Thread A modifies
UI:     for f in status.files: draw(f)  # Thread B iterates → CRASH
```

### Correct Pattern

```
# GOOD: Immutable snapshot
Worker: snapshot = StatusSnapshot(files=tuple(files))
Worker: signal.emit(snapshot)   # Hand off immutable data
UI:     for f in snapshot.files: draw(f)  # Safe - can't change
```

---

## Pattern 5: Debounced Event-Driven Refresh

### The Rule

Refresh triggers:
- User actions (explicit commands)
- Filesystem changes (debounced)
- Post-operation refresh

NEVER refresh on a timer/interval.

### Why

Timer-based polling:
- Wastes resources when nothing changed
- Still misses rapid changes between intervals
- Creates unpredictable timing bugs

Event-driven refresh:
- Responds immediately to actual changes
- Uses no resources when idle
- Debouncing prevents flood during rapid changes

### Debounce Pattern

```
Event received
    → Cancel pending debounce timer
    → Start new debounce timer (e.g., 100ms)
    → Timer fires → Execute refresh
```

### Cancel-Before-New Pattern

Before starting a new background job:
1. Cancel any pending job of the same type
2. Start the new job

This prevents stale results from overwriting fresh results.

---

## Pattern 6: Multipane Dock Layout

### The Rule

For complex multi-panel GUIs:
1. Use dock widgets for each panel
2. Assign corners to dock areas
3. Use splits for proper resize handles
4. Persist layout to settings

### Structure

```
┌────────────────────────────────────────────────────┐
│ Main Window                                        │
├────────────────────────────────────────────────────┤
│  ┌─────────┬───────────────────────┬────────────┐  │
│  │         │                       │            │  │
│  │  Left   │       Center          │   Right    │  │
│  │  Dock   │       Area            │   Dock     │  │
│  │  Area   │  (can be dock-only)   │   Area     │  │
│  │         │                       │            │  │
│  ├─────────┴───────────────────────┴────────────┤  │
│  │                Bottom Dock Area              │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
```

### Why

- Dock widgets support user customization (drag, resize, tab, float)
- Corner assignment determines which area "owns" corners
- Splits create proper resize handles between docks
- Layout persistence respects user preferences

---

## Anti-Patterns to Avoid

### 1. Direct Backend Calls from UI

```
# BAD
def on_button_click(self):
    data = database.query("SELECT * FROM ...")  # Blocks UI thread!
    self.display(data)
```

### 2. Mutable Shared State

```
# BAD
class SharedState:
    items = []  # Mutable list shared between threads

worker_thread.append(SharedState.items)  # Race condition!
ui_thread.iterate(SharedState.items)     # May crash
```

### 3. Timer-Based Polling

```
# BAD
timer = Timer(interval=1000)  # Poll every second
timer.timeout.connect(self.refresh_everything)
```

### 4. Blocking on Background Results

```
# BAD
def refresh(self):
    future = thread_pool.submit(heavy_work)
    result = future.result()  # Blocks UI thread!
```

### 5. Two-Way Data Bindings

```
# BAD
view.data = model.data          # Model → View
view.on_change = model.update   # View → Model (direct mutation)
```

---

## Summary Checklist

- [ ] UI thread only renders and reacts
- [ ] All backend work runs on worker threads
- [ ] Data flows one direction: Backend → Controller → Model → View
- [ ] Worker jobs have signals, cancellation, auto-cleanup
- [ ] Cross-thread data is immutable
- [ ] Refresh is event-driven, not timer-based
- [ ] Cancel pending jobs before starting new ones
- [ ] Dock layout supports user customization
