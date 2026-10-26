# Security Guidelines

## Checks before a commit

Where the item applies to the code being changed:

- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] All user inputs validated
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (sanitized HTML)
- [ ] CSRF protection enabled
- [ ] Authentication/authorization verified
- [ ] Rate limiting on endpoints
- [ ] Error messages don't leak sensitive data

## Secret Management

Use env vars, never hardcode secrets.

## Security Response

If a security issue is found:
1. Stop and report it before continuing
2. Fix exploitable issues before other work; the **security-reviewer** agent helps judge severity
3. Rotate any exposed secrets
