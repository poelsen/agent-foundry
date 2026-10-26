# Security Guidelines

## Checks before a commit

Where the item applies to the code being changed:

- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] External input validated at the boundary (arguments, files, network, env)
- [ ] No string-built queries or shell commands from input (parameterize, pass argv lists)
- [ ] Error messages and logs don't leak secrets or private data

Web-facing code also needs the checks in the REST API template (auth on every endpoint, XSS and CSRF protection, rate limiting).

## Secret Management

Use env vars, never hardcode secrets.

## Security Response

If a security issue is found:
1. Stop and report it before continuing
2. Fix exploitable issues before other work; the **security-reviewer** agent helps judge severity
3. Rotate any exposed secrets
