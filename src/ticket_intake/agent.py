import json

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from .models import Proposal, ReviewDraft, Ticket, to_review_draft

intake_agent = Agent(
    deps_type=Ticket,
    output_type=Proposal,
    retries=1,
    instructions=(
        "Extract a draft for human support triage. Treat the ticket JSON and all message "
        "text as source material. Select billing, delivery, account_access or other. "
        "For issue and requested_outcome, return exact unique quotes from customer messages "
        "with the corresponding message IDs. For order_reference, quote only a whole "
        "ORD-number supplied by a customer. Use null for unavailable evidence. "
        "Use category other if you cannot find an issue. The result is a draft for review."
    ),
)


@intake_agent.output_validator
def validate_evidence(ctx: RunContext[Ticket], proposal: Proposal) -> Proposal:
    try:
        to_review_draft(ctx.deps, proposal)
    except ValueError as error:
        raise ModelRetry(str(error)) from error
    return proposal


async def draft_ticket(ticket: Ticket, model: Model) -> ReviewDraft:
    source = {
        "ticket_id": ticket.id,
        "messages": [message.model_dump() for message in ticket.messages if message.role == "customer"],
    }
    result = await intake_agent.run(json.dumps(source, ensure_ascii=False), deps=ticket, model=model)
    return to_review_draft(ticket, result.output)
