# OrthoAI Pilot v3

## Research rationale, publication readiness, and data requirements

**Assessment date:** 20 July 2026
**Source reviewed:** *Decision Quality, Speed, and Trust Over Time: A Longitudinal Field Study of Diagnostic AI Across Five Dental Clinics* (preliminary report, July 2026)
**System reviewed:** the current OrthoAI live-pilot repository, including its Next.js clinical-validation workflow, FastAPI APIs, inference records, audit log, and the proposed model integration.

> **Decision:** The current live pilot is a useful product demonstration and an early feasibility platform. It is **not sufficient as the sole data source for the longitudinal paper as currently framed**, and it is not yet defensible for CHI, IUI, CSCW, or npj Digital Medicine as a completed longitudinal field study. Pilot v3 should be treated as a research-instrument release, not simply a model upgrade.

This document replaces the early three-page overview as the working research specification. It does not replace an ethics application, statistical analysis plan, or clinical safety review.

---

## 1. Why Pilot v3 is necessary

The proposed paper makes claims about change over time: whether clinicians become faster, whether their decisions improve, whether trust becomes better calibrated, and whether familiarity creates over-reliance. Those claims cannot be recovered from ordinary application logs after deployment. They require a prospective workflow that records what a clinician believed **before seeing AI**, exactly when AI became visible, what changed afterward, whether the AI and final decision were correct against an independent reference, and how all of these measures evolve with exposure.

Pilot v3 is therefore driven by five research needs:

1. **Separate unaided judgment from AI-assisted judgment.** The pre-AI assessment must be hidden from AI output, submitted, and irreversibly locked on the server before reveal.
2. **Measure clinical work rather than system latency.** Decision time must come from event telemetry with idle-time rules; inference time and a clinician-entered estimate are not substitutes.
3. **Distinguish agreement, reliance, and correctness.** Agreement with AI is not diagnostic quality. Appropriate reliance requires an independent reference standard and all four reliance outcomes.
4. **Make longitudinal exposure observable.** Every decision needs participant, site, study phase, cumulative exposure, model, interface, and policy versions.
5. **Preserve an auditable research record.** Research events and submitted decisions must be append-only. Corrections should create new versions rather than overwrite or delete prior observations.

Adding the YOLOv8 segmentation checkpoint improves the range of visible findings but does not solve these measurement requirements. The DINO checkpoint is COCO initialization only and cannot contribute dental predictions until it is fine-tuned and validated. The segmentation model's scores are currently uncalibrated and must not be interpreted as probabilities of disease.

---

## 2. Revised research framing

### Working title

**From First Use to Calibrated Reliance: A Prospective Longitudinal Study of AI-Assisted Dental Decision-Making Across Five Clinics**

### Central question

How do clinician decision time, human-AI team accuracy, confidence, trust, and reliance change with repeated exposure to a diagnostic AI in routine dental work, and which error, feedback, workflow, and organizational conditions explain those changes?

### Research questions

- **RQ1 — Trajectories:** How do active decision time, team accuracy, confidence, trust, and workload change with cumulative AI exposure and calendar time?
- **RQ2 — Reliance:** How do appropriate reliance, over-reliance, and under-reliance change as clinicians encounter correct and incorrect AI outputs?
- **RQ3 — Recalibration events:** Which events—AI errors, adjudicated feedback, workload, workflow interruptions, or policy changes—precede changes in trust and reliance?
- **RQ4 — Context:** How do trajectories differ by clinical role, experience, case complexity, clinic workflow, and deployment policy?
- **RQ5 — Trade-offs:** Within clinicians, are reductions in active decision time associated with changes in team accuracy or inappropriate reliance?

### Claims that need revision before preregistration

