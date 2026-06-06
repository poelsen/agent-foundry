# GUI Threading Skill

Framework-agnostic patterns for building responsive multithreaded GUI applications.

## Overview

This skill provides battle-tested patterns for GUI applications that need to perform background work without freezing the UI. The patterns are derived from authoritative sources including MIT's thread safety course, KDAB's Qt expertise, and Facebook's Flux architecture.

## When to Use

Activate this skill when:
- Building desktop GUI applications with async operations
- Implementing background data fetching
- Designing state management for multithreaded UIs
- Creating responsive interfaces that don't freeze

## Patterns Included

| Pattern | Purpose | Source |
|---------|---------|--------|
| UI Thread Protection | Keep UI responsive | KDAB Rules #2, #3 |
| One-Way Data Flow | Predictable state updates | Flux, Redux, Elm |
| Worker Job Pattern | Safe background execution | KDAB Rule #7 |
| Immutable Snapshots | Thread-safe data sharing | MIT 6.005, Redux |
| Debounced Refresh | Efficient event handling | Event-driven design |
| Multipane Dock Layout | Customizable panel layouts | Qt patterns |

## Key Principles

### 1. UI Thread Does Two Things Only

```
Render → Display data from models
React  → Respond to input, dispatch commands
```

The UI thread NEVER runs backend operations, file I/O, or heavy computations.

### 2. Data Flows One Direction

```
Backend → Controller → Models → Views
```

Views never write directly to backend. User actions create commands that flow to the controller.

### 3. Cross-Thread Data is Immutable

Workers create read-only snapshots. UI reads snapshots. No shared mutable state.

## Related Files

| File | Purpose |
|------|---------|
| `.claude/rules/gui-threading.md` | Non-negotiable rules |
| `.claude/skills/python-qt-gui/SKILL.md` | Python/Qt implementation |
| `rule-library/lang/python-qt.md` | Python/Qt checklists |

## Extension Skills

This is a base skill. Language/framework-specific extensions:

- **Python/Qt**: `.claude/skills/python-qt-gui/SKILL.md`

To create additional extensions (e.g., for Electron, GTK, WinUI), follow the same pattern: extend the base concepts with framework-specific implementations.

## References

- [MIT 6.005 Thread Safety](https://web.mit.edu/6.005/www/fa14/classes/18-thread-safety/)
- [KDAB: Eight Rules of Multithreaded Qt](https://www.kdab.com/the-eight-rules-of-multithreaded-qt/)
- [Facebook Flux Architecture](https://facebookarchive.github.io/flux/docs/in-depth-overview/)
- [Redux: Why Immutable Data](https://redux.js.org/faq/immutable-data)
- [Martin Fowler: Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)
