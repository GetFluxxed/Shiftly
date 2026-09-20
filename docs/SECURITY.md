# Security baseline

## Identity and session model

The app currently relies on:
- shared crew credentials at the store level
- manager credentials tied to a store membership
- hashed session tokens stored in Postgres
- short-lived session expiry checks

This design meets the current product needs but does not yet provide the multi-tenant identity model described in the broader roadmap.

## Current controls

- store access codes are hashed before being stored
- crew passwords are hashed using a store-specific derivation
- manager credentials use username + salt + password hash
- cookies are HttpOnly and SameSite=Strict
- security headers are added in ShiftlyHandler.end_headers()
- rate limits are enforced for failed sign-ins and sign-ups
- database queries are parameterized

## Known gaps to record

- manager membership authorization is currently coupled directly to the session and selected store
- typed names are still treated as user identity in some workflows
- there is no explicit role matrix beyond manager versus crew
- no audit log of account actions or photo/media provenance exists yet
- the legacy crew sign-in path still uses shared credentials and store-level access

## Guardrails for future evolution

- derive tenant access from membership records, not from arbitrary request fields
- keep legacy employee names as report metadata, never as verified identity
- preserve original notes independently of AI-generated summaries
- do not trust supplied store IDs without authorization checks
- keep secret configuration out of version control and never log it
