# Security: Internal Tools

Moderate security for internally published tools.

## Required Checks
Before ANY commit:
- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] Environment variables for configuration
- [ ] Basic input validation on external inputs
- [ ] Error messages don't expose internal paths/stack traces
- [ ] Dependencies reasonably up to date

## Authentication
- Internal SSO/LDAP integration preferred
- Service accounts for automation
- No shared credentials

## Logging
- Log access and errors
- Don't log sensitive data (passwords, tokens, PII)

## Not Required
- Full OWASP compliance
- Penetration testing
- Rate limiting (internal network)
