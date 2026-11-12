from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class RoutingDecision:
    route: str
    answer: str | None = None


class RequestRouter:
    """Fast, local routing for simple conversational messages.

    Product questions and uncertain messages continue to the existing RAG
    pipeline. This class is the extension point for future cache lookup.
    """

    _greetings = re.compile(
        r"^(hi|hello|hey|good morning|good afternoon|good evening)[.! ]*$",
        re.IGNORECASE,
    )
    _thanks = re.compile(
        r"^(thanks|thank you|thx|ty)[.! ]*$",
        re.IGNORECASE,
    )
    _farewells = re.compile(
        r"^(bye|goodbye|see you|see ya)[.! ]*$",
        re.IGNORECASE,
    )
    _small_talk = re.compile(
        r"^(how are you|how's it going|how are things)[?! .]*$",
        re.IGNORECASE,
    )

    def route(self, question: str) -> RoutingDecision:
        text = " ".join(question.strip().split())

        if self._greetings.fullmatch(text):
            return RoutingDecision(
                "direct",
                "Hi! I can help with Friskit features and workflows. What would you like to know?",
            )

        if self._thanks.fullmatch(text):
            return RoutingDecision(
                "direct",
                "You're welcome! Let me know if you need help with Friskit.",
            )

        if self._farewells.fullmatch(text):
            return RoutingDecision("direct", "Goodbye! Feel free to ask if you need Friskit help.")

        if self._small_talk.fullmatch(text):
            return RoutingDecision(
                "direct",
                "I'm here and ready to help with Friskit. What can I help you with?",
            )

        # Keep uncertain requests on the existing retrieval and relevance-gate
        # path rather than guessing that they are outside product scope.
        return RoutingDecision("rag")