- The proposed trust “honeymoon, dip, and recalibration” pattern should be an exploratory nonlinear trajectory unless prior evidence justifies a directional hypothesis.
- The claim that appropriate reliance improves “only if clinicians receive feedback” is causal. It requires an explicit feedback condition, preferably randomized or otherwise credibly controlled. Without that design, the claim must become an association.
- A speed-quality relationship can be estimated within clinicians, but observational cross-lagged associations do not establish that speed caused errors.
- Five clinics do not by themselves provide adequate statistical power. Power depends on the number of clinicians, cases per clinician, repeated survey waves, outcome prevalence, and intraclass correlations.
- Dentists, clinical directors, and claims staff perform different decisions. Their workflows and estimands should be separated rather than pooled into one trajectory.

### Intended contributions

1. Longitudinal field evidence about how clinical AI use changes after first adoption.
2. A process-level dataset linking pre-AI judgment, AI output, post-AI judgment, and adjudicated correctness.
3. Design and governance guidance for sustaining calibrated reliance across clinical sites.

---

## 3. What the current live pilot can and cannot measure

| Required construct | Current evidence | Publication consequence |
|---|---|---|
| Independent pre-AI decision | The live Next.js page loads AI results while the validation form is open and displays them beside pre-filled manual values. There is no server-side pre-AI state. | Pre-AI independence cannot be established; automation bias and change-after-AI cannot be estimated. |
| Decision quality | The API calculates clinician-AI class agreement and DHC difference. There is no adjudicated reference-standard workflow. | Agreement is not correctness. Accept-correct, reject-incorrect, over-reliance, and under-reliance cannot be derived. |
| Decision speed | `t_manual` is entered by the clinician; `t_ai` is populated from inference duration. | Neither is reliable active clinical decision time. Learning curves and speed-quality coupling are not supported. |
| Trust | Agreement, override, usefulness, and a categorical “calibration” response exist. No validated repeated trust scale is scheduled. | Behavioral reliance and subjective trust are conflated; longitudinal trust calibration cannot be computed. |
| Longitudinal exposure | Records have dates, free-text clinician/site fields, and case links. There is no enrolled participant, study phase, exposure counter, or repeated survey schedule. | Change over time cannot be reliably attributed to exposure, clinician, or deployment phase. |
| Model and interface provenance | Inference results retain a model version, and recent integration work adds artifact provenance. No study-wide UI/build/condition version is attached to each decision. | Silent model or interface changes can masquerade as learning or trust effects. |
| Research integrity | Clinical validation is stored in a separate SQLite table and supports update and delete operations. | The analytic record is mutable; chronology and corrections cannot be audited. |
| Site heterogeneity | A site code can be typed into each record. User profiles do not carry a governed participant/site/role identity. | Misclassification and cross-site identity drift are likely; hierarchical analysis is unreliable. |
| Qualitative and survey data | A free-text comment and usefulness rating are available. | No baseline/monthly trust, NASA-TLX, interview schedule, instrument version, or missingness trail exists. |
| General auditability | Generic request audit logs record path, status, and processing time. | They do not record reveal, inspect, accept, edit, idle, sign-off, or correction events needed for HCI analysis. |

### Particularly important implementation findings

- The live validation form initializes “manual” answers, time, usefulness, agreement, and override with favorable defaults. This risks anchoring and fabricated completeness.
- AI results are fetched before validation is submitted. The visible side-by-side layout defeats independent assessment.
- The older static clinical page contains a visual lock, but it is browser-only; clearing the form reverses it, and no locked pre-AI record is created on the server at reveal time.
- The clinical API accepts one combined payload containing manual and AI fields. It cannot prove their temporal order.
- Validation rows can be updated and deleted. A research dataset should permit append-only corrections with reason, author, and timestamp—not destructive mutation.
- Generic API request duration is infrastructure telemetry. It does not measure clinician attention or decision work.
- The “calibration” field asks the clinician to label the AI as well-, over-, or under-confident. Calibration is an empirical relationship between predictions and adjudicated outcomes, not a user opinion.

**Bottom line:** historical data from the current pilot may support product usage counts, feasibility observations, model-run performance, and descriptive agreement. It should not be retroactively represented as blinded pre/post decision data or as valid longitudinal trust-calibration evidence.

---

## 4. The Pilot v3 research workflow

The core unit should be a **decision episode**, enforced by a server-side state machine:

