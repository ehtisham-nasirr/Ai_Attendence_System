# Security & Authentication

## Never Hardcode

- `PASSWORD`
- `SECRET_KEY` / `JWT_SECRET`
- `API_KEY`
- `TOKEN`
- `DATABASE_URL` / `DATABASE_PASSWORD`
- `PRIVATE_KEY` / encryption keys
- Camera RTSP URLs, usernames and passwords
- LDAP bind credentials, SMTP credentials, payroll webhook secrets

Configuration is loaded with **pydantic-settings** from environment variables:

```python
class Settings(BaseSettings):
    jwt_secret: SecretStr
    database_url: SecretStr
    model_config = SettingsConfigDict(env_file=".env")
```

Maintain both `.env` (real values, **never committed**) and `.env.example` (same keys, placeholder values, committed). Camera credentials entered through the UI are stored encrypted in the database (`rtsp_url_encrypted`), never in plain text and never in `.env`.

## Production Security Checklist

Production configuration must:

- Disable debug mode and the interactive docs in production (`/api/docs` only in dev/staging, or behind admin auth)
- Serve everything over HTTPS through Nginx; HSTS enabled
- Set CORS to the portal's exact origin — never `allow_origins=["*"]`
- Set auth cookies as `HttpOnly`, `Secure`, `SameSite=Lax` (or `Strict`)
- Protect cookie-authenticated state-changing requests against CSRF (double-submit token or SameSite=Strict + Origin check)
- Send security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`)
- Hash passwords with argon2; lock accounts after 5 failed logins; session timeout 30 minutes
- Rate-limit `/auth/login` and API-key endpoints
- Keep the engine API, PostgreSQL, Redis and MinIO on the internal network only — no public ports

## Authentication vs. Authorization

- **Authentication:** *Who is the user?* — JWT access token in an HttpOnly cookie (portal), Active Directory via ldap3 when enabled (FR-40), hashed API keys in `api_clients` for the payroll integration.
- **Authorization:** *What is this user allowed to do?* — role-based permissions from requirements §4, enforced by the `require_permission()` dependency, plus **data scoping** (a Department Manager only sees their department; an Employee only sees their own records).

Always implement permission and scope checks on the backend. Hiding a button in React is a UX nicety, not a security control.

```
Frontend permission check
        +
Backend permission + scope check
        ↓
  Secure application
```

**The backend is the final authority.** Every sensitive action — enrollment, biometric erasure, corrections, threshold changes, exports — is re-checked server-side and written to the audit log.

## API Keys

- Store only a hash (`key_hash`) and a short prefix for identification; show the full key once at creation.
- Scope keys (`integration:read`) and record `last_used_at`.
- Outbound payroll webhooks are signed with HMAC-SHA256 using a secret from configuration.
