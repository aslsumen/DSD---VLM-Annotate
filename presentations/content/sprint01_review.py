"""Sprint 1 Review deck content (static slides, sprint ended 2026-11-01)."""

DECK = {
    "slug": "sprint-01-review",
    "title": "Sprint 1 Review",
    "short_title": "Sprint 1 Review",
    "subtitle": "What was delivered, what was missed, and what it cost",
    "meta": [
        "Static report slides · sprint 2026-10-19 → 2026-11-01",
        "Prepared 2026-11-05 · no review meeting is recorded in the repository",
        "Evidence: docs/sprint-reviews/sprint-01.md, docs/weekly-reports/week-01.md",
    ],
    "slides": [
        {
            "layout": "bullets",
            "section": "Context",
            "title": "Sprint 1 goal and constraints",
            "bullets": [
                "Course sprint 1: 2026-10-19 → 2026-11-01",
                "No MVP or prototype required at this gate",
                "One hard deliverable: Project Plan v1 slides, upload by 2026-11-02 23:59",
                "Presentation: Intro / Vision / Plan on 2026-11-03",
                "Constraint discovered later: official guidelines are behind a FER login",
            ],
        },
        {
            "layout": "table",
            "section": "Delivery",
            "title": "What was delivered",
            "columns": ["Item", "State", "Evidence"],
            "rows": [
                ["Course calendar + deliverables register", "Late (11-05)", "docs/course/"],
                ["Vision, scope, users, success criteria", "Late (11-05)", "docs/PROJECT_PLAN.md"],
                ["Risk register, backlogs, burndown", "Late (11-05)", "docs/"],
                ["Project Plan v1 slides", "Late (11-05)", "presentations/01-*.pptx"],
                ["Sprint 1 review + retro slides", "Late (11-05)", "presentations/sprint-01-*.pptx"],
            ],
            "font_size": 13,
        },
        {
            "layout": "bullets",
            "section": "Gaps",
            "title": "What was missed",
            "bullets": [
                "Project Plan v1 was not uploaded by 2026-11-02 23:59",
                "No outcome recorded for the 2026-11-03 presentation",
                "Official guideline files were never obtained (HTTP 401)",
                "No team names, capacity, time zones or meeting minutes",
                "Supervisor access to living artifacts not configured",
            ],
            "note": "These are recorded as facts in the deliverables register, not as excuses.",
        },
        {
            "layout": "quote",
            "section": "Increment",
            "title": "Demo: none",
            "text": "Sprint 1 produced no runnable software. None was required, but the planning artifacts "
            "that were required arrived after the deadline.",
            "attribution": "Verified by inspecting the repository: no application code existed before 2026-11-05",
            "tone": "warn",
        },
        {
            "layout": "bullets",
            "section": "Quality",
            "title": "Verification evidence for Sprint 1",
            "bullets": [
                "No tests, builds or measurements exist — there was no code",
                "No model evaluation was run",
                "No customer or supervisor feedback is recorded",
                "Any number in a Sprint 1 report would be invented, so there are none",
            ],
        },
        {
            "layout": "bullets",
            "section": "Backlog",
            "title": "Backlog and risk movement",
            "bullets": [
                "No Sprint 1 backlog was tracked in a repository",
                "Sprint 2 backlog created 2026-11-05: 18 tasks, 85 SP provisional",
                "R-05 opened: late Project Plan deck (occurred)",
                "R-01, R-04, R-12 opened: guidelines, capacity, supervisor access",
            ],
        },
        {
            "layout": "bullets",
            "section": "Outcome",
            "title": "Sprint 1 verdict",
            "bullets": [
                "Goal: partially met, entirely late",
                "Course deadline: MISSED",
                "MVP gate: not applicable in Sprint 1",
                "Recovery: build the missing artifacts, upload immediately, notify the supervisor",
                "Carry-over: deck upload, guideline download, capacity and access setup",
            ],
        },
        {
            "layout": "checklist",
            "section": "Actions",
            "title": "What happens next",
            "items": [
                "Upload the late Project Plan v1 deck and tell the supervisor",
                "Download the three official guideline files",
                "Fill team names, roles, capacity and time zones",
                "Grant supervisors access to backlog and burndown",
                "Write minutes for any Week 1 meeting that actually happened",
            ],
        },
    ],
}
