# Forest Systems Dashboard
## Replacement MVP Specification

This document replaces the previous cohort-landscape engine specification.

The product defined here is not a GIS map, not a cohort simulator, and not a generic forestry sandbox. It is a constrained, individual-tree, systems-first simulator built to make forest succession legible.

The first version should behave like a scientific systems toy:

- small enough to understand
- explicit enough to trace cause and effect
- constrained enough to actually ship
- grounded enough to later support literature-backed refinement

---

## 1. Product Definition

### 1.1 What This Product Is

The MVP is a live dashboard for an abstract, Pacific Northwest-inspired western conifer forest stand.

It simulates:

- individual trees
- four fixed tree temperaments
- ongoing growth, suppression, reproduction, turnover, and disturbance
- emergent forest composition over time
- causal relationships between base controls, intermediate state, and outcomes

The core user experience is:

1. open the dashboard
2. watch the forest evolve continuously
3. change a few live controls
4. see how those controls propagate through the system
5. understand why forest composition changes

### 1.2 What This Product Is Not

The MVP is not:

- a real geographic map
- a raster landscape simulator
- a species identification tool
- a biomass accounting tool
- a full forestry planning product
- a shrub, fuel, fungal, soil biogeochemistry, or wildlife simulator

### 1.3 Design Goal

The product must answer three questions at all times:

1. What exists in the forest right now?
2. What forces are acting on it right now?
3. Why is the composition changing?

If the interface cannot answer those questions quickly, the MVP has failed.

---

## 2. Scientific Framing

### 2.1 Ecological Scope

The MVP represents an abstract western conifer stand inspired by Pacific Northwest forest dynamics.

It is intentionally not species-resolved in version 1. Instead, it models four fixed ecological roles derived from two axes:

- temperament axis: `gambler` vs `struggler`
- structural axis: `large` vs `small`

### 2.2 Meaning of the Two Axes

`Gambler` means:

- more disturbance-opportunistic
- more dependent on opening and opportunity
- higher reproductive output
- weaker long-term persistence under suppression

`Struggler` means:

- more suppression-tolerant
- slower and more conservative
- lower reproductive output
- better long-term persistence under canopy

`Large` means:

- capable of becoming canopy-dominant
- capable of creating a meaningful canopy opening when it dies

`Small` means:

- typically not a major gap-maker
- responds to canopy conditions but does not usually create major openings itself

### 2.3 Central Succession Loop

The simulator revolves around one ecological cycle:

1. canopy closes
2. suppressed trees persist or fail underneath
3. a large tree dies or is disturbed
4. canopy gap opens
5. regrowth opportunity increases
6. gamblers exploit the opening more aggressively
7. some recruits eventually become future large gap-makers
8. forest composition shifts over time

This loop must be visible in both the model and the UI.

---

## 3. Fixed Tree Temperaments

Version 1 uses exactly four tree roles:

1. `Large Gambler`
2. `Small Gambler`
3. `Large Struggler`
4. `Small Struggler`

These are fixed built-in identities in version 1.

### 3.1 Large Gambler

Expected behavior:

- recruits strongly after canopy opening
- grows aggressively in favorable conditions
- can eventually become canopy-dominant
- creates real openings when mature individuals die
- tends to be less persistent under long suppression

### 3.2 Small Gambler

Expected behavior:

- recruits strongly after canopy opening
- turns over relatively quickly
- responds rapidly to opportunity
- rarely creates a major canopy opening when it dies

### 3.3 Large Struggler

Expected behavior:

- persists under shade better than gamblers
- slower, steadier growth
- lower reproductive opportunism
- can eventually become canopy-dominant
- creates meaningful openings when it dies

### 3.4 Small Struggler

Expected behavior:

- strong persistence under suppression
- slower growth
- lower reproductive opportunism
- rarely creates a major canopy opening when it dies
- functions as a durable subordinate or subcanopy presence

### 3.5 Constraints

The temperaments must differ through mechanisms, not arbitrary buffs.

Allowed mechanism differences:

- growth potential
- suppression tolerance
- reproductive output
- chance of successful recruitment after opening
- sensitivity to drought/heat
- mortality risk profile
- maximum structural size class

Not allowed:

- unexplained hidden advantages
- cosmetic role differences with no systemic meaning

---

## 4. Simulation Scope

### 4.1 Simulation Unit

The simulation unit is the individual tree.

Version 1 does not use cohorts.

### 4.2 World Model

The forest is a single stand, not a mapped landscape.

The stand is modeled as an abstract forest population with canopy structure and composition state. Version 1 does not require a geographic map or a visible spatial stand view.

### 4.3 Version 1 Contents

Included:

- individual trees
- four temperaments
- established stand at startup
- continuous playback in the UI
- fire, wind, and drought/heat stress
- baseline aging and turnover
- composition dashboard
- node graph of causal relationships

Excluded:

- shrubs
- herbs
- fungi
- soil carbon and nutrient cycling
- GIS layers
- named species
- manual fire painting or map drawing
- multi-site comparison

---

## 5. Tree State Model

Each tree must store at least:

- `id`
- `temperament`
- `age`
- `alive`
- `size_class`
- `canopy_role`
- `vigor`
- `suppression_level`
- `reproductive_state`
- `disturbance_damage_state`

### 5.1 Definitions

`age`
- integer or continuous age in years

`size_class`
- abstract structural size indicator used to determine whether a tree is still small, approaching dominance, or fully gap-capable

`canopy_role`
- one of `canopy`, `subcanopy`, `suppressed`

`vigor`
- normalized health/performance indicator

`suppression_level`
- how strongly the tree is limited by closed canopy conditions

`reproductive_state`
- whether the tree is immature, maturing, or reproductively active

`disturbance_damage_state`
- recent damage burden from wind, heat, or fire

### 5.2 Mortality

Trees do not die at a fixed age.

Mortality must be stochastic and driven by:

- background age-related risk
- accumulated stress
- disturbance damage
- suppression history

This means death is probabilistic, not scheduled.

---

## 6. Core Processes

Version 1 simulates six core processes.

### 6.1 Growth

Tree growth depends on:

- temperament
- current vigor
- suppression level
- current heat/drought conditions
- recent disturbance history

Growth outcomes:

- change in size class
- change in vigor
- eventual transition into canopy-capable status for large temperaments

### 6.2 Suppression

Suppression represents canopy closure and limited opportunity.

Suppression affects:

- growth reduction
- vigor decline
- delayed reproduction
- elevated mortality risk

Strugglers tolerate suppression better than gamblers.

### 6.3 Reproduction

Reproduction depends on:

- temperament
- reproductive maturity
- current vigor
- current opportunity state

Gamblers reproduce more aggressively than strugglers.

### 6.4 Recruitment

Recruitment is the process by which new trees enter the stand.

Recruitment probability depends on:

- reproductive output already present in the stand
- current regrowth opportunity
- recent canopy opening
- current heat/drought burden
- temperament-specific recruitment advantage

Gamblers benefit more from openings.
Strugglers persist better when the canopy remains closed.

### 6.5 Gap Creation

A meaningful canopy gap can be created only by the loss of a `large` tree.

Gap creation increases:

- regrowth opportunity
- gambler recruitment success
- short-term growth release for some existing trees

Small-tree mortality does not create the same level of opening.

### 6.6 Turnover

Turnover is the combined effect of:

- mortality
- recruitment
- canopy opening
- replacement through time

Turnover must always be active, even with no major disturbance event.

---

## 7. Disturbance Model

Version 1 includes three disturbances plus baseline turnover.

### 7.1 Fire

Fire is emergent.

It is not directly triggered by a user button in version 1.

Fire probability is influenced by:

- heat
- drought stress
- stand vulnerability state

Fire outcomes can include:

- sudden mortality spike
- canopy opening
- increased turnover
- temporary regrowth opportunity increase

### 7.2 Wind

Wind is driven directly by the `Wind` control.

Wind outcomes can include:

- increased structural failure
- higher mortality for vulnerable trees
- canopy opening when large trees fail
- composition shifts through changed opportunity

### 7.3 Drought / Heat Stress

Drought/heat stress is driven by the `Heat` control and functions as a persistent system pressure.

It affects:

- vigor decline
- growth reduction
- mortality risk
- reproduction success
- fire risk

### 7.4 Baseline Aging and Turnover

Even without a major disturbance event, the forest must still change through:

- stochastic senescence
- stress accumulation
- replacement of individuals over time

---

## 8. User-Facing Controls

Version 1 exposes exactly four live controls.

### 8.1 Heat

Meaning:

- climate pressure
- heat burden
- drought-driving force

Effects:

- raises drought stress
- lowers growth performance
- raises mortality risk
- raises fire risk

### 8.2 Wind

Meaning:

- structural disturbance pressure

Effects:

- raises wind damage
- increases mortality of vulnerable trees
- increases canopy opening if large trees fail

### 8.3 Growth Advantage

Meaning:

- how strongly opportunistic temperaments outperform conservative temperaments under favorable conditions

Effects:

- changes growth-rate differences by temperament
- changes how rapidly opportunity is converted into dominance

### 8.4 Mortality Pressure

Meaning:

- baseline turnover pressure
- background senescence/stress intensity

Effects:

- increases probability of death
- increases replacement opportunity
- changes turnover rate even without dramatic disturbance

### 8.5 Interaction Requirement

The controls must operate live while the simulation is running.

They are not pre-run configuration only.

---

## 9. System Layers

The product must expose three causal layers.

### 9.1 Base Controls

The user changes:

- Heat
- Wind
- Growth Advantage
- Mortality Pressure

### 9.2 Intermediate State

The simulator computes:

- Drought Stress
- Fire Risk
- Growth Rate by Temperament
- Mortality Risk by Temperament
- Regrowth Opportunity

### 9.3 Emergent Outputs

The simulator displays:

- Living Tree Count
- Share by Temperament
- Turnover Rate
- Disturbance Frequency

All displayed outcomes should be traceable back through these layers.

---

## 10. Primary Dashboard Layout

Version 1 is a dashboard-first product.

### 10.1 Center Panel

