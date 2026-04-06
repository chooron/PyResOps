"""Rolling flood-ops workflow service."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any

from ..domain.constraint import Constraint, ConstraintSet
from ..domain.forecast import ForecastBundle
from ..domain.program import DispatchProgram
from ..domain.result import EvaluationResult, SimulationResult
from ..storage.repository import Repository
from .evaluation import EvaluationService
from .optimization import OptimizationService
from .program import ProgramService
from .simulation import SimulationService
from .snapshot import SnapshotService


@dataclass
class CandidatePlanRecord:
    """Candidate plan with its computed evidence."""

    program: DispatchProgram
    simulation: SimulationResult
    evaluation: EvaluationResult
    created_at: datetime
    conditions_hash: str


@dataclass
class FinalizedPlanRecord:
    """Finalized-plan history entry."""

    finalized_id: str
    program_id: str
    source_program_id: str
    version: int
    supersedes_id: str | None
    created_at: datetime


@dataclass
class WorkingContext:
    """In-memory working context keyed by reservoir + context."""

    working_plan_id: str | None = None
    latest_conditions_hash: str | None = None
    last_simulation_program_id: str | None = None
    last_evaluation_program_id: str | None = None
    candidate_plans: dict[str, CandidatePlanRecord] = field(default_factory=dict)
    finalized_records: list[FinalizedPlanRecord] = field(default_factory=list)


class RollingOpsService:
    """Workflow orchestration for rolling flood operations."""

    def __init__(
        self,
        *,
        program_service: ProgramService,
        simulation_service: SimulationService,
        evaluation_service: EvaluationService,
        optimization_service: OptimizationService,
        snapshot_service: SnapshotService,
        repository: Repository,
    ):
        self.program_service = program_service
        self.simulation_service = simulation_service
        self.evaluation_service = evaluation_service
        self.optimization_service = optimization_service
        self.snapshot_service = snapshot_service
        self.repository = repository
        self._working_store: dict[tuple[str, str], WorkingContext] = {}

    def optimize_flexible_release_plan(
        self,
        *,
        reservoir_id: str,
        context_id: str,
        horizon_hours: int,
        control_interval_seconds: int,
        forecast: ForecastBundle,
        constraints: dict[str, Any] | None = None,
        objectives: dict[str, Any] | None = None,
        directives: dict[str, Any] | None = None,
        optimizer_backend: str | None = None,
    ) -> dict[str, Any]:
        """Generate candidate plan and evidence; auto-adopt if no working plan exists."""
        initial_state = self.snapshot_service.get_snapshot(reservoir_id)
        if not initial_state:
            raise ValueError(f"Snapshot not found for reservoir: {reservoir_id}")

        constraints = constraints or {}
        objectives = objectives or {}
        directives = directives or {}

        program, schedule = self.optimization_service.optimize_flexible_release_plan(
            initial_state=initial_state,
            forecast=forecast,
            horizon_hours=horizon_hours,
            control_interval_seconds=control_interval_seconds,
            constraints=constraints,
            objectives=objectives,
            directives=directives,
            optimizer_backend=optimizer_backend,
            metadata={
                "reservoir_id": reservoir_id,
                "context_id": context_id,
            },
        )

        simulation = self.simulation_service.run_simulation(program, initial_state, forecast)
        evaluation = self.evaluation_service.evaluate(
            simulation,
            constraint_set=self._build_constraint_set(constraints),
            proxy_options={
                "env_min_flow": float(constraints.get("min_environmental_flow", 0.0)),
                "max_ramp_rate": constraints.get("max_ramp_rate"),
                "tailwater_level": directives.get("tailwater_level", initial_state.level - 10.0),
            },
        )

        conditions_hash = self._compute_conditions_hash(
            forecast, constraints, objectives, directives
        )

        context = self._get_or_create_context(reservoir_id, context_id)
        context.candidate_plans[program.id] = CandidatePlanRecord(
            program=program,
            simulation=simulation,
            evaluation=evaluation,
            created_at=datetime.now(),
            conditions_hash=conditions_hash,
        )

        auto_adopted = False
        if context.working_plan_id is None:
            auto_adopted = True
            context.working_plan_id = program.id
            context.latest_conditions_hash = conditions_hash
            context.last_simulation_program_id = program.id
            context.last_evaluation_program_id = program.id

        return {
            "candidate_plan_id": program.id,
            "summary": {
                "segment_count": schedule.segment_count,
                "control_interval_seconds": schedule.control_interval_seconds,
                "release_values": schedule.release_values,
                "overall_score": evaluation.overall_score,
                "violations_count": len(evaluation.constraint_violations),
                "auto_adopted_as_working": auto_adopted,
            },
        }

    def reassess_plan(
        self,
        *,
        reservoir_id: str,
        context_id: str,
        forecast: ForecastBundle,
        constraints: dict[str, Any] | None = None,
        directives: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reassess current working plan under updated conditions; read-only."""
        context = self._get_context(reservoir_id, context_id)
        if not context or not context.working_plan_id:
            raise ValueError("Working plan not found for context")

        initial_state = self.snapshot_service.get_snapshot(reservoir_id)
        if not initial_state:
            raise ValueError(f"Snapshot not found for reservoir: {reservoir_id}")

        working_plan_id = context.working_plan_id
        candidate = context.candidate_plans.get(working_plan_id)
        working_program = (
            candidate.program if candidate else self.program_service.get_program(working_plan_id)
        )
        if not working_program:
            raise ValueError(f"Working program not found: {working_plan_id}")

        constraints = constraints or {}
        directives = directives or {}

        reassessed_sim = self.simulation_service.run_simulation(
            working_program, initial_state, forecast
        )
        reassessed_eval = self.evaluation_service.evaluate(
            reassessed_sim,
            constraint_set=self._build_constraint_set(constraints),
            proxy_options={
                "env_min_flow": float(constraints.get("min_environmental_flow", 0.0)),
                "max_ramp_rate": constraints.get("max_ramp_rate"),
                "tailwater_level": directives.get("tailwater_level", initial_state.level - 10.0),
            },
        )

        baseline_score = candidate.evaluation.overall_score if candidate else None
        recommendation = "keep"
        rationale: list[str] = []
        if reassessed_eval.constraint_violations:
            recommendation = "replace"
            rationale.append("Detected constraint violations under updated conditions")
        elif baseline_score is not None and reassessed_eval.overall_score < baseline_score - 5.0:
            recommendation = "replace"
            rationale.append("Overall score dropped materially versus baseline")
        else:
            rationale.append("Current working plan remains acceptable")

        return {
            "working_plan_id": working_plan_id,
            "recommendation": recommendation,
            "evidence": {
                "baseline_overall_score": baseline_score,
                "reassessed_overall_score": reassessed_eval.overall_score,
                "violations_count": len(reassessed_eval.constraint_violations),
                "max_level": reassessed_sim.max_level,
                "min_level": reassessed_sim.min_level,
                "avg_outflow": reassessed_sim.avg_outflow,
                "rationale": rationale,
            },
        }

    def replace_working_plan(
        self,
        *,
        reservoir_id: str,
        context_id: str,
        candidate_plan_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Explicitly replace working plan with a generated candidate plan."""
        context = self._get_or_create_context(reservoir_id, context_id)
        if candidate_plan_id not in context.candidate_plans:
            raise ValueError(f"Candidate plan not found: {candidate_plan_id}")

        previous_plan_id = context.working_plan_id
        selected = context.candidate_plans[candidate_plan_id]

        context.working_plan_id = candidate_plan_id
        context.latest_conditions_hash = selected.conditions_hash
        context.last_simulation_program_id = candidate_plan_id
        context.last_evaluation_program_id = candidate_plan_id

        return {
            "previous_working_plan_id": previous_plan_id,
            "working_plan_id": candidate_plan_id,
            "reason": reason,
            "updated_at": datetime.now().isoformat(),
        }

    def finalize_plan(self, *, reservoir_id: str, context_id: str) -> dict[str, Any]:
        """Finalize current working plan and persist append-only history."""
        context = self._get_context(reservoir_id, context_id)
        if not context or not context.working_plan_id:
            raise ValueError("Working plan not found for context")

        source_program_id = context.working_plan_id
        candidate = context.candidate_plans.get(source_program_id)
        if not candidate:
            raise ValueError("Working plan evidence is missing; regenerate candidate first")

        version = len(context.finalized_records) + 1
        supersedes_id = (
            context.finalized_records[-1].finalized_id if context.finalized_records else None
        )

        now = datetime.now()
        safe_res = self._safe_id_component(reservoir_id)
        safe_ctx = self._safe_id_component(context_id)
        finalized_id = f"fin_{safe_res}_{safe_ctx}_v{version}_{now.strftime('%Y%m%d%H%M%S')}"
        finalized_program_id = f"{source_program_id}__final_v{version}"

        program_data = candidate.program.model_dump(mode="json")
        program_data["id"] = finalized_program_id
        program_data.setdefault("metadata", {})
        program_data["metadata"]["finalization"] = {
            "finalized_id": finalized_id,
            "version": version,
            "supersedes_id": supersedes_id,
            "reservoir_id": reservoir_id,
            "context_id": context_id,
            "source_program_id": source_program_id,
            "finalized_at": now.isoformat(),
        }
        self.repository.save_program(finalized_program_id, program_data)

        sim_data = candidate.simulation.model_dump(mode="json")
        sim_data["program_id"] = finalized_program_id
        sim_data["snapshot_count"] = len(candidate.simulation.snapshots)
        self.repository.save_simulation_result(finalized_program_id, sim_data)

        eval_data = candidate.evaluation.model_dump(mode="json")
        eval_data["program_id"] = finalized_program_id
        eval_data["violations_count"] = len(candidate.evaluation.constraint_violations)
        self.repository.save_evaluation_result(finalized_program_id, eval_data)

        snapshot = self.snapshot_service.get_snapshot(reservoir_id)
        if snapshot:
            self.repository.save_snapshot(reservoir_id, snapshot.model_dump(mode="json"))

        self.repository.save_finalized_record(
            finalized_id=finalized_id,
            reservoir_id=reservoir_id,
            context_id=context_id,
            program_id=finalized_program_id,
            source_program_id=source_program_id,
            supersedes_id=supersedes_id,
            version=version,
            record_data={
                "overall_score": candidate.evaluation.overall_score,
                "violations_count": len(candidate.evaluation.constraint_violations),
                "max_level": candidate.simulation.max_level,
            },
        )

        context.finalized_records.append(
            FinalizedPlanRecord(
                finalized_id=finalized_id,
                program_id=finalized_program_id,
                source_program_id=source_program_id,
                version=version,
                supersedes_id=supersedes_id,
                created_at=now,
            )
        )

        return {
            "persisted_ids": {
                "finalized_id": finalized_id,
                "program_id": finalized_program_id,
                "simulation_result_id": finalized_program_id,
                "evaluation_result_id": finalized_program_id,
            },
            "version": version,
            "supersedes_id": supersedes_id,
        }

    def get_working_state(self, *, reservoir_id: str, context_id: str) -> dict[str, Any]:
        """Return current working-plan state and latest evidence."""
        context = self._get_context(reservoir_id, context_id)
        if not context:
            return {
                "reservoir_id": reservoir_id,
                "context_id": context_id,
                "working_plan_id": None,
                "candidate_plan_ids": [],
                "latest_conditions_hash": None,
                "last_simulation": None,
                "last_evaluation": None,
                "finalized_history": [],
            }

        current = (
            context.candidate_plans.get(context.working_plan_id)
            if context.working_plan_id
            else None
        )
        last_sim = None
        last_eval = None
        if current:
            last_sim = {
                "program_id": current.program.id,
                "max_level": current.simulation.max_level,
                "min_level": current.simulation.min_level,
                "avg_outflow": current.simulation.avg_outflow,
            }
            last_eval = {
                "program_id": current.program.id,
                "overall_score": current.evaluation.overall_score,
                "flood_control_score": current.evaluation.flood_control_score,
                "water_supply_score": current.evaluation.water_supply_score,
                "power_generation_score": current.evaluation.power_generation_score,
                "ecological_score": current.evaluation.ecological_score,
                "violations_count": len(current.evaluation.constraint_violations),
            }

        return {
            "reservoir_id": reservoir_id,
            "context_id": context_id,
            "working_plan_id": context.working_plan_id,
            "candidate_plan_ids": list(context.candidate_plans.keys()),
            "latest_conditions_hash": context.latest_conditions_hash,
            "last_simulation": last_sim,
            "last_evaluation": last_eval,
            "finalized_history": [
                {
                    "finalized_id": item.finalized_id,
                    "program_id": item.program_id,
                    "source_program_id": item.source_program_id,
                    "version": item.version,
                    "supersedes_id": item.supersedes_id,
                    "created_at": item.created_at.isoformat(),
                }
                for item in context.finalized_records
            ],
        }

    def _build_constraint_set(self, constraints: dict[str, Any]) -> ConstraintSet | None:
        items: list[Constraint] = []
        if constraints.get("max_level") is not None:
            items.append(
                Constraint(
                    id="max_level",
                    name="Max level",
                    constraint_type="level_max",
                    parameters={"max_level": float(constraints["max_level"])},
                )
            )

        if constraints.get("min_environmental_flow") is not None:
            items.append(
                Constraint(
                    id="env_min_flow",
                    name="Environmental minimum flow",
                    constraint_type="flow_min",
                    parameters={"min_flow": float(constraints["min_environmental_flow"])},
                )
            )

        if constraints.get("min_water_supply_flow") is not None:
            items.append(
                Constraint(
                    id="supply_min_flow",
                    name="Water supply minimum flow",
                    constraint_type="flow_min",
                    parameters={"min_flow": float(constraints["min_water_supply_flow"])},
                )
            )

        return ConstraintSet(constraints=items) if items else None

    def _compute_conditions_hash(
        self,
        forecast: ForecastBundle,
        constraints: dict[str, Any],
        objectives: dict[str, Any],
        directives: dict[str, Any],
    ) -> str:
        payload = {
            "forecast": forecast.model_dump(mode="json"),
            "constraints": constraints,
            "objectives": objectives,
            "directives": directives,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
        return sha256(blob.encode("utf-8")).hexdigest()

    def _get_or_create_context(self, reservoir_id: str, context_id: str) -> WorkingContext:
        key = (reservoir_id, context_id)
        if key not in self._working_store:
            self._working_store[key] = WorkingContext()
        return self._working_store[key]

    def _get_context(self, reservoir_id: str, context_id: str) -> WorkingContext | None:
        return self._working_store.get((reservoir_id, context_id))

    def _safe_id_component(self, value: str) -> str:
        return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)