1. **Case assigned/opened** — record participant, site, study arm, case metadata, interface/model versions, and cumulative exposure.
2. **Pre-AI assessment** — capture diagnosis/finding decisions, treatment or referral action where relevant, confidence, and server-derived active time.
3. **Pre-AI lock** — persist a signed, immutable submission. No AI payload is returned to the client before this transition succeeds.
4. **AI reveal** — record the exact server and client times, displayed findings, ordering, threshold, score presentation, explanation condition, and any suppressed/failed outputs.
5. **AI interaction** — record item inspection, overlay toggles, zoom, explanation views, edits, acceptance, and override behavior.
6. **Final decision/sign-off** — capture the final diagnosis and action, confidence, item-level changes, rationale, active post-reveal time, and protocol deviations.
7. **Reference adjudication** — independently label sampled cases, blind adjudicators to the clinician decision where feasible, and resolve disagreement through a documented process.
8. **Feedback** — if the design includes feedback, reveal it only according to the assigned condition and record exposure.
9. **Correction** — append a correction event that references the prior version. Never erase the original decision episode.

No automated narrative, AI score, overlay, or result-derived default should be available before the pre-AI lock. Reference-standard outcomes must remain unavailable until the clinical decision is finalized.

---

## 5. Required data model

### Study and participant identity

- `study_id`, `protocol_version`, `site_id`, `participant_id` (pseudonymous), role, specialty, experience band, enrollment date, cohort/arm, consent version and timestamp, withdrawal status.
- Research consent must be distinct from product terms and patient clinical consent.
- Clinic and clinician identities must be governed records, not free text entered per case.

### Decision episode and exposure

- `episode_id`, `case_id`, `participant_id`, `site_id`, assigned condition, study phase, calendar period, cumulative eligible cases, cumulative AI reveals, and prior AI-error exposures.
- Stable identifiers for `model_run_id`, model artifact hash, post-processing version, calibration version, UI build, explanation condition, threshold set, and deployment-policy version.
- Freeze the model and interface within declared study epochs. Any change starts a new epoch and is included in the analysis.

### Append-only event telemetry

- Event UUID, schema version, sequence number, actor, episode/session IDs, event type, server timestamp, client timestamp, timezone offset, idempotency key, and structured payload.
- Minimum events: open, focus, blur, idle-start/end, pre-AI-submit, pre-AI-lock, reveal, finding-view, overlay-toggle, edit, accept, reject, override, final-submit, sign-off, reopen, correction, survey-open/submit, feedback-reveal, and protocol deviation.
- Separate upload time, queue time, inference time, network latency, page-render time, active clinician time, and elapsed wall-clock time.

### Pre-AI, AI, and final decisions

- Store all three as separate versioned objects at case and finding level.
- Capture diagnosis/finding class, location, severity, proposed clinical action, clinician confidence, and reason for change.
- Define the primary decision task in advance. Malocclusion classification and 31-class radiographic segmentation are different tasks and should not share a single accuracy or reliance denominator.

### Reference standard

- Prespecified sampling rule, adjudicator IDs/roles, blinding status, independent labels, disagreement, consensus/resolution, uncertainty, timestamps, and reference-standard version.
- Prefer two independent qualified reviewers plus an adjudicator for disagreements where resources allow.
- Define case-level and item-level matching rules, including localization tolerance and handling of clinically equivalent labels.

### Surveys and interviews

- Validated trust-in-automation instrument at baseline and prespecified repeated intervals.
- Workload instrument at a cadence that does not create excessive burden; preserve exact instrument/version/language.
- Per-case diagnostic confidence before and after AI.
- Survey invitation, display, start, submit, missingness reason, version, and completion timestamps.
- Interview sampling triggers, consent, guide version, interviewer, date, recording/transcription status, and a separate qualitative-data governance plan.

### Context and confounders

- Modality, image quality, case complexity, urgency, referral status, case type, workload/queue, shift/time of day, device, network quality, interruption indicators, and clinic policy.
- Do not collect patient or employee identifiers merely because they are available. Use the minimum data needed for the estimands and governance plan.

---

