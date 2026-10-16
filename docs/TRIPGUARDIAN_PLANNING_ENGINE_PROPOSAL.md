# TripGuardian Planning Engine Improvement Proposal

## 1. Objective

Improve TripGuardian's itinerary planning for user-selected destinations in Da Lat. The planner should create schedules that are geographically efficient, realistic in duration, suitable for the time of day, and adaptable to individual preferences.

The goal is **not** to make every itinerary follow one fixed lifestyle pattern. Rules such as “high-energy activities in the morning,” “cafés after tiring activities,” or “photography in the afternoon” are hypotheses that may suit some users and places but not others. They should be configurable preferences or soft optimization signals, not universal rules.

The proposed approach combines:

- Structured place data and evidence-based duration estimates.
- LLM-assisted interpretation of natural-language requests and uncertain place attributes.
- A deterministic scheduling and optimization engine.
- Independent validation of hard constraints and schedule feasibility.
- User feedback and personalization to improve later plans.

## 2. Core Design Principles

1. **Hard constraints are never traded away.** Opening hours, fixed appointments, travel feasibility, locked destinations, and other physical constraints must be satisfied or explicitly reported as infeasible.
2. **Preferences are soft constraints.** Activity timing, recovery stops, pace, photography opportunities, and route compactness should influence the score but remain adjustable.
3. **Do not assume one ideal travel style.** Activity transitions should be inferred from explicit user preferences where possible, and otherwise use neutral defaults with low confidence.
4. **Evidence before assumptions.** Facts such as opening hours must have a source. Estimates should include a range and confidence.
5. **Optimize the whole schedule, not isolated stops.** A locally attractive next destination can produce a poor overall route or an exhausting day.
6. **Keep the planner explainable.** The system should be able to explain why a stop was placed at a certain time and which preferences or constraints influenced the decision.
7. **Personalize without overfitting.** A single user edit should not automatically become a permanent preference. Distinguish trip-specific requests, session signals, and stable preferences.
8. **Fail transparently.** If the data are incomplete or no feasible schedule exists, expose uncertainty and offer alternatives instead of inventing facts.

## 3. Proposed Architecture

### 3.1. Planning pipeline

1. **Parse the request**
   - Resolve the user's selected place names to canonical `place_id` values.
   - Extract trip dates, start/end times, transport mode, must-visit anchors, meal needs, budget constraints, and explicit preferences.
   - Ask a clarification question only when an ambiguity materially affects feasibility or the result.

2. **Retrieve place intelligence**
   - Fetch normalized serving records for the selected places and relevant nearby alternatives.
   - Retrieve opening hours, location coordinates, activity attributes, visit-duration estimates, time suitability, evidence, and confidence.
   - Retrieve live or cached travel times, weather, sunrise/sunset, and other context when available.

3. **Estimate visit duration**
   - Produce a plausible duration range rather than relying on a single crawler-derived estimate.
   - Adapt the selected duration to user pace and intended activity.
   - Preserve uncertainty when evidence is weak.

4. **Generate candidate schedules**
   - Group nearby locations using travel-time data.
   - Generate plausible visit orders and time-slot assignments.
   - Insert meal and rest blocks according to explicit requirements and configurable defaults.

5. **Score and optimize**
   - Score complete candidate itineraries against travel, timing, fatigue, meal, preference, and robustness criteria.
   - Search for a good feasible plan while respecting hard constraints.
   - Return a small set of meaningfully different alternatives when useful.

6. **Validate independently**
   - Recalculate the timeline from the chosen sequence.
   - Check opening hours, travel, visit durations, breaks, fixed commitments, and other hard constraints.
   - Do not accept an itinerary solely because an LLM says it is feasible.

7. **Explain and learn**
   - Explain important scheduling decisions and uncertainty.
   - Collect user edits and feedback, while distinguishing temporary requests from long-term preferences.

### 3.2. Division of responsibility

| Component | Main responsibility |
|---|---|
| LLM | Interpret natural-language requests; propose classifications from supplied evidence; summarize trade-offs |
| Place data and estimation rules | Provide source-backed facts, duration ranges, time suitability, and confidence |
| Optimization engine | Select ordering, time slots, meals, rest periods, and trade-offs |
| Timeline simulator | Compute arrival, departure, waiting, travel, and buffer time |
| Validator | Enforce hard constraints and determine feasibility |
| Feedback layer | Record explicit preferences and user-approved learning signals |

