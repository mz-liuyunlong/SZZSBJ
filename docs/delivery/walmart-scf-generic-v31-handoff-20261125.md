# Walmart SCF V3.1 handoff — 2026-11-25

Base: 0d438c101d44a733e551fe2d6ab9ca82046d5895. Branch: feat/walmart-scf-generic-20261125. Owner authorized Git implementation, not production change.

## Implementation candidate

- New internal generic client and v4 signed envelope, executor and HTTPS transport.
- Existing signing key, SSM resolver, store mapping, CAM/STS and SCF runtime reused.
- Existing v1/v2/v3 behavior retained, including old business controls; new v4 path is separate.
- New v4 response decoder reuses legacy PDF/ZIP checks, SCF outer/inner response limits adjusted only for the generic client.
- Bundle manifest and Python 3.10 smoke include v4. Offline pytest exercises full mocked chain.

## Verification

At commit preparation, complete repository checkout and local preflight are unavailable in the connector environment. No tests are claimed passed. GitHub CI and independent review are required before merge. No real provider call, production database, real secret, production configuration, migration, frontend or deployment was performed.

## Next

Check actual PR CI results; run applicable preflight where checkout is available; fix failures in this branch. Only after review and separate deployment authorization, record per-store stable aliases and verify existing configuration, publish CN2601 canary, verify old and new queries, and roll out the remaining eight stores. See integration documentation. No actual write operation is part of the rollout test.
