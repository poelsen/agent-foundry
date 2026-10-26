# Testing

## What to run, and when

- While working, run the tests that cover what you changed, plus a quick sanity check if the project has one. Don't run the whole suite after every edit.
- Run the full suite before a merge when the change is wide (shared code, data models, build config) or when you can't tell what it touches. Say which run you did.
- Scheduled or CI runs catch regressions you didn't foresee; that is their job, not every edit's.
- Use the test command from the Environment section or the project's own notes. Don't invent a different one.

## What to write

- A test for every behaviour you add or fix. Start with the test when it clarifies the behaviour; write it after when the shape of the code isn't clear yet.
- Test behaviour, not implementation. A test that mirrors the code it tests, or that only asserts the mock was called, proves nothing; leave it out.
- Keep each test independent of ordering and of other tests' state.
- Match the project's existing layout and fixtures.

## Coverage

The project's own target applies. Where it has none, keep new code roughly as well covered as the code around it. Coverage is a signal, not a goal: don't write tests to move the number.

## When a test fails

1. Read the failure before changing anything.
2. Fix the code, not the test, unless the test is wrong.
3. Check isolation: does it fail alone, and does it fail on a clean checkout?

The **e2e-test-\*** agents help with user-flow tests in a web or GUI app.
