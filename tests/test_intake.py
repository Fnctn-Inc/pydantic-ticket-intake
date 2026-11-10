import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from ticket_intake.agent import draft_ticket
from ticket_intake.cli import main
from ticket_intake.models import Proposal, Ticket, to_review_draft

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def ticket() -> Ticket:
    return Ticket.model_validate_json((EXAMPLES / "delivery-ticket.json").read_text())


@pytest.fixture
def proposal() -> dict:
    return json.loads((EXAMPLES / "delivery-proposal.json").read_text())


def test_source_offsets_and_staff_exclusion(ticket, proposal):
    def model(messages, info):
        user_prompt = next(part.content for message in messages for part in message.parts if isinstance(part, UserPromptPart))
        source = json.loads(user_prompt)
        assert [message["id"] for message in source["messages"]] == ["customer-1"]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, proposal)])

    result = asyncio.run(draft_ticket(ticket, FunctionModel(model)))
    assert result.status == "ready_for_review"
    assert result.suggested_queue == "delivery"
    for span in (result.issue, result.requested_outcome, result.order_reference):
        assert span is not None
        assert ticket.messages[0].text[span.start : span.end] == span.quote


def test_invalid_evidence_retries_then_accepts_correction(ticket, proposal):
    responses = []
    bad = {**proposal, "order_reference": {"message_id": "customer-1", "quote": "ORD-0000"}}

    def model(messages, info):
        retried = any(
            isinstance(part, ToolReturnPart) and part.content == "order_reference must quote the cited message exactly."
            for message in messages
            for part in message.parts
        )
        responses.append(retried)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, proposal if retried else bad)])

    result = asyncio.run(draft_ticket(ticket, FunctionModel(model)))
    assert result.order_reference.quote == "ORD-8492"
    assert responses == [False, True]


def test_persistent_fabrication_returns_no_draft(ticket, proposal):
    proposal["issue"]["quote"] = "The refund was approved."
    with pytest.raises(UnexpectedModelBehavior):
        def model(_messages, info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, proposal)])

        asyncio.run(draft_ticket(ticket, FunctionModel(model)))


@pytest.mark.parametrize(
    ("field", "message_id", "quote"),
    [
        ("issue", "staff-1", "Waiting for the warehouse team."),
        ("issue", "other-ticket", "nothing arrived"),
        ("issue", "customer-1", "NOTHING arrived"),
        ("order_reference", "customer-1", "8492"),
        ("order_reference", "customer-1", "ORD-849"),
    ],
)
def test_rejects_invalid_citations(ticket, proposal, field, message_id, quote):
    proposal[field] = {"message_id": message_id, "quote": quote}
    with pytest.raises(ValueError):
        to_review_draft(ticket, Proposal.model_validate(proposal))


def test_overlapping_occurrences_require_a_longer_quote(proposal):
    ticket = Ticket.model_validate(
        {"id": "t1", "messages": [{"id": "m1", "role": "customer", "text": "Aaaa."}]}
    )
    candidate = Proposal(category="other", issue={"message_id": "m1", "quote": "aa"},
                         requested_outcome=None, order_reference=None)
    with pytest.raises(ValueError, match="ambiguous"):
        to_review_draft(ticket, candidate)


def test_no_issue_abstains(ticket):
    fields = {"issue": None, "requested_outcome": None, "order_reference": None}
    assert to_review_draft(ticket, Proposal(category="other", **fields)).status == "needs_clarification"
    with pytest.raises(ValueError, match="requires an issue"):
        to_review_draft(ticket, Proposal(category="billing", **fields))


def test_duplicate_message_id_rejected(ticket):
    data = ticket.model_dump()
    data["messages"][1]["id"] = data["messages"][0]["id"]
    with pytest.raises(ValidationError, match="unique"):
        Ticket.model_validate(data)


def test_cli_exit_codes_and_parseable_stdout(tmp_path, capsys):
    ticket_path = str(EXAMPLES / "delivery-ticket.json")
    assert main([ticket_path, str(EXAMPLES / "delivery-proposal.json")]) == 0
    assert json.loads(capsys.readouterr().out)["ticket_id"] == "ticket-240"
    bad = tmp_path / "proposal.json"
    bad.write_text('{"unexpected":"field"}')
    assert main([ticket_path, str(bad)]) == 1
    result = capsys.readouterr()
    assert not result.out
    assert "Intake rejected" in result.err
