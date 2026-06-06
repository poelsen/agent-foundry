# Architecture Principles

## Project Discovery

When implementing new functionality:
1. Search for battle-tested skeleton projects
2. Use parallel agents to evaluate options:
   - Security assessment
   - Extensibility analysis
   - Relevance scoring
   - Implementation planning
3. Clone best match as foundation
4. Iterate within proven structure

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
