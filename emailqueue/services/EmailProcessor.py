import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

class TransientEmailException(Exception):
    """Temporary email failure that can be retried (e.g., SMTP timeout, 5xx server busy)."""
    pass

class PermanentEmailException(Exception):
    """Permanent email failure that cannot be retried (e.g., invalid address, blacklisted)."""
    pass

class EmailProcessor:
    def __init__(self, mockSendHandler: Optional[Callable[[str, str, str], bool]] = None):
        self.mockSendHandler = mockSendHandler

    def sendEmail(self, recipient: str, subject: str, body: str) -> bool:
        """
        Sends an email via the downstream email provider (mocked).
        Throws TransientEmailException or PermanentEmailException when test scenarios dictate.
        """
        if self.mockSendHandler is not None:
            return self.mockSendHandler(recipient, subject, body)

        # Built-in deterministic mock triggers based on recipient patterns for testing
        if recipient.endswith("@transient-fail.com"):
            raise TransientEmailException("Mock downstream SMTP server temporarily unavailable.")

        if recipient.endswith("@permanent-fail.com"):
            raise PermanentEmailException("Mock recipient mailbox does not exist.")

        logger.info("Mock email successfully dispatched to %s: [%s]", recipient, subject)
        return True

