"""Sprint 1 Retrospective deck content (static slides)."""

DECK = {
    "slug": "sprint-01-retrospective",
    "title": "Sprint 1 Retrospective",
    "short_title": "Sprint 1 Retrospective",
    "subtitle": "Facts, root causes, and six actions for Sprint 2",
    "meta": [
        "Static report slides · sprint 2026-10-19 → 2026-11-01",
        "Prepared 2026-11-05 from repository evidence; not a record of a retrospective meeting",
        "Team sentiment was not measured and is not invented",
    ],
    "slides": [
        {
            "layout": "bullets",
            "section": "Method",
            "title": "How this retrospective was produced",
            "bullets": [
                "Inspected the repository, git state, calendar and deliverables register",
                "Separated verifiable facts from assumptions about people",
                "No meeting happened in the repository; no attendance is claimed",
                "Team members must replace assumptions with real observations",
            ],
        },
        {
            "layout": "columns",
            "section": "Facts",
            "title": "What went well / what did not",
            "left": {
                "heading": "Went well",
                "bullets": [
                    "Course calendar and deliverable types captured accurately",
                    "Product vision, users and success criteria now written",
                    "Scope frozen early: MVP vs optional",
                    "Backlog and risks exist and are actionable",
                ],
            },
            "right": {
                "heading": "Did not go well",
                "bullets": [
                    "No repository during Sprint 1",
                    "Project Plan upload deadline missed",
                    "Guidelines never obtained",
                    "No capacity or ownership data",
                    "Living artifacts not supervisor-accessible",
                    "No minutes, including the mandatory session",
                ],
            },
        },
        {
            "layout": "table",
            "section": "Causes",
            "title": "Root causes, not symptoms",
            "columns": ["Cause", "Evidence", "Fix"],
            "rows": [
                ["No owner for the upload step", "Register had TBD everywhere", "Named owner + evidence cell"],
                ["External blocker not escalated", "Materials return 401", "Risk with human action and date"],
                ["No daily decomposition", "All work on 11-05", "Daily gate plan in Sprint Backlog"],
                ["'Done' meant 'exists'", "Deck built, never uploaded", "Done = uploaded + evidence"],
            ],
            "font_size": 12,
        },
        {
            "layout": "table",
            "section": "Actions",
            "title": "Six actions with dates",
            "columns": ["#", "Action", "By", "Signal"],
            "rows": [
                ["A-1", "Upload late deck, notify supervisor", "11-06", "link in register"],
                ["A-2", "Download 3 guideline files", "11-06", "checklist INSPECTED"],
                ["A-3", "Fill roles, capacity, time zones", "11-06", "capacity table complete"],
                ["A-4", "Supervisor access to artifacts", "11-07", "link in register"],
                ["A-5", "Hold a real retrospective", "11-15", "minutes attached"],
                ["A-6", "Minutes for any Week 1 meeting", "11-06", "file or 'none held'"],
            ],
            "font_size": 12,
        },
        {
            "layout": "quote",
            "section": "Experiment",
            "title": "Sprint 2 experiment",
            "text": "Every course artifact has a named owner and an upload-evidence cell before work starts.",
            "attribution": "Checked at the mid-sprint review on 2026-11-11 and at sprint close",
        },
        {
            "layout": "bullets",
            "section": "Measurement",
            "title": "What we will watch in Sprint 2",
            "bullets": [
                "Was the Requirements & Design deck uploaded by 2026-11-09 23:59?",
                "Were Requirements v1 and Design v1 frozen by 2026-11-13?",
                "Is the MVP testable on 2026-11-15 with evidence?",
                "Did every deck/document have an owner at creation time?",
                "Is supervisor access working, not just promised?",
            ],
        },
        {
            "layout": "bullets",
            "section": "Honesty",
            "title": "What this retrospective does not know",
            "bullets": [
                "Why no work reached the repository before 2026-11-05",
                "Who attended which meeting",
                "What the supervisor or customer said on 2026-11-03",
                "How the team feels about the sprint",
                "Only the team can fill these gaps — guessing would poison the next sprint",
            ],
        },
    ],
}
