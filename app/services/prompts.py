"""The one prompt that powers the whole 'AI feature'."""

SYSTEM_PROMPT = (
    "You are a support-ticket triage assistant. You read one support ticket "
    "and classify it. You respond with ONLY valid JSON and no other text."
)

USER_PROMPT_TEMPLATE = """Analyze this support ticket and respond with ONLY valid JSON in exactly this shape:
{{
  "category": one of ["billing", "bug", "refund", "account", "other"],
  "urgency_score": integer 1-10 (10 = business-critical, angry customer, money lost),
  "summary": one sentence, max 20 words,
  "suggested_reply": a polite 2-3 sentence draft reply to the customer
}}

Ticket subject: {subject}
Ticket body: {body}
"""


def build_user_prompt(subject: str, body: str) -> str:
    return USER_PROMPT_TEMPLATE.format(subject=subject, body=body)
