"""Rules first, then a local classifier, then a recorded mid-run switch."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from runbyus.common.models import Classification, Route, WorkItem
from runbyus.common.policy import Policy

Classifier = Callable[[str], Classification]


@dataclass(frozen=True)
class PlannedRoute:
    space: str
    label: str
    agent: str
    provider: str
    model: str
    tier: str
    risk: str
    confidence: float
    reason: str
    intent: str = ""


def default_classifier(text: str) -> Classification:
    lowered = text.lower()
    if "vlan" in lowered or "powerdns" in lowered or "dns" in lowered:
        return Classification(
            space="infra",
            label="infra",
            intent="diagnose_dns",
            complexity="medium",
            risk="impactful",
            needs_tools=True,
            confidence=0.86,
        )
    return Classification(
        space="p1",
        label="personal",
        intent="chat",
        complexity="low",
        risk="read",
        needs_tools=False,
        confidence=0.82,
    )


def _agent_for(space: str, rule_agent: str = "") -> str:
    if rule_agent:
        return rule_agent
    if space == "infra":
        return "infra"
    if space == "family":
        return "list"
    return "assistant"


class Router:
    def __init__(self, ledger, policy: Policy, emitter, classifier: Classifier | None = None):
        self.ledger = ledger
        self.policy = policy
        self.emitter = emitter
        self.classifier = classifier or default_classifier

    def plan(self, text: str) -> PlannedRoute:
        body = (text or "").strip()
        for rule in self.policy.match_rules():
            if re.search(rule["match"], body):
                return PlannedRoute(
                    space=str(rule.get("space") or "family"),
                    label=str(rule.get("label") or "shared"),
                    agent=_agent_for(str(rule.get("space") or "family"), str(rule.get("agent") or "")),
                    provider=str(rule.get("provider") or "none"),
                    model=str(rule.get("model") or ""),
                    tier=str(rule.get("tier") or "rules"),
                    risk=str(rule.get("risk") or "read"),
                    confidence=1.0,
                    reason=str(rule.get("reason") or "static rule"),
                    intent=str(rule.get("agent") or "list"),
                )
        result = self.classifier(body)
        if result.confidence < 0.7:
            return PlannedRoute(
                space=result.space,
                label=result.label,
                agent=_agent_for(result.space),
                provider="local",
                model="llama-large",
                tier="escalated",
                risk=result.risk,
                confidence=result.confidence,
                reason="classifier below 0.7",
                intent=result.intent,
            )
        return PlannedRoute(
            space=result.space,
            label=result.label,
            agent=_agent_for(result.space),
            provider="local",
            model="llama-classifier",
            tier="classifier",
            risk=result.risk,
            confidence=result.confidence,
            reason=result.intent,
            intent=result.intent,
        )

    def route(self, work_item: WorkItem, text: str) -> Route:
        for rule in self.policy.match_rules():
            match = re.search(rule["match"], text.strip())
            if match:
                route = self.ledger.add_route(
                    work_item.id,
                    tier=rule["tier"],
                    provider=rule.get("provider", "none"),
                    model=rule.get("model", ""),
                    risk=rule.get("risk", "read"),
                    confidence=1.0,
                    reason=rule.get("reason", "static rule"),
                )
                self.emitter.router(work_item, route)
                return route
        result = self.classifier(text)
        if result.confidence < 0.7:
            route = self.ledger.add_route(
                work_item.id,
                tier="escalated",
                provider="local",
                model="llama-large",
                risk=result.risk,
                confidence=result.confidence,
                reason="classifier below 0.7",
            )
        else:
            route = self.ledger.add_route(
                work_item.id,
                tier="classifier",
                provider="local",
                model="llama-classifier",
                risk=result.risk,
                confidence=result.confidence,
                reason=result.intent,
            )
        self.emitter.router(work_item, route)
        return route

    def switch_model(self, work_item: WorkItem, provider: str, model: str, reason: str) -> Route:
        allowed = self.policy.allowed_models(work_item.space_id, work_item.label_id)
        if provider not in allowed:
            raise PermissionError(f"{provider} is not allowlisted for this space/label")
        route = self.ledger.add_route(
            work_item.id,
            tier="escalated",
            provider=provider,
            model=model,
            risk="impactful",
            confidence=1.0,
            reason=reason,
        )
        self.emitter.router(work_item, route)
        return route
