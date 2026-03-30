"""
System 4 — WAGGLE PROTOCOL (Apis mellifera)

The sensory and decision-making system of SYMBIONT. When the organism faces
a decision with multiple alternatives, this protocol activates instead of
delegating to a single agent.

Key biological properties:
- Scouts explore options independently (no communication between them)
- Waggle dance encodes quality + confidence in structured reports
- Amplification: strong reports recruit more scouts to validate
- Quorum: decision emerges when N agents converge on same option
- Dynamic thresholds: reversible decisions need less quorum than irreversible ones
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from symbiont.config import WaggleConfig
from symbiont.types import QuorumLevel, WaggleReport

logger = logging.getLogger(__name__)


@dataclass
class WaggleSession:
    """A single decision-making session."""
    id: str
    question: str
    quorum_level: QuorumLevel
    reports: list[WaggleReport] = field(default_factory=list)
    votes: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    decision: str | None = None
    decided: bool = False

    @property
    def quorum_threshold(self) -> int:
        return self.quorum_level.value

    def tally(self) -> dict[str, float]:
        """Tally votes weighted by intensity."""
        scores: dict[str, float] = defaultdict(float)
        for report in self.reports:
            scores[report.option] += report.intensity
        return dict(scores)

    def check_quorum(self) -> str | None:
        """Check if any option has reached quorum. Returns winning option or None."""
        option_voters: dict[str, set[str]] = defaultdict(set)
        for report in self.reports:
            option_voters[report.option].add(report.scout_id)

        for option, voters in option_voters.items():
            if len(voters) >= self.quorum_threshold:
                return option
        return None


# Type for scout dispatch function
ScoutDispatcher = Callable[[str, str], Coroutine[Any, Any, WaggleReport | None]]


class WaggleProtocol:
    """
    Bee-inspired collective decision-making.

    No single agent makes important decisions. The system collectively
    decides through exploration, amplification, and quorum.
    """

    def __init__(self, config: WaggleConfig | None = None) -> None:
        self.config = config or WaggleConfig()
        self._sessions: dict[str, WaggleSession] = {}
        self._scout_dispatcher: ScoutDispatcher | None = None

    def set_scout_dispatcher(self, dispatcher: ScoutDispatcher) -> None:
        """
        Register the function that dispatches scouts to explore options.
        Called by the organism during wiring.

        The dispatcher receives (session_id, question) and returns a WaggleReport.
        """
        self._scout_dispatcher = dispatcher

    async def initiate(
        self,
        session_id: str,
        question: str,
        quorum_level: QuorumLevel = QuorumLevel.MEDIUM,
    ) -> WaggleSession:
        """
        Start a new decision session.

        Phase 1 — DIVERGE: dispatch scouts to explore alternatives independently.
        """
        session = WaggleSession(
            id=session_id,
            question=question,
            quorum_level=quorum_level,
        )
        self._sessions[session_id] = session

        logger.info(
            "waggle: session '%s' started (quorum=%d, question='%s')",
            session_id,
            session.quorum_threshold,
            question[:80],
        )

        # Phase 1: Diverge — dispatch scouts in parallel
        if self._scout_dispatcher:
            scout_count = min(self.config.max_scouts, max(self.config.min_scouts, session.quorum_threshold + 1))
            tasks = [
                asyncio.create_task(
                    self._dispatch_with_timeout(session_id, question)
                )
                for _ in range(scout_count)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, WaggleReport):
                    session.reports.append(result)

        logger.info(
            "waggle: session '%s' diverge complete — %d reports collected",
            session_id,
            len(session.reports),
        )

        # Phase 2: Dance — amplify strong reports
        await self._amplify(session)

        # Phase 3: Recruit — validate top options (additional rounds)
        for _ in range(self.config.recruitment_rounds):
            winner = session.check_quorum()
            if winner:
                break
            await self._recruit(session)

        # Phase 4: Quorum check
        winner = session.check_quorum()
        if winner:
            session.decision = winner
            session.decided = True
            logger.info("waggle: session '%s' decided: '%s'", session_id, winner)
        else:
            # No quorum — escalate
            tally = session.tally()
            if tally:
                # Pick highest-scored option as suggestion (not decided)
                session.decision = max(tally, key=tally.get)
                logger.warning(
                    "waggle: session '%s' no quorum — suggesting '%s' (score=%.2f)",
                    session_id,
                    session.decision,
                    tally[session.decision],
                )

        return session

    async def submit_report(self, session_id: str, report: WaggleReport) -> None:
        """Manually submit a report to an active session."""
        session = self._sessions.get(session_id)
        if session and not session.decided:
            session.reports.append(report)

    async def _dispatch_with_timeout(self, session_id: str, question: str) -> WaggleReport | None:
        try:
            return await asyncio.wait_for(
                self._scout_dispatcher(session_id, question),
                timeout=self.config.scout_timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.warning("waggle: scout timed out for session '%s'", session_id)
            return None
        except Exception:
            logger.exception("waggle: scout failed for session '%s'", session_id)
            return None

    async def _amplify(self, session: WaggleSession) -> None:
        """
        Phase 2 — DANCE: strong reports are amplified (more visible).
        Weak reports decay naturally.
        """
        for report in session.reports:
            if report.intensity >= self.config.amplification_threshold:
                # Amplification: create a synthetic "vote" for this option
                session.votes[report.option].append(report.scout_id)
                logger.debug(
                    "waggle: amplified '%s' (intensity=%.2f)",
                    report.option,
                    report.intensity,
                )

    async def _recruit(self, session: WaggleSession) -> None:
        """
        Phase 3 — RECRUIT: send additional scouts to validate top options.
        This is independent validation, not groupthink.
        """
        if not self._scout_dispatcher:
            return

        tally = session.tally()
        if not tally:
            return

        # Recruit scouts to validate the top 2 options
        top_options = sorted(tally, key=tally.get, reverse=True)[:2]
        for option in top_options:
            validation_q = f"Validate option: {option}. Original question: {session.question}"
            report = await self._dispatch_with_timeout(session.id, validation_q)
            if report:
                session.reports.append(report)

    def get_session(self, session_id: str) -> WaggleSession | None:
        return self._sessions.get(session_id)

    def get_all_sessions(self) -> dict[str, WaggleSession]:
        return dict(self._sessions)
