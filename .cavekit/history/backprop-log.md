
## Entry 1

- date: 2026-07-28T12:00:00Z
- classification: superseded_test
- kit: cavekit-catalog-url-dispatch.md
- requirement: R4 (slot-based identifier resolution, formerly R3)
- ac_added: none
- failing_test_before_fix: tests/unit_test/action/test_catalog_bot_response.py::TestCatalogBotResponseDispatch::test_slot_identifier_resolves_slot_value
- fix_commit: (T-008 cleanup — source file already absent, pyc orphan)
- pattern_category: design_revision
- notes: Kits revised 2026-07-28 to move dispatch entry point from ActionKaironBotResponse to WhatsappBot.send_custom_json. Old test file deleted; stale .pyc triggered backprop. No kit amendment needed. Regression coverage for R4 reassigned to T-010 (test_whatsapp_catalog_dispatch.py).