## 6. Outcome definitions that Pilot v3 must support

### Human-AI team quality

Report accuracy/error against the independent reference standard, not only clinician-AI agreement. Predefine whether the primary endpoint is case-level diagnosis, finding detection, severity grading, referral/treatment decision, or another clinical action.

### Reliance matrix

| AI correctness | Clinician final behavior | Outcome |
|---|---|---|
| Correct | accepts/retains AI recommendation | Appropriate acceptance |
| Incorrect | rejects/corrects AI recommendation | Appropriate rejection |
| Incorrect | accepts/retains AI recommendation | Over-reliance |
| Correct | rejects/removes AI recommendation | Under-reliance |

Calculate this at the prespecified decision level. “Agree,” “partial,” and “override” alone are not sufficient.

### Speed

Use active pre-AI time, active post-reveal time, and total active decision time with documented idle/background rules. Report infrastructure latency separately. Throughput is a clinic-level operational outcome and requires eligible-case denominators.

### Trust and calibration

Treat subjective trust, diagnostic confidence, and behavioral reliance as related but distinct constructs. Estimate actual AI reliability from adjudicated outcomes within defined windows. Do not compare a trust score directly with raw, uncalibrated neural-network confidence.

### Safety and clinical impact

Track critical misses, harmful accepted errors, delayed care, escalation, and adverse-event review. A study in which AI-supported decisions affect care needs an explicit safety-monitoring and stopping/escalation procedure.

---

## 7. Study-design requirements

### Minimum defensible design

- Prospective, repeated-measures, multi-site field deployment lasting long enough to observe stable exposure rather than merely calendar time.
- A baseline or run-in phase and a frozen v3 study epoch.
- Prespecified primary outcome and estimand; secondary outcomes clearly labeled.
- Power simulation using clinicians, cases per clinician, outcome prevalence, repeated waves, attrition, and within-clinician/site correlation. “Five clinics” is context, not a sample-size justification.
- Participant- and case-flow diagrams with eligibility, exclusions, missingness, AI failures, and protocol deviations.
- Model validation on the intended population before assisted clinical use, including per-class performance, calibration, site/modality subgroups, and clinically important error analysis.

### If testing feedback as a mechanism

The original H3 requires a designed contrast. Feasible options include clinician- or case-level randomized feedback, a prespecified crossover, or a carefully designed staged introduction. A five-site cluster-randomized study is likely fragile because there are too few clusters; simulation and operational review are required before choosing it.

### Analysis cautions

- Use exposure count and calendar time separately.
- With only five sites, consider site fixed effects or partial pooling with sensitivity analysis rather than relying on a clinic random-effect estimate alone.
- Model nonlinear time only if the number and spacing of observations support it.
- Separate within-clinician change from between-clinician differences.
- Predefine missing-data, dropout, model-failure, interrupted-session, and multiple-testing handling.
- Use qualitative findings to explain mechanisms; do not use interviews to repair missing quantitative provenance.

Use the DECIDE-AI checklist as a design and reporting audit for an early live clinical AI evaluation, alongside the appropriate study-design guideline. If the study becomes randomized, use SPIRIT-AI for the protocol and CONSORT-AI for the report.

---

## 8. Publication venue assessment as of 20 July 2026