The LLM must not invent opening hours, travel times, or evidence for a location. Every factual value used by the planner should come from a data source or a clearly labelled fallback estimate.

## 4. Place Data and Duration Estimation

### 4.1. Normalize the serving data

Avoid reading scattered crawler files during each planning request. Build a normalized, indexed serving record for each location.

Suggested fields:

```text
PlaceServing
├── identity
│   ├── place_id, canonical_name, aliases, coordinates, area
├── operations
│   ├── opening_hours, closures, meal_services
├── activity_profile
│   ├── activity_types, energy_range, recovery_potential
├── duration_estimate
│   ├── short, typical, long, confidence, evidence
├── time_suitability
│   ├── sunrise, morning, noon, afternoon, sunset, night
├── contextual_signals
│   ├── crowd_by_time, weather_sensitivity, seasonal_context
└── provenance
    ├── source, observed_at, freshness, estimation_method
```

These are proposed fields; they should only be populated when supported by evidence or explicitly marked as inferred estimates.

### 4.2. Use duration ranges

For each place, maintain three estimates:

- `short`: a reasonable quick visit.
- `typical`: a normal visit under the stated assumptions.
- `long`: an extended visit, such as more exploration or photography.

Illustrative category defaults (not measured values for specific Da Lat places):

| Activity type | Short | Typical | Long |
|---|---:|---:|---:|
| Café | 30 min | 60 min | 90 min |
| Pagoda / temple | 30 min | 60 min | 90 min |
| Scenic viewpoint | 20 min | 45 min | 75 min |
| Photography attraction | 30 min | 60 min | 100 min |
| Hiking / demanding outdoor activity | 60 min | 120 min | 180 min |

Use the best available evidence in roughly this order:

1. Reliable observed visit-duration data, after filtering implausible stays.
2. Location-specific evidence about size, facilities, trails, activities, and repeated visitor reports.
3. Activity-category estimates adjusted by place attributes.
4. Configurable fallback defaults with low confidence.

Do not treat Google Maps' generic estimate as ground truth. Also distinguish a true visit from time spent inside a large zone or business district.

A baseline can be derived from observed data:

\[
D_{\mathrm{base}} = \operatorname{median}(D_{\mathrm{reliable\ observations}})
\]

Then adapt the planned duration to pace and intended activity:

\[
D_{\mathrm{planned}} =
\operatorname{clip}(D_{\mathrm{base}} \times M_{\mathrm{pace}} \times M_{\mathrm{activity}},
D_{\min}, D_{\max})
\]

The multipliers and limits must be configurable and calibrated with evaluation data. Do not imply that they are learned if they are only heuristics.

### 4.3. Keep time components separate

Represent these as distinct timeline components:

- `visit_duration`
- `travel_duration`
- `queue_duration`, when supported by evidence
- `meal_duration`
- `recovery_duration`
- `buffer_duration`

This makes it clear why a stop occupies a particular block and prevents travel, queues, or rest from being silently mixed into the visit estimate.

### 4.4. Store confidence and provenance

Each estimate should include fields such as:

```text
value_or_range
confidence: high | medium | low
source_type
source_reference
estimated_at
estimation_method
```

Low-confidence values should result in wider ranges or more schedule buffer. Missing evidence should not be silently converted into a confident fact.

## 5. Activity Profiles and Time Suitability

### 5.1. Describe what a place supports

A broad category such as `cafe`, `pagoda`, or `viewpoint` is not enough to determine its best scheduling role. Use a flexible profile:

| Attribute | Example | Purpose |
|---|---|---|
| `activity_types` | coffee, sightseeing, photography | Describes possible activities |
| `energy_level` | low / medium / high, possibly a range | Approximate physical demand |
| `time_windows` | sunrise, daytime, sunset, night | Candidate suitable periods |
| `weather_sensitivity` | indoor / mixed / outdoor exposed | Supports weather-aware scheduling |
| `visit_range` | short / typical / long | Supports duration estimation |
| `recovery_potential` | low / medium / high / unknown | Estimates whether the stop can be restful |
| `meal_role` | breakfast / lunch / dinner / none / unknown | Helps determine whether it can fulfil a meal |
| `confidence` | high / medium / low | Communicates evidence quality |

