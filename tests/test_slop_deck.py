"""An invented slide deck that plants every slop shape seen in generated decks: stock title
templates, "X, not Y" kickers with no period, dash negations, bare denials, maxims, slogan
sentence runs and slogan commands. Each planted line must be flagged by at least one rule, and the
deck as a whole must score well below a clean document."""

import pytest

from clarity.config import load_config
from clarity.engine import analyze

DECK = {
    "title": "Four branches. One shared catalog.",
    "subtitle": "Library systems proposal",
    "sections": [
        {"title": "One catalog. Two ways to borrow.",
         "subtitle": "Connect readers to resources",
         "text": "Keep the archive complete. Keep the loans quick.",
         "items": ["Catalog access, audit trail and tags for every shelf list."]},
        {"title": "Six vendors. No surprises.",
         "subtitle": "Capture what matters most",
         "text": "Scan first. Shelve the book second.",
         "items": ["Vendor files arrive nightly over SFTP."]},
        {"title": "Earn trust with every release.",
         "subtitle": "Plain notices, not five reminder emails",
         "text": "Momentum flows outward. Signed approvals decide what reaches the shelves.",
         "items": ["Requests are not loans."]},
        {"title": "A family card is not a family account.",
         "subtitle": "A lost hold is worse than a slow hold",
         "text": "Staff rotate. Policies stay. A new cardholder must not see the old loans.",
         "items": ["Missing scan ≠ confirmed return."]},
        {"title": "Late fees stay visible. Bad records stay out.",
         "subtitle": "A reading habit, not a borrowing metric",
         "text": "Every check has a librarian and a fix path.",
         "items": ["Fines, holds and renewals—not just barcode scans.",
                   "Unknown age is not consent."]},
        {"title": "Three services. Different promises.",
         "subtitle": "Priority order",
         "text": "Use cached records for speed and check holds before any notice.",
         "items": ["Checkout speed is not accuracy.",
                   "Every overdue book back by the due date—not merely “notice sent.”"]},
        {"title": "Membership is not access.",
         "subtitle": "A barcode never proves residency",
         "text": "One decision per reader and branch.",
         "items": ["Quiet failure is not success."]},
        {"title": "Volunteers suggest. Librarians decide.",
         "subtitle": "Supervised self-service",
         "text": "Volunteers sort returns. Librarians check each change before it goes live."},
        {"title": "Pilot one branch. Then earn the right to grow.",
         "subtitle": "Order services, not tools",
         "items": ["Card renewal and fines come before new branches, not after them"]},
        {"title": "The tricky part is not the software.",
         "subtitle": "Close risk with clear owners",
         "text": "Guard reader privacy. Make delays visible. Grow on results."},
    ],
}

# (planted text, rules any one of which must flag it)
PLANTED = [
    ("Four branches. One shared catalog.", {"stock-title-shape", "weak-title"}),
    ("Connect readers to resources", {"slogan-imperative-title"}),
    ("Capture what matters most", {"slogan-imperative-title"}),
    ("Scan first. Shelve the book second.", {"slogan-sentence-run"}),
    ("Earn trust with every release.", {"abstract-physical-verb", "slogan-imperative-title"}),
    ("Plain notices, not five reminder emails", {"trailing-negation"}),
    ("Momentum flows outward.", {"abstract-physical-verb-catalogued"}),
    ("Requests are not loans.", {"bare-denial"}),
    ("A family card is not a family account.", {"bare-denial"}),
    ("A lost hold is worse than a slow hold", {"comparative-maxim"}),
    ("Staff rotate. Policies stay.", {"slogan-sentence-run"}),
    ("Missing scan ≠ confirmed return.", {"bare-denial"}),
    ("A reading habit, not a borrowing metric", {"trailing-negation"}),
    ("Fines, holds and renewals—not just barcode scans.", {"trailing-negation"}),
    ("Unknown age is not consent.", {"bare-denial"}),
    ("Checkout speed is not accuracy.", {"bare-denial"}),
    ("Every overdue book back by the due date—not merely “notice sent.”", {"trailing-negation"}),
    ("Membership is not access.", {"bare-denial"}),
    ("A barcode never proves residency", {"bare-denial"}),
    ("Quiet failure is not success.", {"bare-denial"}),
    ("Volunteers suggest. Librarians decide.", {"stock-title-shape", "weak-title"}),
    ("Then earn the right to grow.", {"abstract-physical-verb"}),
    ("Order services, not tools", {"trailing-negation"}),
    ("Card renewal and fines come before new branches, not after them", {"trailing-negation"}),
    ("The tricky part is not the software.", {"sig-noun-phrase", "bare-denial"}),
    ("Close risk with clear owners", {"slogan-imperative-title"}),
    ("Guard reader privacy. Make delays visible. Grow on results.", {"slogan-sentence-run"}),
]


@pytest.fixture(scope="module")
def result():
    return analyze(DECK, config=load_config(None))


def _rules_on(result, planted):
    """Rules (experimental ones included) with a finding inside the planted text."""
    found = set()

    for f in result["findings"]:
        context = f.get("context", "")

        if context and (context in planted or planted in context):
            found.add(f["rule"])

    return found


@pytest.mark.parametrize(("planted", "rules"), PLANTED)
def test_every_planted_line_is_flagged(result, planted, rules):
    assert _rules_on(result, planted) & rules, f"{planted!r} not flagged by any of {sorted(rules)}"


def test_the_deck_is_flagged_for_one_title_template(result):
    assert any(f["rule"] == "repeated-title-shape" for f in result["findings"])


def test_the_deck_scores_well_below_a_clean_document(result):
    assert result["score"] < 80, result["score"]
