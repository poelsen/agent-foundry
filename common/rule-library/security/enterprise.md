# Security: Enterprise/Production

Extends `security.md` with strict requirements for production systems.

## Additional Checks (fix before committing)

- [ ] Secret manager for credentials (not env vars)
- [ ] CSP headers + output encoding for XSS
- [ ] Auth on every endpoint (explicit public allowlist)
- [ ] Authorization checks (RBAC/ABAC)
- [ ] Dependencies scanned for CVEs
- [ ] Secrets scanned in CI (gitleaks/git-secrets)

## Data Protection

- Encrypt at rest and in transit (TLS 1.3)
- PII handling compliant with GDPR/privacy reqs
- Audit logging for sensitive operations
- Data retention policies enforced

## Incident Response

Same as security.md, plus:
4. Review entire codebase for similar issues
5. Document in security log
