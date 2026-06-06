# Python GUI Review Process

Use this process for PySide6, PyQt, Qt, or other Python desktop GUI work. It
extends the [Python review process](python.md) with GUI-thread,
widget-lifecycle, signal/slot, persistence, and GUI test checks.

## GUI reviewer routing

| Trigger | Executed reviewer/agent | Required skill or rule set |
|---------|-------------------------|----------------------------|
| QThread, workers, signals/slots, cancellation, UI-thread safety | `code-reviewer-python` or `architect-python` instructed to apply the rule set | `gui-threading` skill |
| PySide6 widgets, layouts, QDockWidget, persistence, pytest-qt | `code-reviewer-python` instructed to apply the rule set | `python-qt-gui` skill |
| GUI E2E behavior, widget signals, headless CI, pytest-qt maintenance | `e2e-test-python-qt` | pytest-qt and GUI E2E rules |
| Cross-plugin GUI architecture or plugin framework contracts | `architect-python` + relevant GUI rule set | `gui-threading` and/or `python-qt-gui` |

Record both the executed reviewer and any skill/rule set consulted. Do not
claim that a skill was "run" unless an actual agent or human applied it.

## GUI risk triggers

Escalate to T3 when the change touches:

- worker/thread lifecycle or cancellation;
- device/network/file I/O that might run on the UI thread;
- signal/slot payload contracts;
- widget ownership/destruction order;
- persisted geometry, dock state, or layout presets;
- plugin lifecycle, open/close/reconnect behavior;
- live data rendering, timers, throttling, or backpressure;
- tests that rely on sleeps instead of Qt synchronization.

## GUI-thread safety checklist

- [ ] No device, network, filesystem, or long-running computation runs on the
      UI thread.
- [ ] Worker outputs crossing threads are immutable snapshots or otherwise
      thread-safe.
- [ ] Signals carry stable, documented payload shapes.
- [ ] Stale worker results are ignored with generation/cancellation guards.
- [ ] UI updates happen only on the main thread.
- [ ] Timers are owned by objects with clear lifetime.
- [ ] Close/reconnect paths stop timers/workers before widgets are destroyed.

## Widget and layout checklist

- [ ] Parent/child ownership is explicit.
- [ ] `QObject` parents are real Qt objects or `None`, not plain mocks.
- [ ] Layout changes preserve user resizing where intended.
- [ ] Scroll areas are introduced only where they do not steal splitter
      resize behavior.
- [ ] Dock/title-bar controls keep accessible hit targets and visible hover
      states.
- [ ] Persisted geometry/layout data remains backward-compatible or has a
      migration path.
- [ ] Reconnect or reopen paths restore state without stale widgets/signals.

## GUI test checklist

- [ ] Use `qtbot.waitUntil` or `qtbot.waitSignal`, not hardcoded sleeps.
- [ ] Exercise widget state through Qt-visible behavior, not only internal
      attributes.
- [ ] Use real Qt parents or `None`; do not pass plain `Mock()` as a QObject
      parent.
- [ ] Verify signal emissions and payload shapes for changed contracts.
- [ ] Cover close/reopen/reconnect where lifecycle is changed.
- [ ] Headless CI constraints are respected.
- [ ] Avoid patching Qt internals in ways that can crash the test runner.

## Project GUI defaults

Project-specific GUI expectations (plugin contracts, recorder/store flows,
shared dock/title-bar behavior, settings persistence flow, focused-test
patterns) belong in the project's `CLAUDE.md` or rule files, not here. When
reviewing, surface project-specific defaults from those sources and cite them
in the review header.

## GUI-specific severity adjustments

Escalate severity when:

- the UI thread can block on device or filesystem I/O;
- a stale worker can update a destroyed or newer widget;
- a layout change removes expected user resizing;
- a persisted state change can strand users in a broken layout;
- a signal payload becomes polymorphic without an explicit typed contract.

## GUI output addendum

```text
GUI guard: <pytest-qt test, signal assertion, lifecycle test, threading check, or manual UI verification>
```