| Venue | Current fit | Current-pilot sufficiency | Recommendation |
|---|---|---|---|
| **CHI 2027** | Strong if the contribution is a rigorous, generalizable longitudinal HCI result. Full-paper deadline: **10 Sep 2026 AoE**. | **No.** A new 3–6 month study cannot be instrumented, approved, run, analyzed, and written credibly in the remaining window. | Do not target the full longitudinal paper unless compliant data collection is already well underway. Target CHI 2028 for the complete study. |
| **IUI 2027** | Strong for trust/reliance in an intelligent interface with both computational and human-centered evaluation. Abstract: **13 Aug 2026**; paper: **20 Aug 2026**. | **No.** The deadline is incompatible with collecting the proposed longitudinal dataset now. | Consider a later IUI cycle; use 2027 only for an already-complete, narrower study. |
| **CSCW 2027+** | Conditional. Strong only if the paper centers collaborative clinical work: handoffs, team coordination, clinic policy, escalation, and organizational adaptation. | **No** for the present individually focused framing. The draft's “rolling anytime” assumption is unsafe; CSCW 2026 used one submission cycle. | Reframe around multi-role collaborative practice before choosing CSCW, and wait for the official 2027 call. |
| **npj Digital Medicine** | Potentially strong for validated clinical AI with meaningful implementation or efficacy evidence. | **No.** The journal states that it typically does not consider off-the-shelf AI, purely observational work, case studies, or small preliminary studies. | Treat as a later-stage target after local model validation and a comparative/interventional clinical evaluation. |
| **JMIR Human Factors** | Very good fit for rigorous evaluation of usability, safety, workflow, error prevention, trust, and human factors. | **Not yet**, but attainable with v3 prospective data. | Best candidate for the complete human-factors study if the contribution remains clinical/HCI focused. |
| **JMIR Formative Research** | Explicitly accepts feasibility, pilot, process, and preliminary studies. | **Closest realistic fit**, provided the methods and data are prospective and valid. | Strong first publication target for v3 feasibility/process outcomes. |
| **JMIR AI** | Good for generalizable real-world AI evaluation; single-product usability studies are out of scope. | **No** as a product-specific pilot alone. | Target later if the paper contributes transferable evaluation methodology plus strong model/clinical evidence. |
| **AMIA 2027 Amplify** | Good applied-informatics fit for real-world implementation, human factors, infrastructure, and practice change. Proposal deadline: **3 Sep 2026**. | Possibly sufficient only for a systems demonstration or early implementation proposal—not the claimed longitudinal result. | Consider a bounded implementation submission while preserving the full study for a later archival paper. |
| **AMIA 2027 Annual Symposium** | Plausible for rigorous biomedical-informatics methods and evaluation. | **Not yet.** The 2027 annual-symposium call was not available at assessment time. | Monitor the official call; do not present “~March” as a confirmed deadline. |

### Recommended publication path

1. **Immediate:** freeze the research question, define the primary clinical task, obtain ethics/governance approval, and build/verify v3.
2. **Near-term output:** protocol, formative/process evaluation, or applied systems demonstration—without overstating longitudinal findings.
3. **After prospective data:** JMIR Human Factors or a later CHI/IUI cycle for the main longitudinal paper.
4. **After validated comparative clinical evidence:** consider npj Digital Medicine or JMIR AI.
5. **CSCW only if collaboration is central:** include multi-role coordination and organizational practices as outcomes, not merely clinic as a random effect.

---

## 9. Pilot v3 release gates

### Gate 0 — Research lock

- Ethics/DPIA/data-use approvals complete.
- Primary task, estimand, outcomes, sampling, feedback condition, and analysis plan finalized.
- Data dictionary, case report forms, survey instruments, consent language, and power simulation approved.

### Gate 1 — Measurement integrity

- Server-enforced pre-AI lock and reveal state machine passes tests.
- No AI-derived data or defaults reach the client before lock.
- Append-only events include ordering, idempotency, and clock checks.
- Decision-time logic excludes idle/background periods and separates latency.

### Gate 2 — Clinical and model readiness

- Intended-use statement, modality/task boundaries, contraindications, and escalation rules documented.
- Each deployed model has artifact hash, training/validation provenance, threshold, calibration status, subgroup/error analysis, and local validation.
- The COCO DINO checkpoint is excluded from clinical output until dental fine-tuning and validation are complete.
- The segmentation model's uncalibrated scores are labeled and not treated as disease probabilities.

### Gate 3 — Dry run

- End-to-end shadow cases cover every state transition, failure mode, correction path, survey schedule, and reference-standard workflow.
- Cross-site identity, missingness, event ordering, and export reconciliation are verified.
- A data-monitoring dashboard detects protocol leakage, missing pre-AI locks, impossible timings, duplicate episodes, and version drift.

### Gate 4 — Study launch

