# Test Credentials

## Application Login
- **Login Type**: Username + PIN (no password visible on screen, uses PIN on backend)
- **Admin Account**: `@shish123` (PIN: `1234`)
- **Auth Endpoint**: POST `/api/auth/access` with `{"username": "@shish123", "pin": "1234"}`
- **Token field in response**: `token`

## Alternative Users
- `rishaan@2017` (admin)
- `Manas@123` (user)

## Kite API
- Kite access token stored in `system_meta` collection key `kite_session`
- Kite API key available in backend `.env`
- Redirect URL: https://multibagger-engine.preview.emergentagent.com/api/kite/callback
