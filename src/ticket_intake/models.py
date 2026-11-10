import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Category = Literal["billing", "delivery", "account_access", "other"]


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Message(StrictRecord):
    id: Identifier
    role: Literal["customer", "staff"]
    text: Annotated[str, Field(min_length=1, max_length=8_000)]


class Ticket(StrictRecord):
    id: Identifier
    messages: Annotated[list[Message], Field(min_length=1, max_length=30)]

    @model_validator(mode="after")
    def unique_message_ids(self) -> "Ticket":
        if len({message.id for message in self.messages}) != len(self.messages):
            raise ValueError("Message IDs must be unique within the ticket.")
        return self


class Evidence(StrictRecord):
    message_id: Identifier
    quote: Annotated[str, Field(min_length=1, max_length=400)]


class Proposal(StrictRecord):
    category: Category
    issue: Evidence | None
    requested_outcome: Evidence | None
    order_reference: Evidence | None


class SourceSpan(Evidence):
    start: int
    end: int


class ReviewDraft(StrictRecord):
    ticket_id: Identifier
    suggested_queue: Category
    status: Literal["ready_for_review", "needs_clarification"]
    issue: SourceSpan | None
    requested_outcome: SourceSpan | None
    order_reference: SourceSpan | None


def resolve_span(customer_messages: dict[str, str], evidence: Evidence, field: str) -> SourceSpan:
    source = customer_messages.get(evidence.message_id)
    if source is None:
        raise ValueError(f"{field} must cite a customer message from this ticket.")
    start = source.find(evidence.quote)
    if not evidence.quote.strip() or start < 0:
        raise ValueError(f"{field} must quote the cited message exactly.")
    if source.find(evidence.quote, start + 1) != -1:
        raise ValueError(f"{field} is ambiguous. Use a longer unique quote.")
    end = start + len(evidence.quote)
    if field == "order_reference":
        whole_reference = any(
            (start, end) == match.span()
            for match in re.finditer(r"(?<![\w-])ORD-[0-9]{4,12}(?![\w-])", source)
        )
        if not whole_reference:
            raise ValueError("order_reference must be a complete ORD-number from the source.")
    return SourceSpan(message_id=evidence.message_id, quote=evidence.quote, start=start, end=end)


def to_review_draft(ticket: Ticket, proposal: Proposal) -> ReviewDraft:
    if proposal.issue is None and proposal.category != "other":
        raise ValueError("A suggested queue requires an issue quote. Use other if the issue is unclear.")
    customer_messages = {message.id: message.text for message in ticket.messages if message.role == "customer"}
    fields = {}
    for field in ("issue", "requested_outcome", "order_reference"):
        evidence = getattr(proposal, field)
        fields[field] = resolve_span(customer_messages, evidence, field) if evidence is not None else None
    return ReviewDraft(
        ticket_id=ticket.id,
        suggested_queue=proposal.category,
        status="ready_for_review" if proposal.issue is not None else "needs_clarification",
        **fields,
    )
