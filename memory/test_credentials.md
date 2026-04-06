# Test Credentials

## Admin / Owner Account
- **Username**: `@shish123`
- **PIN**: `1234`
- **Role**: `owner`

## Login Endpoint
```
POST /api/auth/access
Body: { "username": "@shish123", "password": "1234" }
```

## Notes
- The "password" field is the PIN (4-digit)
- Owner role has full access to all admin endpoints
- Credits: admin-exempt (unlimited)
- These credentials were verified working in test iteration 21 (2026-02-06)
