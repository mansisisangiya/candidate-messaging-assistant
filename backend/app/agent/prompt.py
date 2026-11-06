from app.llm.base import ChatMessage
from app.models import Conversation

SYSTEM_PROMPT = (
    "You are an assistant that drafts replies for a recruiter to candidate messages. "
    "Use the tools to look up the candidate, their interview status and the job. "
    "Only state facts returned by tools; never invent dates or compensation details. "
    "If a tool fails, do not promise anything that depends on it. "
    "Reply with the draft message text only."
)


def build_messages(conversation: Conversation, instructions: str | None) -> list[ChatMessage]:
    transcript = "\n".join(f"[{m.sender}] {m.text}" for m in conversation.messages)
    user_text = (
        f"Conversation: {conversation.id}\n"
        f"Candidate ID: {conversation.candidate_id}\n"
        f"Transcript:\n{transcript}\n"
        f"Recruiter instructions: {instructions or 'none'}"
    )
    return [ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_text)]
