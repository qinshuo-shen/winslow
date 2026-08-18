"""
One-time categorization: assign the real tags in this project's database
to the 5 top-level "Project" tags the user named directly (PhD core, PhD
side, Education, ASPARi operation, Personal), confirmed with the user
rather than guessed -- see tasks.set_tag_parent()/list_tags() for the
underlying two-level hierarchy this populates.

Run manually, once, from the repo root:

    python -m procrastination_tool.reclassify_tags

Safe to re-run -- set_tag_parent() is an upsert (creates a tag if it
doesn't exist yet, otherwise just updates its parent), so running this
twice is a no-op the second time. If you add a new tag later that belongs
under one of these 5 projects, either add it to the mapping below and
re-run, or set it directly via POST /api/tags {name, parent} from the app.

Tags not listed below (e.g. "Other", Notion's literal catch-all) are left
as-is -- top-level, uncategorized -- rather than force-fit into one of the
5 projects.
"""
from . import auth, tasks

_MAPPING = {
    "PhD core": [
        "Research", "Proposal", "Qualifier", "Data management",
        "Scientific Information", "Paper 1", "Paper 2", "Paper 3", "Paper 4",
        "ISARC 2024", "ISARC 2025", "Simulator", "Defense external assessor",
    ],
    "PhD side": [
        "Department", "Seminar", "Workshop", "Summer school", "UHI", "WSLS",
    ],
    "Education": [
        "Coursework", "Machine Learning Course", "Simulation Course",
        "Road Construction Course", "Module 8", "Teaching",
        "Teaching and Supervision", "BSc supervision", "MSc supervision",
        "Taste of Teaching", "Presentation Skills",
        "Gerko-Van Gelder", "DTC", "ARS", "Visual Storytelling",
    ],
    "ASPARi operation": [
        "ASPARi symposium", "Office", "PQi",
    ],
    "Personal": [
        "Personal and Service", "Personal life", "Personal finance",
        "Dutch", "Futsal", "Vibe coding", "Programming",
    ],
}


def reclassify() -> None:
    # Multi-user follow-up: this is the owner's own personal tag taxonomy
    # (real project names like "PhD core"), so it always applies to the
    # owner's account specifically -- same "no HTTP session to read a
    # user_id from, so resolve the owner directly" reasoning as
    # focus_cli.py.
    owner = auth.get_owner_user()
    if owner is None:
        raise RuntimeError("No account exists yet -- run scripts/create_user.py first.")

    for project in _MAPPING:
        tasks.set_tag_parent(owner.id, project, None)  # ensure it's top-level, not nested

    applied = 0
    for project, sub_tags in _MAPPING.items():
        for sub_tag in sub_tags:
            tasks.set_tag_parent(owner.id, sub_tag, project)
            applied += 1

    all_tags = {t.name for t in tasks.list_tags(owner.id)}
    mapped = {name for names in _MAPPING.values() for name in names} | set(_MAPPING.keys())
    unmapped = sorted(all_tags - mapped)

    print(f"Top-level projects ensured: {len(_MAPPING)}")
    print(f"Sub-tags reclassified: {applied}")
    if unmapped:
        print(f"Left uncategorized (top-level, not in any mapping): {unmapped}")


if __name__ == "__main__":
    reclassify()