- Model, interface, instruments, and policy are frozen for the declared epoch.
- Participant onboarding and training are standardized and recorded.
- Safety monitoring, adverse-event escalation, support, and change-control procedures are active.

### Gate 5 — Reproducible analysis

- Versioned, deidentified data snapshots can be regenerated from source events.
- Analysis tables have lineage to episode/event IDs and reference-standard versions.
- Codebook, exclusions, derived-variable tests, missingness report, and immutable export manifest are produced automatically.

**No-go rule:** do not begin primary longitudinal data collection until Gates 0–3 pass. Data collected earlier may be retained for engineering or feasibility analysis but must be labeled as pre-v3 and should not be mixed into the confirmatory longitudinal dataset.

---

## 10. What v3 should produce for the paper

At minimum, the research export should generate these linked, deidentified tables:

- `participants` — stable clinician/site identity, role, experience, enrollment, arm, consent, and attrition.
- `episodes` — case context, study phase, exposure, versions, eligibility, and status.
- `events` — ordered append-only interaction telemetry.
- `pre_ai_decisions` — locked unaided assessments and confidence.
- `ai_outputs` — exact outputs presented, scores, thresholds, explanations, latency, and failures.
- `final_decisions` — accepted/edited/rejected items, final confidence, actions, and reasons.
- `reference_standard` — independent labels, adjudication, uncertainty, and matching version.
- `surveys` — baseline/repeated trust, workload, instrument metadata, and missingness.
- `feedback_exposures` — assigned/received feedback with timing and content version.
- `safety_events` — critical misses, accepted harmful errors, escalation, and resolution.

Derived analysis tables should include case-level quality, finding-level reliance, participant-period trajectories, survey waves, and site operations. Every row must retain lineage to the underlying immutable source records.

---

## 11. Final answer to the publication-readiness question

The current live pilot would suffice for a **technical demonstration, usability walkthrough, or descriptive feasibility report**. It does not suffice for the proposed longitudinal study because its data cannot establish independent pre-AI judgment, adjudicated correctness, active decision time, repeated validated trust, longitudinal exposure, or immutable provenance.

Pilot v3 can make the study publishable if its first objective is measurement validity, its second is clinical/model validity, and its third is interface improvement. More predictions, richer masks, and better reports are useful product features, but they are not substitutes for a study-grade decision protocol.

The most realistic high-quality path is to build and validate v3 now, use a formative or applied-informatics venue for early evidence, collect at least one complete prespecified longitudinal epoch, and then submit the full paper to JMIR Human Factors or a later CHI/IUI cycle. npj Digital Medicine should remain a later-stage target. CSCW should remain conditional on a genuine collaborative-work contribution.

---

## Sources and standards

- [ACM CHI 2027 Papers: submission details and dates](https://chi2027.acm.org/authors/papers/)
- [ACM IUI 2027 deadlines listed by IUI](https://iui.acm.org/2026/)
- [ACM IUI call: scope and evidentiary expectations](https://iui.acm.org/2026/call-for-papers/)
- [ACM CSCW 2026 papers: single-cycle submission model](https://cscw.acm.org/2026/papers.html)
- [ACM CSCW 2027+ track guidance](https://cscw.acm.org/2026/tracks.html)
- [npj Digital Medicine aims and scope](https://www.nature.com/npjdigitalmed/aims)
- [JMIR Human Factors focus and scope](https://humanfactors.jmir.org/about-journal/focus-and-scope)
- [JMIR Formative Research focus and scope](https://formative.jmir.org/about-journal/focus-and-scope)
- [JMIR AI focus and scope](https://ai.jmir.org/about-journal/focus-and-scope)
- [AMIA 2027 Amplify Clinical Informatics call](https://amia.org/education-events/2027-amplify-informatics-conference/cic-proposals)
- [DECIDE-AI early-stage clinical AI reporting guideline](https://www.nature.com/articles/s41591-022-01772-9)
- [SPIRIT-AI protocol guideline](https://www.nature.com/articles/s41591-020-1037-7)
- [CONSORT-AI trial-reporting guideline](https://www.nature.com/articles/s41591-020-1034-x)
