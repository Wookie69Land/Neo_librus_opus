# JWT Token — Frontend Developer Guide

## Overview

After a successful `POST /api/auth/login`, the server returns a **JWT (JSON Web Token)** in the response body:

```json
{ "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...." }
```

Store this token (e.g. in memory or `localStorage`) and send it with every authenticated request as a **Bearer token**:

```
Authorization: Bearer <token>
```

---

## Token Structure

A JWT has three Base64URL-encoded parts separated by dots:

```
HEADER.PAYLOAD.SIGNATURE
```

| Part | Contains |
|------|----------|
| Header | Algorithm (`HS256`) and token type (`JWT`) |
| Payload | User data claims (see below) |
| Signature | HMAC-SHA256 hash — **only the server can verify this** |

---

## Reading the Payload (Client-Side)

You can decode the **Header** and **Payload** client-side without the secret key — they are just Base64URL-encoded JSON.  
**Never try to verify or forge the signature on the client.** Treat the payload as read-only metadata.

### JavaScript / TypeScript

```ts
function decodeJwtPayload(token: string): Record<string, unknown> {
  const base64Url = token.split('.')[1];
  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
  const json = decodeURIComponent(
    atob(base64)
      .split('')
      .map(c => '%' + c.charCodeAt(0).toString(16).padStart(2, '0'))
      .join('')
  );
  return JSON.parse(json);
}

const claims = decodeJwtPayload(token);
```

### Using a library (recommended)

```bash
npm install jwt-decode
```

```ts
import { jwtDecode } from 'jwt-decode';

const claims = jwtDecode(token);
```

---

## Payload Claims

After login the token payload contains all non-secret user attributes:

| Claim | Type | Description |
|-------|------|-------------|
| `sub` | `number` | User ID (primary key) |
| `username` | `string` | Login name |
| `email` | `string` | Email address |
| `first_name` | `string` | First name |
| `last_name` | `string` | Last name |
| `region` | `number \| null` | Voivodeship code |
| `date_joined` | `string` (ISO 8601) | Account creation date |
| `role_id` | `number` | `0` = no role, `1` = library admin, `2` = library manager |
| `library_id` | `number` | Associated library ID (`0` if no role) |
| `jti` | `string` | Unique token identifier (hex) |

### Example decoded payload

```json
{
  "sub": 2,
  "username": "lland",
  "email": "lukaskraj@gmail.com",
  "first_name": "Lukas",
  "last_name": "Land",
  "region": 7,
  "date_joined": "2026-03-18T20:53:36.781011+00:00",
  "role_id": 0,
  "library_id": 0,
  "jti": "1983657c0ea6076dea74b16833fb5a99"
}
```

---

## Important Notes

- **No expiry (`exp`)** — this is a session-based token. It is valid as long as it exists in the server's database. After `POST /api/auth/logout` the server deletes it and the token becomes permanently invalid.
- **Do not verify the signature client-side.** The HMAC secret is only on the server.
- **Do not modify the token.** Any change to the payload will make the signature invalid and the server will reject it.
- **Treat the token like a password.** Do not log it, do not expose it in URLs.
