from __future__ import annotations

from .contracts import IncomingMessage


class AccountGatewayService:
    def should_process_message(self, message: IncomingMessage) -> tuple[bool, str | None]:
        if message.channel_type == "private":
            return True, None
        if message.channel_type == "group" and message.mentioned_owner:
            return True, None
        return False, "message is outside the owner proxy scope"

