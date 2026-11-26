"""Builds the project-specific SDLC workflow for the selected model.

Each phase lists activities, roles, deliverables, security and testing work, compliance
checkpoints, entry/exit criteria and a human approval gate. The templates are then
customised with this project's open questions, conflicts, control gaps and top risks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models.requirement import WorkflowPhase


@dataclass
class WorkflowContext:
    open_questions: int = 0
    open_conflicts: int = 0
    control_gaps: list[str] = field(default_factory=list)
    top_risks: list[str] = field(default_factory=list)
    jurisdictions: list[str] = field(default_factory=list)
    requirement_count: int = 0


def P(name, goal, activities, roles, deliverables, security, testing, compliance, entry, exit_, gate) -> WorkflowPhase:
    return WorkflowPhase(
        name=name, goal=goal, activities=activities, roles=roles, deliverables=deliverables,
        security_activities=security, testing=testing, compliance_checkpoints=compliance,
        entry_criteria=entry, exit_criteria=exit_, approval_gate=gate,
        traceability="Every deliverable links back to requirement ids and their source statements.",
    )


def _requirements_phase(extra_goal: str = "") -> WorkflowPhase:
    return P(
        "Requirements and compliance baseline",
        "Turn stakeholder input into an approved, traceable requirement baseline." + extra_goal,
        ["Interview remaining stakeholders and resolve open clarification questions",
         "Classify and prioritise requirements; resolve conflicts between stakeholders",
         "Map each requirement to regulations and mandatory controls",
         "Agree customer-risk categories and onboarding journeys (retail, entity, remote)"],
        ["Business analyst", "Product owner", "Compliance officer", "Security architect"],
        ["Approved requirement baseline", "Compliance-control matrix", "Requirements traceability matrix", "Risk register v1"],
        ["Data classification of KYC data", "Privacy impact assessment scoping", "Initial threat model"],
        ["Requirement review against acceptance-criteria quality checklist"],
        ["Compliance officer confirms regulatory mappings", "Legal review of high-impact interpretations"],
        ["Stakeholder inputs collected and PII-masked"],
        ["No unresolved conflicts or blocking questions", "Baseline approved"],
        "Requirements baseline approval (project manager, architect, security, compliance)",
    )


WATERFALL = lambda: [
    _requirements_phase(),
    P("System design", "Design the KYC onboarding architecture against the baseline.",
      ["Design identity verification, screening and risk-rating components", "Define data model, retention and audit logging", "Design integrations (registries, screening vendors, core banking)"],
      ["Architect", "Security architect", "Data protection officer"],
      ["Architecture and interface specification", "Data-flow and retention design", "Security design"],
      ["Threat modelling (STRIDE) of every data flow", "Encryption and key-management design"],
      ["Design review against each requirement"], ["Privacy-by-design review"],
      ["Baseline approved"], ["Design signed off, traceable to requirements"], "Design approval (architect, security, compliance)"),
    P("Implementation", "Build the system to the approved design.",
      ["Implement services and integrations", "Implement configurable rules for risk rating and re-KYC"],
      ["Developers", "Tech lead"], ["Working software", "Build documentation"],
      ["Secure coding standards", "Static analysis and dependency scanning"], ["Unit tests per requirement"], ["Code review evidence retained"],
      ["Design approved"], ["All requirements implemented, unit tests pass"], "Code-complete review"),
    P("Verification", "Prove the system meets the requirements.",
      ["System and integration testing", "Security and penetration testing", "Accuracy testing of identity verification and screening", "Performance and availability testing"],
      ["QA lead", "Security testers"], ["Test reports", "Traceability matrix with test results"],
      ["Penetration test", "Presentation-attack testing for liveness"], ["System, integration, security and performance tests"],
      ["Compliance test evidence per control"], ["Code complete"], ["All critical defects closed; coverage of every requirement"], "Test-exit approval"),
    P("Deployment and acceptance", "Release to production under compliance sign-off.",
      ["User acceptance by operations and compliance", "Production deployment and cut-over", "Staff training"],
      ["Product owner", "Operations", "Compliance officer"], ["Release package", "Go-live approval record"],
      ["Production hardening", "Access review"], ["User acceptance test"], ["Compliance officer sign-off before first real customer is onboarded"],
      ["Verification complete"], ["Acceptance signed"], "Production-readiness approval"),
    P("Operations and maintenance", "Run, monitor and keep the system compliant.",
      ["Monitor alerts and turnaround", "Process regulatory change", "Periodic KYC refresh operations"],
      ["Operations", "Compliance officer"], ["Operations runbook", "Regulatory change log"],
      ["Vulnerability management", "Access recertification"], ["Regression testing for changes"], ["Change approval gate for any requirement change"],
      ["Live"], ["Stable operation"], "Change approval for each baseline change"),
]

V_MODEL = lambda: [
    _requirements_phase(" Define acceptance tests alongside each requirement."),
    P("System design and system test planning", "Design the whole system and plan its verification together.",
      ["Architecture design", "Write system-test plans traceable to requirements", "Design audit trail and evidence capture"],
      ["Architect", "Test lead", "Security architect"], ["System design", "System test plan", "Threat model"],
      ["STRIDE threat model", "Security requirements verification plan"], ["System test specification"], ["Control-to-test mapping reviewed by compliance"],
      ["Baseline approved"], ["Design and test plan approved"], "Design and verification-plan approval"),
    P("Component design and integration test planning", "Design components and the tests that will prove their interfaces.",
      ["Detailed design of identity, screening, risk-rating and case-management components", "Integration test plan for vendors and registries"],
      ["Tech lead", "Developers"], ["Component designs", "Integration test plan"], ["Secure interface design"], ["Integration test specification"], ["Vendor due diligence"],
      ["System design approved"], ["Component designs reviewed"], "Component design review"),
    P("Implementation", "Build components.", ["Implement and unit test components"], ["Developers"], ["Code", "Unit tests"],
      ["Static analysis", "Secrets scanning"], ["Unit tests"], ["Code review evidence"], ["Component designs approved"], ["Unit tests pass"], "Code-complete review"),
    P("Unit and integration verification", "Verify each level against its design.",
      ["Run unit and integration tests", "Test accuracy of document and face verification"], ["QA", "Developers"], ["Unit and integration results"],
      ["Dependency and container scanning"], ["Unit, integration, interface and negative tests"], ["Evidence archived per control"],
      ["Code complete"], ["Integration tests pass"], "Integration test exit"),
    P("System verification and validation", "Verify against the system tests and validate against stakeholder needs.",
      ["System test execution", "Penetration and presentation-attack testing", "Performance, availability and failover tests", "Stakeholder validation"],
      ["QA lead", "Security testers", "Compliance officer"], ["System test report", "Penetration test report", "Validation report"],
      ["Penetration test", "Liveness spoofing tests"], ["System and non-functional tests"], ["Control effectiveness test results reviewed by compliance"],
      ["Integration verified"], ["All requirements verified and validated"], "Verification and validation sign-off"),
    P("Release and operations", "Deploy under final compliance approval and operate.",
      ["Production readiness review", "Deploy", "Operate and monitor"], ["Product owner", "Operations", "Compliance officer"],
      ["Release record", "Operations runbook"], ["Production hardening"], ["Smoke tests"], ["Final compliance approval before go-live"],
      ["Validated"], ["Live and monitored"], "Production-readiness approval"),
]


def _spiral_loop(n: int, focus: str, goal_extra: str) -> list[WorkflowPhase]:
    tag = f"Spiral {n}"
    return [
        P(f"{tag}: objectives and constraints", f"Fix the objectives for this loop: {focus}.",
          ["Confirm what this loop must settle", "List alternatives and constraints (cost, regulation, vendors)"],
          ["Product owner", "Business analyst", "Compliance officer"], ["Loop objectives", "Open-issue list"],
          ["Review data-handling constraints"], [], ["Compliance confirms which rules constrain this loop"],
          ["Previous loop reviewed" if n > 1 else "Initial stakeholder inputs collected"], ["Objectives agreed"], f"{tag} start approval"),
        P(f"{tag}: risk analysis and prototype", "Reduce the biggest risks with the cheapest experiment." + goal_extra,
          ["Rank risks and uncertainties from the risk register", "Build the smallest prototype or spike that answers them", "Test with real stakeholders or synthetic KYC data"],
          ["Architect", "Developers", "Risk lead"], ["Risk assessment update", "Prototype and findings"],
          ["Threat-model the prototype", "Use synthetic or masked customer data only"], ["Prototype evaluation against success criteria"],
          ["Compliance reviews prototype findings"], ["Objectives agreed"], ["Top risks reduced or consciously accepted"], f"{tag} risk review"),
        P(f"{tag}: engineering", "Build and verify the increment that the prototype justified.",
          ["Develop the validated increment", "Update requirements and traceability from what was learned"],
          ["Developers", "QA"], ["Tested increment", "Updated baseline candidate"], ["Secure coding and scanning"],
          ["Unit, integration and regression tests"], ["Control evidence for new functionality"], ["Risk review passed"], ["Increment verified"], f"{tag} increment acceptance"),
        P(f"{tag}: evaluation and planning", "Decide whether to continue, change direction or stop.",
          ["Stakeholder review of the increment", "Re-score SDLC factors and open questions", "Plan the next loop"],
          ["Project manager", "Product owner", "Compliance officer"], ["Evaluation report", "Next-loop plan"],
          ["Security review of findings"], [], ["Compliance sign-off on what moves into the baseline"],
          ["Increment accepted"], ["Decision recorded: continue, pivot or release"], f"{tag} go / no-go (all four approvers)"),
    ]


def SPIRAL() -> list[WorkflowPhase]:
    return (
        _spiral_loop(1, "settle the biggest uncertainties (customer risk trigger, verification method, regulatory interpretation)", "")
        + _spiral_loop(2, "build and validate the core onboarding flow", "")
        + _spiral_loop(3, "harden, scale and prepare for release", " Include penetration and performance tests.")
        + [P("Release", "Release the validated system under final approval.",
             ["Production readiness review", "Deployment", "Operational handover"], ["Operations", "Compliance officer", "Project manager"],
             ["Release record", "Runbook"], ["Production hardening", "Access review"], ["Acceptance and smoke tests"],
             ["Final compliance sign-off before first real customer"], ["Spiral 3 go decision"], ["Live"], "Production-readiness approval")]
    )


def AGILE() -> list[WorkflowPhase]:
    return [
        P("Discovery and backlog", "Create a prioritised backlog from stakeholder input.",
          ["Story mapping of onboarding journeys", "Groom backlog with acceptance criteria", "Definition of Done including compliance evidence"],
          ["Product owner", "Business analyst", "Compliance officer"], ["Backlog", "Definition of Done", "Compliance checklist"],
          ["Security and privacy stories in the backlog"], ["Acceptance criteria review"], ["Compliance officer reviews mandatory-control stories"],
          ["Inputs collected"], ["Backlog ready for sprint 1"], "Backlog approval"),
        P("Sprint cycle (repeat)", "Deliver small verified increments.",
          ["Sprint planning", "Build and test", "Sprint review with stakeholders", "Retrospective"],
          ["Scrum team", "Product owner"], ["Working increment each sprint", "Updated traceability"],
          ["Per-sprint threat review", "Dependency scanning"], ["Automated tests per story", "Regression suite"], ["Compliance evidence collected per story"],
          ["Sprint backlog agreed"], ["Definition of Done met"], "Sprint review acceptance"),
        P("Hardening and release", "Stabilise and release.",
          ["Hardening sprint", "Performance and security testing", "Release readiness"], ["QA", "Security", "Compliance officer"],
          ["Release candidate", "Test and compliance evidence"], ["Penetration test"], ["Non-functional tests"],
          ["Compliance sign-off for release"], ["Scope complete"], ["Release approved"], "Release approval"),
        P("Operate and improve", "Run, monitor and keep improving.", ["Monitor and support", "Process regulatory changes as backlog items"],
          ["Operations", "Product owner"], ["Runbook", "Change log"], ["Vulnerability management"], ["Regression"], ["Change approval for regulatory-relevant changes"],
          ["Live"], ["Stable"], "Change approval"),
    ]


def DEVSECOPS() -> list[WorkflowPhase]:
    stages = [
        ("Plan and threat-model", "Plan work and model threats continuously.", ["Backlog refinement", "Threat modelling per feature"], ["Product owner", "Security"], ["Prioritised backlog", "Threat model"], ["Threat modelling"], [], ["Compliance requirements tagged on stories"]),
        ("Code and commit", "Write code with security checks at commit.", ["Peer review", "Pre-commit secrets and lint checks"], ["Developers"], ["Reviewed code"], ["Secrets scanning", "SAST"], ["Unit tests"], ["Code-review evidence"]),
        ("Build and test", "Automate build and verification.", ["CI pipeline", "Dependency and container scanning"], ["DevOps", "QA"], ["Signed build artefacts", "Test results"], ["SCA, container scanning"], ["Automated functional and API tests"], ["Pipeline evidence archived"]),
        ("Release gates", "Stop unsafe releases automatically.", ["Policy-as-code gates", "DAST", "Compliance evidence check"], ["Security", "Compliance officer"], ["Gate decision record"], ["DAST", "Policy checks"], ["Security and performance tests"], ["Mandatory-control evidence present before release"]),
        ("Deploy and operate", "Deploy safely and observe.", ["Progressive rollout", "Monitoring and alerting"], ["DevOps", "Operations"], ["Release record", "Dashboards"], ["Runtime protection", "Access control review"], ["Smoke tests"], ["Change record linked to requirements"]),
        ("Monitor and respond", "Detect issues and learn.", ["Incident response", "Feedback into backlog"], ["Operations", "Security"], ["Incident reports", "Backlog updates"], ["Incident response", "Vulnerability management"], [], ["Regulator notification process ready"]),
    ]
    return [
        P(name, goal, acts, roles, deliv, sec, test, comp, ["Previous stage passed"], ["Stage gate green"], f"{name} gate")
        for name, goal, acts, roles, deliv, sec, test, comp in stages
    ]


def AGILE_V() -> list[WorkflowPhase]:
    return [
        _requirements_phase(" Establish a regulated baseline that increments extend."),
        P("Architecture runway", "Design the regulated core once, then evolve it.", ["Architecture and data-protection design", "Verification strategy per level"],
          ["Architect", "Security architect"], ["Architecture", "Verification strategy"], ["Threat model"], ["Test strategy"], ["Privacy-by-design review"],
          ["Baseline approved"], ["Architecture approved"], "Architecture approval"),
        P("Increment cycle (repeat)", "Deliver increments, verifying each against its requirements (a V per increment).",
          ["Plan increment from backlog", "Design, build and unit test", "Integration and system verification of the increment", "Stakeholder review"],
          ["Scrum team", "QA", "Compliance officer"], ["Verified increment", "Updated traceability and compliance matrix"],
          ["Security testing every increment"], ["Unit, integration and system tests per increment"], ["Compliance sign-off on each increment's controls"],
          ["Increment planned"], ["Increment verified and accepted"], "Increment acceptance"),
        P("Validation and release", "Validate the whole and release.", ["Full system validation", "Penetration and presentation-attack tests", "Release"],
          ["QA lead", "Security", "Compliance officer"], ["Validation report", "Release record"], ["Penetration test"], ["End-to-end validation"],
          ["Final compliance approval"], ["All planned increments verified"], ["Validated"], "Release approval"),
        P("Operate and change", "Operate and process change under control.", ["Monitor", "Handle regulatory change as new increments"],
          ["Operations", "Product owner"], ["Runbook", "Change log"], ["Vulnerability management"], ["Regression"], ["Change approval for baselined requirements"],
          ["Live"], ["Stable"], "Change approval"),
    ]


def AGILE_DEVSECOPS() -> list[WorkflowPhase]:
    return [
        _requirements_phase(" Keep the baseline thin and extend it continuously."),
        *DEVSECOPS()[:5],
        P("Operate, monitor and adapt", "Operate and fold regulatory change into the backlog.",
          ["Monitoring and incident response", "Regulatory change intake", "Sprint review with compliance"], ["Operations", "Security", "Compliance officer"],
          ["Incident reports", "Updated baseline"], ["Incident response", "Vulnerability management"], ["Regression"],
          ["Change approval for baselined requirements"], ["Live"], ["Stable"], "Change approval"),
    ]


TEMPLATES = {
    "Waterfall": WATERFALL,
    "V-Model": V_MODEL,
    "Spiral": SPIRAL,
    "Agile (Scrum/Kanban)": AGILE,
    "DevSecOps": DEVSECOPS,
    "Agile-V hybrid": AGILE_V,
    "Agile-DevSecOps hybrid": AGILE_DEVSECOPS,
}


def build_workflow(model: str, ctx: WorkflowContext) -> list[WorkflowPhase]:
    """Template for ``model`` customised with this project's situation."""
    phases = TEMPLATES.get(model, AGILE_V)()
    first = phases[0]
    if ctx.open_questions:
        first.activities.insert(0, f"Resolve or consciously accept {ctx.open_questions} open clarification question(s)")
    if ctx.open_conflicts:
        first.activities.insert(0, f"Resolve {ctx.open_conflicts} open conflict(s) between stakeholder requirements")
    for gap in ctx.control_gaps[:6]:
        first.compliance_checkpoints.append(f"Close control gap: {gap}")
    if ctx.top_risks:
        first.deliverables.append("Mitigation plan for: " + "; ".join(r[:70] for r in ctx.top_risks[:3]))
    if ctx.jurisdictions:
        first.compliance_checkpoints.append("Confirm applicable jurisdictions: " + ", ".join(ctx.jurisdictions))
    phases[-1].compliance_checkpoints.append("No real customer data in non-production environments")
    return phases
