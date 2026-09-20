# API baseline

## Authentication endpoints

### POST /api/auth/login
- Accepts storeCode, role, password
- Returns a session cookie for manager or crew
- Errors: 400, 401, 429

### POST /api/auth/signup
- Requires admin key and store metadata
- Creates a store, manager account, membership, and manager session
- Errors: 400, 403, 409, 429, 503

### POST /api/auth/add-manager
- Creates another manager record for an existing store
- Requires admin key and store code

### POST /api/auth/logout
- Clears both manager and crew session cookies

### GET /api/auth/status
- Reports whether the current user is authenticated and whether the role is manager or crew

## Report endpoints

### GET /api/reports
- Requires manager authentication
- Returns reports for the authenticated manager’s stores

### POST /api/reports
- Requires crew authentication
- Validates payload, checks duplicate/cooldown protections, runs quality gate, and queues report
- Returns 202 while job is pending

### GET /api/heads-up
- Returns store-scoped current Head’s Up message
- Works for crew or manager if store is known

### POST /api/heads-up
- Requires manager authentication
- Saves a store-level Head’s Up message

## Overview endpoints

### GET /api/managers
- Requires manager authentication
- Returns manager activity list for the current store

### GET /api/weekly-overview
- Requires manager authentication
- Returns AI-generated summary of the last seven days of reports for the session store

## Health endpoint

### GET /api/health
- Returns server health and DB config status
- Status 200 for healthy DB; 503 when database not ready

## Compatibility note

These routes are treated as the compatibility contract for the current browser app. Any future changes should preserve the path, payload structure, cookies, and response codes unless an explicit contract update is planned.