The center panel is a large composition treemap.

Primary measurement:

- share by `living tree count`

Each block is colored by temperament.

The treemap should make it immediately obvious:

- which role is dominant
- which role is shrinking
- how the forest composition is changing over time

### 10.2 Reserved Future Modes

Do not implement these as primary v1 metrics, but reserve the model to support them later:

- canopy area share
- biomass share

### 10.3 Side Panel

A live node graph shows what is feeding into what.

The graph is not decorative. It is a primary explanatory surface.

### 10.4 Supporting Charts

Required time-series charts:

- living tree count over time
- share by temperament over time
- turnover rate over time
- disturbance frequency over time

### 10.5 Time Controls

Required controls:

- play
- pause
- simulation speed
- reset

The UI should feel continuous to the user even if the engine updates in discrete internal steps.

---

## 11. Node Graph Specification

The graph must stay constrained in version 1.

Target size:

- 10 to 15 nodes

### 11.1 Required Nodes

Base controls:

- Heat
- Wind
- Growth Advantage
- Mortality Pressure

Intermediate state:

- Drought Stress
- Fire Risk
- Growth Rate by Temperament
- Mortality Risk by Temperament
- Regrowth Opportunity

Emergent outputs:

- Living Tree Count
- Share by Temperament
- Turnover Rate
- Disturbance Frequency

### 11.2 Graph Rules

- Every edge must have real model meaning.
- No purely decorative arrows.
- The graph must be readable at a glance.
- Node highlighting should show which variables are currently most active or pressured.

### 11.3 Example Causal Chains

Examples the graph must support:

`Heat -> Drought Stress -> Growth Rate by Temperament -> Mortality Risk by Temperament -> Living Tree Count`

`Heat -> Fire Risk -> Disturbance Frequency -> Regrowth Opportunity -> Share by Temperament`

`Wind -> Disturbance Frequency -> Regrowth Opportunity -> Share by Temperament`

`Mortality Pressure -> Turnover Rate -> Regrowth Opportunity -> Share by Temperament`

---

## 12. Initialization

The simulation starts from an established stand.

This starting stand must already contain:

- all four temperaments
- mixed ages
- mixed canopy roles
- ongoing turnover potential

The user should not start from bare ground.

The dashboard should show a living forest immediately.

---

## 13. Internal Timing

The user-facing simulation is continuous.

Implementation rule:

- the UI may animate continuously
- the engine may update in discrete timesteps

Recommended internal timestep:

- annual for first implementation

Reason:

- keeps the model simpler
- keeps the behavior understandable
- reduces implementation risk
- preserves the continuous feel in the interface

---

## 14. Scientific Accuracy Policy

Version 1 is scientifically inspired and mechanically explicit, but deliberately simplified.

### 14.1 Allowed Simplification

- abstract temperaments instead of named species
- stand-level representation instead of full spatial map
- constrained disturbance model
- normalized state variables such as vigor or suppression

### 14.2 Not Allowed

- invented role behavior with no ecological rationale
- hidden black-box rules that cannot be explained in the dashboard
- fake precision presented as measured fact

### 14.3 Research Required Before Trait Finalization

Before the final implementation of temperament parameters, the project should review literature for:

- gambler vs struggler behavior
- gap-maker dynamics for large trees
- western conifer disturbance ecology
- realistic suppression tolerance patterns
- plausible lifespan and recruitment distributions
- fire and wind disturbance response assumptions

This research is for parameter grounding, not for broadening MVP scope.

---

## 15. Implementation Constraints

The MVP must stay small.

### 15.1 Required Constraint Rules

- no map
- no species list
- no shrubs
- no large geographic landscape
- no calibration pipeline
- no hidden complexity added for realism theater

### 15.2 Product Rule

Every variable exposed in the UI must answer:

1. What is it?
2. What does it affect?
3. Where can I see that effect?

If a variable cannot answer those questions, it should not be in version 1.

---

## 16. Success Criteria

The MVP succeeds if a non-technical user can:

1. understand the four tree roles
2. change the four controls live
3. see forest composition shift over time
4. identify when and why gaps and regrowth are happening
5. trace a major outcome back through the node graph

The MVP fails if it becomes:

- a visually dense ecology control panel with no clarity
- a fake forest app with decorative metrics
- a broad but shallow simulator where no mechanism is legible

---

## 17. Deferred Features

These are explicitly deferred beyond version 1:

- real species mapping onto temperaments
- shrubs and understory
- explicit top-down spatial forest view
- canopy-area and biomass as primary composition measures
- additional temperament classes such as hard gamblers or hard strugglers
- GIS integration
- real site import
- advanced fire spread model
- advanced fuel model
- logging
- insect outbreaks
- hydrology layers

These should not be added until the version 1 system is clear, stable, and explainable.

---

## 18. Final Directive

Build the smallest possible simulator that makes forest succession understandable.

Do not optimize for scope.
Do not optimize for realism theater.
Do not optimize for geospatial complexity.

Optimize for:

- clarity
- legibility
- causal traceability
- distinct temperament behavior
- visible succession under disturbance and turnover

