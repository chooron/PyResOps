"""Policy-driven decision orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..constraints import (
    ConstraintFactory,
    ConstraintRegistry,
    register_builtin_constraints,
)
from ..domain.constraint import Constraint
from ..domain.decision import DecisionOutcome, DecisionTraceStep, ViolationRecord
from ..domain.policy import ExecutionContext, PolicyBundle
from ..domain.rule import DispatchRule, RuleAction
from ..rules import RuleFactory, RuleRegistry, register_builtin_rules
from ..rules.actions import normalize_action
from .action_resolver import ActionResolver


@dataclass(slots=True)
class OrchestratorState:
    """State maintained across step decisions."""

    previous_outflow: float | None = None
    trace: list[DecisionTraceStep] = field(default_factory=list)


class DecisionOrchestrator:
    """Orchestrate rules and constraints into executable decisions."""

    def __init__(
        self,
        *,
        constraint_registry: ConstraintRegistry | None = None,
        rule_registry: RuleRegistry | None = None,
    ):
        self.constraint_registry = constraint_registry or ConstraintRegistry()
        self.rule_registry = rule_registry or RuleRegistry()
        register_builtin_constraints(self.constraint_registry)
        register_builtin_rules(self.rule_registry)

        self.constraint_factory = ConstraintFactory(self.constraint_registry)
        self.rule_factory = RuleFactory(self.rule_registry)
        self.action_resolver = ActionResolver()
        self.state = OrchestratorState()

    def reset(self) -> None:
        """Clear previous state and trace."""
        self.state = OrchestratorState()

    def decide(
        self,
        *,
        timestamp: datetime,
        step_index: int,
        state_payload: dict[str, Any],
        inflow: float,
        baseline_outflow: float,
        active_module: str | None,
        policy_bundle: PolicyBundle,
        forecast_payload: dict[str, Any] | None = None,
        history_payload: dict[str, Any] | None = None,
    ) -> DecisionOutcome:
        """Resolve one-step outflow decision."""
        context = ExecutionContext(
            step_index=step_index,
            state=state_payload,
            inflow=float(inflow),
            proposed_outflow=float(baseline_outflow),
            forecast=forecast_payload or {},
            history=history_payload or {},
            directives=policy_bundle.directives,
        )

        matched_rules, actions = self._evaluate_rules(context, policy_bundle.rules.enabled_rules())
        resolved_outflow, adjustments = self.action_resolver.resolve_outflow(
            baseline_outflow=baseline_outflow,
            actions=actions,
        )

        resolved_outflow, constraint_adjustments, violations = self._apply_constraints(
            step_index=step_index,
            level=float(state_payload.get("level", 0.0)),
            inflow=float(inflow),
            outflow=float(resolved_outflow),
            constraints=policy_bundle.constraints.get_by_scope("step"),
        )
        adjustments.extend(constraint_adjustments)

        fallback_used = any(v.enforcement == "hard" for v in violations)
        if fallback_used:
            adjustments.append(
                {
                    "source": "orchestrator",
                    "type": "hard_constraint_fallback",
                    "reason": "hard constraint violated",
                }
            )

        trace_step = DecisionTraceStep(
            step_index=step_index,
            timestamp=timestamp,
            active_module=active_module,
            rule_hits=[rule.id for rule in matched_rules],
            actions=actions,
            proposed_outflow=float(baseline_outflow),
            resolved_outflow=float(resolved_outflow),
            adjustments=adjustments,
            violations=violations,
        )
        self.state.trace.append(trace_step)
        self.state.previous_outflow = float(resolved_outflow)

        return DecisionOutcome(
            outflow=float(resolved_outflow),
            rule_hits=trace_step.rule_hits,
            actions=actions,
            adjustments=adjustments,
            violations=violations,
            fallback_used=fallback_used,
        )

    def global_violations(
        self,
        *,
        simulation_result,
        policy_bundle: PolicyBundle,
    ) -> list[ViolationRecord]:
        """Evaluate global constraints against finalized simulation result."""
        violations: list[ViolationRecord] = []
        for constraint in policy_bundle.constraints.get_by_scope("global"):
            evaluator = self.constraint_factory.create(constraint)
            if evaluator is None:
                continue
            violations.extend(evaluator.validate_global(result=simulation_result))
        return violations

    def _evaluate_rules(
        self,
        context: ExecutionContext,
        rules: list[DispatchRule],
    ) -> tuple[list[DispatchRule], list[RuleAction]]:
        matched: list[DispatchRule] = []
        actions: list[RuleAction] = []

        for rule in rules:
            evaluator = self.rule_factory.create(rule)
            if evaluator is None:
                continue
            if not evaluator.match(context):
                continue

            matched.append(rule)
            actions.extend(
                normalize_action(action) for action in evaluator.produce_actions(context)
            )
            if rule.stop_on_match:
                break

        return matched, actions

    def _apply_constraints(
        self,
        *,
        step_index: int,
        level: float,
        inflow: float,
        outflow: float,
        constraints: list[Constraint],
    ) -> tuple[float, list[dict[str, Any]], list[ViolationRecord]]:
        current_outflow = float(outflow)
        adjustments: list[dict[str, Any]] = []
        violations: list[ViolationRecord] = []

        ordered_constraints = sorted(constraints, key=lambda item: (-item.priority, item.id))

        for constraint in ordered_constraints:
            evaluator = self.constraint_factory.create(constraint)
            if evaluator is None:
                continue

            context = {"previous_outflow": self.state.previous_outflow}
            step_violations = evaluator.validate_step(
                step_index=step_index,
                level=level,
                inflow=inflow,
                outflow=current_outflow,
                context=context,
            )
            if not step_violations:
                continue

            violations.extend(step_violations)
            suggestion = evaluator.suggest_adjustment(
                step_index=step_index,
                level=level,
                inflow=inflow,
                outflow=current_outflow,
                context=context,
            )
            if not suggestion:
                continue

            before = current_outflow
            if suggestion.get("action") == "clamp_outflow":
                min_outflow = suggestion.get("min_outflow")
                max_outflow = suggestion.get("max_outflow")
                if min_outflow is not None:
                    current_outflow = max(current_outflow, float(min_outflow))
                if max_outflow is not None:
                    current_outflow = min(current_outflow, float(max_outflow))
            elif suggestion.get("action") == "increase_outflow":
                target = suggestion.get("target_outflow")
                if target is not None:
                    current_outflow = max(current_outflow, float(target))
            elif suggestion.get("action") == "decrease_outflow":
                target = suggestion.get("target_outflow")
                if target is not None:
                    current_outflow = min(current_outflow, float(target))

            if before != current_outflow:
                adjustments.append(
                    {
                        "source": "constraint",
                        "constraint_id": constraint.id,
                        "before": before,
                        "after": current_outflow,
                        "suggestion": suggestion,
                    }
                )

        return current_outflow, adjustments, violations
