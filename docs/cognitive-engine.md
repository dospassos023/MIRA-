# MIRA Cognitive Engine v1

The cognitive engine is a deterministic orchestration layer around existing Mira memory, policy, and provider adapters. It does not give model text access to tools or authority. The existing `authorized()` gate remains the enforcement point; approvals must come from trusted host code and match an exact operation.

## Separation of concerns

`persona.json` holds Mira's expression identity and fictional age (32). `policy.py` and `cognitive.py` hold rules for evidence, risk, permissions, outcomes, and feedback. Persona language cannot grant permissions.

The evidence ledger stores claim text, source references, status, and a confidence value supplied by the caller. This is provenance metadata, not calibrated probability. `assess()` marks uncertainty and conflicting statuses; it does not decide which scientific claim is true. Existing owner controlled memory continues to handle profile facts, temporal validity, pending contradictions, review, and deletion.

Task runs preserve a plan and state. Safe actions can proceed; consequential actions without a trusted, exact approval escalate. A successful response from an executor is insufficient: `observed=True` is required to report verification. Failed verification triggers best-effort rollback when the adapter returned a rollback token. Feedback attaches to a run as a record for later review; it does not silently modify model weights or confirmed memory.

## Research rationale and limits

- ReAct connects reasoning, actions, and environmental observations: [Yao et al. (2023)](https://arxiv.org/abs/2210.03629). Mira uses an observe-before-claim outcome contract.
- Generative Agents use memory retrieval, reflection, and planning: [Park et al. (2023)](https://doi.org/10.1145/3586183.3606763). Mira retains her current versioned memory and adds run-level feedback.
- Reflexion studies verbal feedback in iterative agents: [Shinn et al. (2023)](https://papers.nips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html). Mira records feedback without treating self-reflection as external verification.
- Self-RAG studies selective retrieval and critique: [Asai et al. (2024)](https://proceedings.iclr.cc/paper_files/paper/2024/hash/25f7be9694d7b32d5cc670927b8091e1-Abstract-Conference.html). Mira's source-linked ledger supports review, but no retrieval ranking is claimed here.
- Metareasoning formalizes the value and cost of further computation: [Russell & Wefald (1991)](https://doi.org/10.1016/0004-3702(91)90015-C). High risk or irreversibility inserts an assessment step; thresholds are engineering choices, not learned/calibrated.
- Language model confidence can be unreliable: [Jiang et al. (2021)](https://doi.org/10.1162/tacl_a_00407). Ledger confidence must not be interpreted as calibrated probability.
- Risk management and governance: [NIST AI RMF Generative AI Profile (2024)](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence).

These papers motivate components; they do not validate this combined system. Current orchestration is a local API for embedding in an application. No Linda OS connection or action adapter is present or verified. The executor protocol is an integration seam only.
