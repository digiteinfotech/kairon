---
created: "2026-07-23T00:00:00Z"
last_edited: "2026-07-28T00:00:00Z"
---

# Cavekit: Catalog Utterance — Overview

## Project

Adds a catalog bot response that, at dispatch time, builds a catalog URL and sends it to the user as a text message. The URL encodes a page name, the bot id, an encrypted identifier, and a session token. The catalog response is stored as an ordinary custom response using an agreed payload convention (`custom.type == "catalog"`) — no new response type, storage document, or API endpoint is introduced.

## Domain Index

| Domain | Cavekit File | Requirements | Status | Description |
|--------|-------------|-------------|--------|-------------|
| catalog-custom-response | cavekit-catalog-custom-response.md | 4 | DRAFT | Catalog payload convention, storage and round-trip through the existing custom-response path |
| catalog-url-dispatch | cavekit-catalog-url-dispatch.md | 11 | DRAFT | Type registration, tracker retrieval, identifier resolution (slot/value), fallback, encryption, token, URL assembly, text/link dispatch, logging |

## Cross-Reference Map

| Domain A | Interacts With | Interaction Type |
|----------|---------------|-----------------|
| catalog-url-dispatch | catalog-custom-response | depends on — dispatch consumes the stored catalog payload |

## Dependency Graph

1. `catalog-custom-response` — no dependencies (implement first)
2. `catalog-url-dispatch` — depends on `catalog-custom-response` (payload convention, R1)

## Coverage Summary

- Domains: 2
- Requirements: 15 (4 + 11)
- Acceptance criteria: 51 (17 + 34)

## Changelog

- 2026-07-23: Revised design. Replaced the earlier dedicated-enum / ResponseCatalog model with the custom-response payload convention; split into catalog-custom-response (storage) and catalog-url-dispatch (dispatch).
- 2026-07-28: Updated for optional label field — R1 and R3 in catalog-custom-response, R9 in catalog-url-dispatch.
