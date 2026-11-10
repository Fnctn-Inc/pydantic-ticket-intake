# Pydantic Ticket Intake

Turn a support conversation into a review draft with links back to the customer's words. A Pydantic AI output validator checks every quote against the source ticket, adds character offsets, and gives the model one retry if a quote is missing, ambiguous, or invented.

## Try it with a saved model response

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run these commands from the repository root.

```sh
uv sync --locked
uv run --locked ticket-intake examples/delivery-ticket.json examples/delivery-proposal.json
uv run --locked pytest
```

The CLI replays the saved proposal through Pydantic AI's `FunctionModel` with no API key. It prints JSON on success and exits with status 1 if the input or evidence fails validation. Change the order number in the proposal to see the rejection. To use your own Pydantic AI model, import `draft_ticket` from `ticket_intake.agent` and call `await draft_ticket(ticket, model)` with a configured provider model.

## What the review draft means

| Field | Behavior |
| --- | --- |
| `suggested_queue` | A model suggestion for billing, delivery, account access, or other. A concrete queue requires a cited issue. |
| `issue`, `requested_outcome` | Exact text from an identified customer message, or `null` when evidence is missing. |
| `order_reference` | A whole customer-supplied reference in the example's `ORD-1234` format, or `null`. |
| `start`, `end` | Zero-based Python string indexes into the original message. `source[start:end]` reconstructs the quote. |
| `status` | `ready_for_review` when an issue has evidence, or `needs_clarification` when there is no cited issue. |

Only customer messages are sent to the configured model. The quote checks prove where text came from. A reviewer still decides whether it supports the suggested queue or requested action. The package produces review data and performs no ticket routing, refunds, or customer messaging. The bundled ticket is synthetic. A provider-backed deployment needs your team's data-handling policy.

For a practical rollout example, see the [Agentec customer support pilot](https://www.agentec.io/industries/customer-service). For the framework APIs, see [Pydantic AI output validation](https://pydantic.dev/docs/ai/core-concepts/output/) and [testing](https://pydantic.dev/docs/ai/guides/testing/).
