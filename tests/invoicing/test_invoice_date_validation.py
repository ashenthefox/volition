"""Date validation on the real invoice form parser (issue #37)."""

import pytest
from starlette.datastructures import FormData

from volition.core.errors import ValidationError
from volition.invoicing.models import ClientRecord, Invoice
from volition.invoicing.web.pages.invoice import parse_invoice_form

CLIENT = ClientRecord(id="c1", name="Example", address=["1 Example Street"])
BASE_FORM: dict[str, str | list[str]] = {
    "number": "42",
    "issueDate": "2026-09-19",
    "dueDate": "",
    "periodStart": "2026-09-01",
    "periodEnd": "2026-09-30",
    "vat": "on",
    "unit": "days",
    "clientId": "c1",
    "description": ["Backend development"],
    "quantity": ["2"],
    "rate": ["300"],
}


def invoice_from(**changes: str) -> Invoice:
    values = {**BASE_FORM, **changes}
    body = FormData(
        [(key, item) for key, value in values.items() for item in (value if isinstance(value, list) else [value])]
    )
    return parse_invoice_form(body, lambda key: CLIENT if key == "c1" else None)


def test_valid_dates_and_optional_dates_are_preserved() -> None:
    absent = invoice_from()
    assert absent.issue_date.isoformat() == "2026-09-19"
    assert absent.due_date is None
    assert absent.period is not None
    assert absent.period.start.isoformat() == "2026-09-01"
    assert absent.period.end.isoformat() == "2026-09-30"
    equal = invoice_from(dueDate="2026-09-19")
    assert equal.due_date is not None
    assert equal.due_date.isoformat() == "2026-09-19"
    later = invoice_from(dueDate="2026-10-19")
    assert later.due_date is not None
    assert later.due_date.isoformat() == "2026-10-19"
    no_period = invoice_from(periodStart="", periodEnd="")
    assert no_period.period is None


def test_due_date_cannot_precede_issue_date() -> None:
    with pytest.raises(ValidationError) as exc:
        invoice_from(dueDate="2026-09-18")
    assert exc.value.errors == ["Due date must be on or after the issue date"]


@pytest.mark.parametrize("missing", ["periodStart", "periodEnd"])
def test_period_requires_both_ends(missing: str) -> None:
    with pytest.raises(ValidationError) as exc:
        invoice_from(**{missing: ""})
    assert exc.value.errors == ["Give both ends of the period, or neither"]


@pytest.mark.parametrize(
    ("field", "value", "label"),
    [
        ("issueDate", "2026-02-31", "Issue date"),
        ("issueDate", "20260919", "Issue date"),
        ("dueDate", "2026-13-01", "Due date"),
        ("dueDate", "2026-W38-6", "Due date"),
        ("periodStart", "2026-02-30", "Period start"),
        ("periodEnd", "bogus", "Period end"),
    ],
)
def test_invalid_dates_get_a_field_specific_message(field: str, value: str, label: str) -> None:
    with pytest.raises(ValidationError) as exc:
        invoice_from(**{field: value})
    assert exc.value.errors == [f"{label} must be a valid date (YYYY-MM-DD)"]


def test_missing_issue_date_is_distinct_from_invalid_issue_date() -> None:
    with pytest.raises(ValidationError) as exc:
        invoice_from(issueDate="")
    assert exc.value.errors == ["Issue date is required"]


def test_reversed_calendar_period_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        invoice_from(periodStart="2026-10-01", periodEnd="2026-09-30")
    assert exc.value.errors == ["Period start must be on or before its end"]


def test_date_errors_are_aggregated_with_other_form_errors() -> None:
    with pytest.raises(ValidationError) as exc:
        invoice_from(issueDate="2026-02-31", dueDate="2026-02-30", periodStart="invalid", periodEnd="", clientId="")
    assert exc.value.errors == [
        "Issue date must be a valid date (YYYY-MM-DD)",
        "Due date must be a valid date (YYYY-MM-DD)",
        "Give both ends of the period, or neither",
        "Period start must be a valid date (YYYY-MM-DD)",
        "Choose a client",
    ]