A place can support multiple activities. A café is not automatically a recovery stop, and a viewpoint is not automatically best at night. Its profile should depend on location-specific evidence and what the user wants to do there.

### 5.2. Score time-slot suitability

For place \(p\), activity \(a\), user \(u\), and visit interval \(t\), calculate a configurable suitability score:

\[
S_{\mathrm{time}}(p,a,u,t) =
w_1 E_{\mathrm{place}}(p,a,t) +
w_2 E_{\mathrm{evidence}}(p,t) +
w_3 P_{\mathrm{user}}(u,p,a,t)
\]

Where:

- \(E_{\mathrm{place}}\): suitability of the place and activity for that period.
- \(E_{\mathrm{evidence}}\): strength of available location-specific evidence.
- \(P_{\mathrm{user}}\): alignment with the user's stated or learned preferences.
- \(w_1,w_2,w_3\): configurable weights.

This score is a preference signal, not proof. Opening hours and other physical restrictions remain hard constraints. Score the full visit interval, not only its start time. For example, a visit that extends beyond closing time should be rejected or adjusted.

Use neutral scores when there is no evidence, and reduce the influence of low-confidence signals. Avoid assigning a high suitability score based only on a generic category.

## 6. Personalization and Activity Transitions

### 6.1. Treat transitions as hypotheses, not rules

Patterns such as the following may be useful but are not universally true:

- High-energy activities in the morning.
- A café after a tiring activity.
- Photography in the afternoon.
- A rest period after lunch.
- Scenic viewpoints near sunset or at night.

The best sequence depends on the user, the exact place, opening hours, weather, travel distances, companions, and the purpose of the trip. Therefore, encode these patterns as configurable soft preferences, not mandatory transitions.

Examples:

- If the user explicitly asks for a full hour of rest after lunch, treat it as a trip-level constraint.
- If the user says they enjoy photography at golden hour, strongly prioritize relevant, evidence-supported time windows.
- If the user dislikes cafés or prefers to keep moving, do not insert cafés simply because the previous stop was strenuous.
- If the user is comfortable with intense activity all day, reduce the fatigue penalty while preserving safety and practical constraints.
- If no preference is known, use balanced defaults with modest weights and allow the optimizer to choose a reasonable sequence.

### 6.2. Model activity transitions with a soft score

Instead of hardcoding rules like “after two demanding attractions, insert a café,” define a transition score between consecutive stops:

\[
S_{\mathrm{transition}}(p_i,p_j,u) =
f(\mathrm{effort}_i,\mathrm{recovery}_j,
\mathrm{travel}_{ij},\mathrm{preferences}_u)
\]

The score can reward a useful recovery stop or penalize an exhausting sequence only when relevant to the user and supported by the stop profiles.

A transition can be evaluated using:

- Effort and duration of the previous activity.
- Recovery potential of the next activity.
- Travel time or detour required.
- User preference for breaks, cafés, movement, or activity density.
- Confidence in the underlying activity classifications.

The model should not force a recovery stop if it creates a long detour or conflicts with the user's preferences. A nearby bench, quiet attraction, hotel break, or no extra stop at all may be better.

### 6.3. Optional fatigue state

A simple fatigue state can be tested as a heuristic:

\[
F_{t+1} = \max(0,F_t + L_t - R_t)
\]

Where \(L_t\) represents effort accumulated from activities and travel, and \(R_t\) represents recovery from breaks or lower-intensity periods.

Use this only as an approximate planning signal. It is not a medical or physiological measurement. Calibrate it with user feedback, make its effect configurable, and allow a user preference to lower or raise the soft fatigue penalty. Do not let this score override physical safety constraints.

### 6.4. Separate preference scopes

Maintain three different sources of preference:

1. **Trip-specific instructions:** “Rest for one hour after lunch today.” Apply to the current plan.
2. **Session-level signals:** The user repeatedly extends photography stops or removes café breaks during this planning session. Use these as tentative evidence.
3. **Stable preferences:** A preference saved or confirmed by the user, such as relaxed pacing or photography-focused travel.

