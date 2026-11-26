"""Human-in-the-loop controls: roles, approval gates and sign-offs.

Authentication is a demo: the caller states a name and role. In production the role must
come from the bank's identity provider (OIDC claims), not from the client.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.models.requirement import ApprovalStatus, Category, Requirement

ROLES = {
    "business_analyst": "Business analyst",
    "product_owner": "Product owner",
    "project_manager": "Project manager",
    "architect": "Architect",
    "security": "Security officer",
    "compliance": "Compliance officer",
}

# project-level gates -> roles that must all sign off
GATES: dict[str, dict] = {
    "baseline": {
        "title": "Requirements baseline",
        "description": "Freeze the reviewed requirements as the baseline for design.",
        "roles": ["product_owner", "security", "compliance"],
    },
    "regulatory": {
        "title": "Regulatory interpretations",
        "description": "Confirm the proposed regulation mappings. The system never makes a final legal determination.",
        "roles": ["compliance"],
    },
    "conflicts": {
        "title": "Conflict resolutions",
        "description": "Agree how contradictory stakeholder requirements are resolved.",
        "roles": ["product_owner", "compliance"],
    },
    "sdlc": {
        "title": "SDLC selection",
        "description": "Adopt the recommended lifecycle model and workflow.",
        "roles": ["project_manager", "architect", "security", "compliance"],
    },
}

# who may decide a requirement; sensitive ones need a specialist
ORDINARY = {"business_analyst", "product_owner", "project_manager", "architect", "security", "compliance"}
SPECIALIST = {"security", "compliance", "architect"}


class NotAllowed(PermissionError):
    pass


def is_sensitive(requirement: Requirement) -> bool:
    high = requirement.risk_level is not None and requirement.risk_level.value == "high"
    return (
        (high and bool({Category.SECURITY, Category.PRIVACY, Category.REGULATORY} & set(requirement.categories)))
        or any(m.needs_legal_review for m in requirement.regulations)
    )


def check_can_decide(role: str, requirement: Requirement) -> None:
    if role not in ORDINARY:
        raise NotAllowed(f"Unknown role '{role}'.")
    if is_sensitive(requirement) and role not in SPECIALIST:
        raise NotAllowed(
            f"{ROLES[role]} cannot decide this requirement: it is high-risk or needs legal review. "
            "A security officer, compliance officer or architect must decide it."
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def blank_gates() -> dict:
    return {gid: {"signoffs": [], "status": "pending"} for gid in GATES}


def ensure_gates(gates: dict | None) -> dict:
    gates = dict(gates or {})
    for gid in GATES:
        gates.setdefault(gid, {"signoffs": [], "status": "pending"})
    return gates


def evaluate_gate(gate_id: str, state: dict) -> dict:
    required = GATES[gate_id]["roles"]
    latest: dict[str, dict] = {}
    for entry in state["signoffs"]:
        latest[entry["role"]] = entry
    if any(e["decision"] == "rejected" for e in latest.values()):
        status = "rejected"
    elif all(latest.get(role, {}).get("decision") == "approved" for role in required):
        status = "approved"
    else:
        status = "pending"
    return {**state, "status": status}


def sign_off(gates: dict, gate_id: str, role: str, user: str, decision: str, note: str = "") -> dict:
    if gate_id not in GATES:
        raise KeyError(gate_id)
    if role not in GATES[gate_id]["roles"]:
        needed = ", ".join(ROLES[r] for r in GATES[gate_id]["roles"])
        raise NotAllowed(f"{ROLES.get(role, role)} cannot sign '{GATES[gate_id]['title']}'. Required: {needed}.")
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    gates = ensure_gates(gates)
    state = dict(gates[gate_id])
    state["signoffs"] = [*state["signoffs"], {"role": role, "user": user, "decision": decision, "note": note, "at": _now()}]
    gates[gate_id] = evaluate_gate(gate_id, state)
    return gates


def reset_gates(gates: dict, gate_ids: list[str], reason: str) -> dict:
    """Invalidate gates when what they approved has changed."""
    gates = ensure_gates(gates)
    for gid in gate_ids:
        state = gates[gid]
        if state["signoffs"] or state["status"] != "pending":
            gates[gid] = {"signoffs": [], "status": "pending", "reset_reason": reason, "reset_at": _now()}
    return gates


def decision_to_status(decision: str) -> ApprovalStatus:
    return {
        "approved": ApprovalStatus.APPROVED,
        "rejected": ApprovalStatus.REJECTED,
        "needs_revision": ApprovalStatus.NEEDS_REVISION,
        "pending": ApprovalStatus.PENDING,
    }[decision]
