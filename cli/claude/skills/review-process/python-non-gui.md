# Python Non-GUI Review Process

Use this process for Python CLIs, scripts, workers, services, daemons,
libraries, and other Python runtime code that is not desktop GUI work. It
extends the [Python review process](python.md).

## Non-GUI risk triggers

Escalate when the change touches:

- CLI argument parsing, exit codes, stdout/stderr contracts, or shell
  scripting;
- service startup, shutdown, daemon lifecycle, cancellation, or signal
  handling;
- background workers, queues, retries, or scheduling;
- network calls, timeouts, authentication, or external APIs;
- filesystem operations, temp files, cleanup, or path handling;
- long-running batch jobs or resource usage;
- library public API compatibility.

## Non-GUI reviewer routing

| Trigger | Executed reviewer/agent | Rule set to apply |
|---------|-------------------------|-------------------|
| CLI/script behavior | `code-reviewer-python` | Scripts and CLI rules |
| Service/worker lifecycle | `architect-python` or `code-reviewer-python` | Lifecycle/cancellation checks |
| Security-sensitive input, files, network, auth | `security-reviewer-python` | Security checks |
| Test strategy for CLI/service behavior | `tdd-guide-python` | Pytest/fake/process checks |
| Build/lint/runtime failure | `build-error-resolver-python` | Existing tool output |

## CLI and script checklist

- [ ] Argument parsing has explicit validation and helpful errors.
- [ ] Exit codes distinguish success, usage error, and runtime failure.
- [ ] stdout is machine-usable when promised; diagnostics go to stderr.
- [ ] Paths are absolute or resolved relative to documented working
      directories.
- [ ] Temporary files/directories are cleaned up on success and failure.
- [ ] Failure messages include enough context to act.

## Service and worker checklist

- [ ] Startup and shutdown order is explicit.
- [ ] Long-running loops have cancellation or stop conditions.
- [ ] Retries have limits, backoff, and surfaced failure.
- [ ] Timeouts exist for external calls.
- [ ] Resource ownership is clear for files, sockets, subprocesses, and
      threads.
- [ ] Logs include context without leaking secrets.
- [ ] Tests cover shutdown, cancellation, timeout, and failure partitions.

## Library checklist

- [ ] Public API changes are documented and tested.
- [ ] Backward compatibility or deprecation horizon is explicit.
- [ ] Errors are typed or documented enough for callers to handle.
- [ ] Global state is avoided or isolated.
- [ ] Import side effects are minimal.

## Non-GUI output addendum

```text
Runtime guard: <CLI test, service lifecycle test, timeout/failure test, subprocess check, or manual verification>
```