Do not convert one edit into a permanent profile change automatically. Let users inspect, correct, or reset learned preferences.

## 7. Route and Schedule Optimization

### 7.1. Optimize the whole itinerary

For a candidate itinerary \(I\), minimize a weighted objective:

\[
\begin{aligned}
J(I) ={}&
w_d C_{\mathrm{travel}} +
w_t C_{\mathrm{timing}} +
w_f C_{\mathrm{fatigue}}\\
&+ w_m C_{\mathrm{meal}} +
w_p C_{\mathrm{preference}} +
w_r C_{\mathrm{risk}}
\end{aligned}
\]

Potential terms:

| Cost | Purpose |
|---|---|
| `C_travel` | Penalize excessive travel, backtracking, and unnecessary detours |
| `C_timing` | Penalize visits outside suitable periods |
| `C_fatigue` | Penalize demanding sequences when the user's preferences support doing so |
| `C_meal` | Penalize missed meal requirements or inconvenient meal timing |
| `C_preference` | Penalize deviations from explicit user priorities |
| `C_risk` | Penalize fragile plans with little buffer or uncertain duration estimates |

Weights should be configurable and tested. Normalize terms before combining them so that one term does not dominate merely because it uses larger numeric values.

Hard constraints are not simply extra penalties. Examples include a place being closed, a locked anchor being moved, or a fixed appointment being missed. If no feasible schedule exists, report the conflict and ask the user which flexible preference they want to relax.

### 7.2. Practical optimization workflow

1. Resolve selected locations to canonical place IDs.
2. Retrieve place profiles, hours, evidence, and confidence.
3. Estimate visit durations according to the intended activity and user pace.
4. Build a travel-time matrix from OSRM or a suitable cache.
5. Cluster nearby places without breaking important time-window requirements.
6. Generate candidate visit orders and time-slot assignments.
7. Insert required meals, fixed commitments, and requested breaks.
8. Simulate the full timeline, including travel, queues, buffers, and recovery.
9. Score feasible schedules using the objective function.
10. Apply local improvements and independently validate the final schedule.
11. Return the best plan and, where useful, alternatives with different trade-offs.

For small sets of stops, exhaustive ordering can be practical. For larger sets, use a heuristic such as nearest-neighbour initialization followed by 2-opt or another local search. This is a practical search strategy, not a guarantee of global optimality.

### 7.3. Meals and post-lunch rest

Meals should be explicit schedule blocks. Use configurable meal windows and the user's preferences rather than fixed universal times.

- Breakfast, lunch, and dinner can be represented as required, optional, or user-specified.
- A restaurant can fulfil a meal only if its meal service and opening hours support it.
- A post-lunch rest can be mandatory when the user requests it, or a soft default otherwise.
- If a meal location is not among the user's selected places, the system can search nearby candidates when the user permits it.
- Do not silently add a restaurant or rest stop that materially changes the user's plan without making the addition visible.

## 8. LLM Integration

Use the LLM at clearly bounded decision points.

| Task | Method |
|---|---|
| Parse natural-language trip requests | LLM with structured output and schema validation |
| Interpret an ambiguous place or activity | LLM grounded in supplied corpus evidence |
| Suggest an activity profile | LLM proposal followed by evidence and confidence checks |
| Estimate duration where evidence is weak | Category-based baseline plus bounded, low-confidence LLM assistance |
| Optimize visit order and timestamps | Deterministic algorithm |
| Verify hours, travel, and feasibility | Data-backed code and independent validator |
| Explain the result | LLM grounded in the computed itinerary and diagnostics |
| Apply a natural-language edit | LLM interprets the edit; planning engine recomputes affected portions |

The LLM should return structured fields rather than unvalidated prose. For inferred fields, retain the evidence or explanation and confidence. Reject malformed or unsupported values and use deterministic fallback behavior.

## 9. Data Access and Precomputation

Create a normalized, indexed serving layer rather than querying scattered crawler files for every request.

Useful precomputed information includes:

