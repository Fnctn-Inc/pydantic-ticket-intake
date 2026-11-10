import argparse
import asyncio
import sys
from pathlib import Path

from pydantic import ValidationError
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from .agent import draft_ticket
from .models import Proposal, Ticket


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a saved model proposal through Pydantic AI.")
    parser.add_argument("ticket", type=Path, help="ticket JSON file")
    parser.add_argument("proposal", type=Path, help="model proposal JSON file")
    args = parser.parse_args(argv)
    try:
        ticket = Ticket.model_validate_json(args.ticket.read_text(encoding="utf-8"))
        proposal = Proposal.model_validate_json(args.proposal.read_text(encoding="utf-8"))

        def replay(_messages, info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, proposal.model_dump())])

        draft = asyncio.run(draft_ticket(ticket, FunctionModel(replay)))
    except (OSError, ValidationError, UnexpectedModelBehavior) as error:
        print(f"Intake rejected ({type(error).__name__}). Check the ticket schema and source quotes.", file=sys.stderr)
        return 1
    print(draft.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
