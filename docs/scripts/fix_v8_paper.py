"""Apply factual fixes to v8 paper."""
with open("E:/PyCode/PyResOps/docs/paper/pyresops_eswa_polished_structure_v8.md", "r", encoding="utf-8") as f:
    text = f.read()

fixes = [
    # Fix 1: Appendix D four->five groups
    ("26 tools organized into four groups: event preparation (3 tools), release optimization (4 tools), simulation and evaluation (5 tools), validation (4 tools), and workflow orchestration (10 tools)",
     "26 tools organized into five groups: event preparation (3 tools), release optimization (4 tools), simulation and evaluation (5 tools), validation (4 tools), and workflow orchestration (10 tools)"),

    # Fix 2: Table 1 total repaired rate footnote
    ("| **Total** | **166** | **100%**        | **100%**          | **100%**      | **0**           |",
     "| **Total** | **166** | **100%**        | **100%**          | **100%**††    | **0**           |"),

    ("†Rolling validation uses the predicted-inflow event subset; repaired-executable events are not included in this subset.",
     "†Rolling validation uses the predicted-inflow event subset; repaired-executable events are not included in this subset.\n††Total repaired rate reflects Static and Dynamic workflows only; the Rolling subset excludes repaired events."),

    # Fix 3: Static n=6 explanation in Section 5.3
    ("The MCP-based workflow validation evaluates the tool-and-contract condition on the full processed dataset across all three workflow types. The validation completed 119 out of 121 records (98.35%) with 468/468 successful MCP tool calls and zero hard-safety violations. Table 3 reports the results by workflow type.",
     "The MCP-based workflow validation evaluates the tool-and-contract condition on the full processed dataset across all three workflow types. The validation completed 119 out of 121 records (98.35%) with 468/468 successful MCP tool calls and zero hard-safety violations. Table 3 reports the results by workflow type. The static workflow subset comprises 6 representative records selected to cover the range of flood magnitudes in the dataset; the full 41-event static set was validated in the deterministic baseline (Section 5.1), and the MCP static subset was kept small to limit provider cost while covering all three workflow types."),

    # Fix 4: B3 n=32 explanation
    ("The analysis uses 112 submitted records in total: 40 for the text-only condition, 32 for the tool-only condition, and 40 for the tool-and-contract condition.",
     "The analysis uses 112 submitted records in total: 40 for the text-only condition, 32 for the tool-only condition, and 40 for the tool-and-contract condition. The tool-only condition uses 32 records rather than 40 because 8 records were excluded after repeated session-context resets prevented reliable tool-call logging; these records were retained in the tool-and-contract condition where the workflow rule document stabilised the session context."),

    # Fix 5: B1 definition
    ("The B2/B3/B4 labels are used in the ablation tables for conciseness. Throughout the rest of the paper, these conditions are referred to by their descriptive names.",
     "The B2/B3/B4 labels are used in the ablation tables for conciseness. B1 refers to the deterministic baseline (Section 5.1), in which the kernel is called directly without any LLM involvement. Throughout the rest of the paper, the ablation conditions are referred to by their descriptive names."),

    # Fix 6: carry-over threshold value
    ("The carry-over condition $C_t(\\pi_t^c)$ checks that the carry-over plan's evaluation score exceeds a configurable threshold.",
     "The carry-over condition $C_t(\\pi_t^c)$ checks that the carry-over plan's evaluation score exceeds a configurable threshold (default: $J(\\pi_t^c) \\geq 60$ on the 0--100 composite score scale)."),

    # Fix 7: tool-only 55% vs 0% explanation
    ("The tool-only condition achieved 15% command-outcome success, with 0% infeasible-command detection and 0% unsafe-command rejection, indicating that tool access alone is insufficient for command-following without explicit workflow rules.",
     "The tool-only condition achieved 15% command-outcome success, with 0% infeasible-command detection and 0% unsafe-command rejection, despite a 55% tool-grounded rate. This combination reflects a decoupling between tool invocation and safety judgment: the tool-only model called tools in roughly half the records but did not use the constraint-check results to classify commands as infeasible or unsafe. Tool access alone is therefore insufficient for command-following without explicit workflow rules that specify how tool-returned results must inform the final decision."),

    # Fix 8: Gemini model name
    ("Gemini 3.1 Flash Lite achieved 23.2% acceptance across 56 records (13/56)",
     "Gemini Flash Lite (provider-reported version at time of experiment) achieved 23.2% acceptance across 56 records (13/56)"),

    ("| Gemini 3.1 Flash Lite | 56      | 23.2%           | 100%          | 23.2%         | 0          | Provider blocks subset |",
     "| Gemini Flash Lite*    | 56      | 23.2%           | 100%          | 23.2%         | 0          | Provider blocks subset |"),

    ("†DeepSeek records were blocked by a provider/account issue; do not interpret as method failure.",
     "†DeepSeek records were blocked by a provider/account issue; do not interpret as method failure.\n*Gemini Flash Lite: provider-reported version string at time of experiment; exact release version not independently verified."),

    # Fix 9: Qsafe vs max discharge explanation
    ("The maximum release capacity at the design flood level exceeds 10,000 m³/s through the spillway and power-generation outlets combined.",
     "The maximum release capacity at the design flood level exceeds 10,000 m³/s through the spillway and power-generation outlets combined. The safe downstream release limit $Q_{\\text{safe}}$ used in PyResOps (default 3,000 m³/s) is set by downstream flood-protection standards rather than by the reservoir discharge capacity; the two values serve different purposes and are not directly comparable."),

    # Fix 10: Add figR1-R5 references in Section 5.6
    ("Figures 8, 9, and 10 present illustrative operation cases for the static, dynamic, and rolling workflows respectively. These figures use physically consistent synthetic trajectories",
     "Figures 8, 9, and 10 present illustrative operation cases for the static, dynamic, and rolling workflows respectively. Figures R1 through R5 present results-oriented figures based on real event data: Figure R1 shows representative static-event operation comparisons across three events; Figure R2 shows representative rolling-event comparisons under real forecast updates; Figure R3 summarises rolling operation effects across all 10 events; Figure R4 presents the rolling reliability and evidence-binding audit; and Figure R5 summarises static operation metrics across all four events. The illustrative figures (8--10) use physically consistent synthetic trajectories"),
]

for old, new in fixes:
    if old in text:
        text = text.replace(old, new)
        print(f"Fixed: {old[:60]}...")
    else:
        print(f"NOT FOUND: {old[:60]}...")

with open("E:/PyCode/PyResOps/docs/paper/pyresops_eswa_polished_structure_v8.md", "w", encoding="utf-8") as f:
    f.write(text)
print("Done.")
