# Architecture Principles

## Starting a new project

When a project starts from nothing, look for a proven skeleton or template for its kind before writing the layout by hand. This doesn't apply to adding functionality to an existing project.

## Design Principles

- Composition over inheritance
- Single responsibility per module
- Explicit dependencies (no hidden globals)
- Design for testability
- Minimize coupling between components

## Module Boundaries

- Clear public API per module
- Dependencies flow inward (core has no external deps)
- Side effects at edges, pure logic in core

## File Organization

- Many small files > few large files
- 200-400 lines typical, 800 max
- Organize by feature/domain, not by type
- Colocate related files (component + test + styles)
- Keep module boundaries visible in directory structure

See project-specific architecture in rule-library/arch/.
