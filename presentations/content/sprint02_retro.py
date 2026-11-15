"""Sprint 2 Retrospective deck content (sprint 2026-11-02 → 2026-11-15)."""

DECK = {
    "slug": "sprint-02-retrospective",
    "title": "Sprint 2 Retrospective",
    "short_title": "Sprint 2 Retrospective",
    "subtitle": "What worked, what caused rework, and five actions for Sprint 3",
    "meta": [
        "Static report slides · Sprint 2: 2026-11-02 → 2026-11-15",
        "Produced 2026-11-15 from repository evidence; no retrospective meeting is recorded",
        "Team sentiment was not measured and is not invented",
    ],
    "slides": [
        {
            "layout": "bullets",
            "section": "Method",
            "title": "How this retrospective was written",
            "bullets": [
                "Inspected the repository, test results, evidence files and deliverable register",
                "Separated verifiable facts from assumptions about people",
                "No meeting minutes exist; no attendance or feedback is claimed",
                "Team members must replace assumptions with real observations",
            ],
        },
        {
            "layout": "columns",
            "section": "Facts",
            "title": "Went well / did not go well",
            "left": {
                "heading": "Went well",
                "bullets": [
                    "A full vertical slice works and is tested",
                    "Evidence is reproducible (tests, smoke JSON)",
                    "Mock is labelled, never presented as AI",
                    "Customer answers analysed quickly into a brief",
                    "Scope discipline: optional features frozen",
                    "Docs aligned to the team's v1.1 documents",
                ],
            },
            "right": {
                "heading": "Did not go well",
                "bullets": [
                    "No repository existed before 5 Nov",
                    "Upload/submission evidence not recorded",
                    "Requirements/design rewritten twice (v1.0→v1.2)",
                    "No capacity or team names all sprint",
                    "Living artifacts not accessible to supervisors",
                    "No real detector, long video or KPI measured",
                ],
            },
        },
        {
            "layout": "table",
            "section": "Causes",
            "title": "Root causes behind the misses",
            "columns": ["Cause", "Evidence", "Fix"],
            "rows": [
                ["No single source of truth for documents", "Team PDFs vs repo v1.0 vs v1.2", "Repo is source; PDFs generated from it"],
                ["No evidence protocol per deadline", "No upload record for 10/13 Nov", "Owner + evidence cell before work"],
                ["External inputs arrived late", "Guidelines 401; client answers 9 Nov", "Risk + human action with date"],
                ["No capacity data", "Empty team table", "Fill capacity before Sprint 3 planning"],
                ["Tooling fragility (encoding)", "PowerShell corrupted accents", "Verify encoding after scripted edits"],
            ],
            "font_size": 11,
        },
        {
            "layout": "table",
            "section": "Actions",
            "title": "Five actions with owners and dates",
            "columns": ["#", "Action", "By", "Signal"],
            "rows": [
                ["A-1", "Upload Status deck; record evidence", "16 Nov", "link in register"],
                ["A-2", "Record 10/13 Nov submission evidence", "17 Nov", "register updated"],
                ["A-3", "Write client answers into repo", "17 Nov", "CUSTOMER_DECISIONS updated"],
                ["A-4", "Fill capacity and supervisor access", "18 Nov", "table complete; link works"],
                ["A-5", "Validate a real 10–30 min video", "20 Nov", "smoke evidence with real file"],
            ],
            "font_size": 12,
        },
        {
            "layout": "quote",
            "section": "Experiment",
            "title": "Sprint 3 experiment",
            "text": "One source of truth: every document lives in the repository, and every submitted PDF is generated from it and recorded with owner, date and evidence.",
            "attribution": "Checked at Sprint 3 planning and at the 29 Nov gate",
        },
        {
            "layout": "bullets",
            "section": "Learning",
            "title": "What the sprint taught us",
            "bullets": [
                "A working prototype is not an MVP when the customer adds roles and access",
                "Documenting honestly costs less than explaining fabricated progress",
                "External approvals (privacy, guidelines) are schedule risks, not paperwork",
                "Mock-first was right: it exposed design flaws before the model arrived",
                "Re-baselining the gate with the supervisor is a decision, not a failure",
            ],
        },
        {
            "layout": "bullets",
            "section": "Honesty",
            "title": "What this retrospective does not know",
            "bullets": [
                "Who attended the 10 Nov presentation and what feedback was given",
                "What was submitted on 13 Nov, and how",
                "What the customer answered on 13 Nov",
                "How the team felt about the sprint",
                "Only the team can fill these gaps; guessing would poison Sprint 3",
            ],
        },
    ],
}