- Duration ranges and confidence.
- Activity profiles and time-suitability scores.
- Nearby-place candidates.
- Location coordinates and canonical identities.
- Reusable travel-time information where freshness permits.

Do not precompute every possible itinerary. The user's chosen destinations, dates, transport, pace, and fixed commitments vary. Precompute reusable place-level features and optimize the selected set at runtime.

Use provenance and freshness fields. For live values, retain source and retrieval time. If OSRM, weather, or other live services fail, clearly label fallback estimates and lower the schedule's robustness rating.

## 10. Validation and Robustness

The validator should independently check:

- Every required or locked location is preserved.
- Opening hours and visit intervals are compatible.
- Travel time fits between consecutive stops.
- Visit, meal, and rest durations do not overlap incorrectly.
- Fixed commitments are respected.
- Required meals and explicit breaks are present.
- Buffers and uncertain duration estimates are reflected in the robustness assessment.
- No unsupported factual value is presented as verified.

A plan that passes basic feasibility checks is not necessarily robust. A schedule with uncertain duration estimates and no buffers should not receive the same confidence as one with reliable evidence and sufficient slack.

If a plan fails, the system should explain the conflict, attempt safe local repairs, and return alternatives where possible. It must not silently move locked places or relax physical constraints.

## 11. Evaluation Plan

Evaluate the planner on a manually reviewed set of Da Lat trips covering different place types, trip lengths, user paces, time-sensitive attractions, meal needs, and weather conditions.

Compare progressively richer versions:

1. Route ordering only.
2. Route ordering plus meal and rest handling.
3. Addition of time-slot suitability.
4. Addition of user-personalized transition and fatigue scoring.
5. Addition of uncertainty-aware duration ranges and robustness optimization.

Metrics:

| Metric | What it measures |
|---|---|
| Hard-constraint violations | Must be zero for accepted plans |
| Opening-hour violations | Whether visits occur when closed |
| Travel time per day | Route efficiency |
| Time-slot suitability | Whether visits occur at appropriate periods |
| Selected-stop coverage | Whether requested places are preserved |
| Meal and rest compliance | Whether required blocks are respected |
| Duration error | Difference from reliable observed visit durations |
| Robustness | Whether small delays make the schedule infeasible |
| User edit rate | How often users need to change the proposed plan |
| User satisfaction | Whether timing and sequencing feel appropriate |

Use simulated cases for early development, but do not treat LLM-generated user feedback as a substitute for real user testing. Inspect failed schedules and evaluate whether each added component improves the outcome.

## 12. Implementation Roadmap

### Phase 1 — Data foundation

- Normalize place records and index fields needed by Planning.
- Add activity profiles, duration ranges, provenance, and confidence.
- Establish conservative defaults for missing data.
- Measure retrieval and duration-estimation performance.

### Phase 2 — Better scheduling

- Add time-slot suitability scores.
- Model meals and requested breaks as explicit blocks.
- Extend the current optimizer's objective with travel, timing, and schedule robustness.
- Preserve independent validation and hard-constraint enforcement.

### Phase 3 — Personalization

- Add relaxed, balanced, and packed pace profiles as editable starting points.
- Allow users to specify preferences such as photography, cafés, rest, outdoor activity, or maximum daily travel.
- Add configurable transition and fatigue penalties.
- Separate trip instructions, temporary session signals, and saved preferences.

### Phase 4 — Evaluation and calibration

- Build a benchmark set of representative trips.
- Run ablation tests against simpler baselines.
- Tune weights using evaluation data and real user feedback.
- Track failures, confidence calibration, user edits, and satisfaction.

## 13. Final Recommendation

The highest-priority improvements are:

1. **Reliable duration ranges** rather than single crawler-derived estimates.
2. **Evidence-backed time-slot suitability** for each location and intended activity.
3. **A constraint-based optimizer** that combines travel efficiency, timing, meals, and schedule robustness.
4. **Personalizable activity transitions** treated as soft preferences, not universal truths.
5. **Independent validation and evaluation** to ensure that the resulting itinerary is both feasible and useful.

The central design principle is that the planner should optimize for **this user's trip**, not for a fixed assumption about how everyone should travel. The LLM helps interpret preferences and evidence; the optimizer chooses the schedule; the validator decides whether it is feasible.
