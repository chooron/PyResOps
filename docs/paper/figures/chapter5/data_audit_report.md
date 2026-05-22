# Chapter 5 Data Audit Report

## Result Files Read
- `data/processed/flood_event/2010062002.csv` exists=yes
- `data/processed/flood_event/2019071011.csv` exists=yes
- `data/processed/flood_event/2024061517.csv` exists=yes
- `data/processed/flood_event/2024061623.csv` exists=yes
- `docs/chapter5_results_codex_outline_prompt.md` exists=yes
- `docs/paper/figures/chapter5/tables/table5_2_static_results.csv` exists=yes
- `docs/paper/figures/chapter5/tables/table5_3_dynamic_results.csv` exists=yes
- `docs/paper/figures/chapter5/tables/table5_4_rolling_results.csv` exists=yes
- `docs/paper/figures/chapter5/tables/table5_5_ablation_results.csv` exists=yes
- `experiments/results/paper_ready/operation_effect_figures/rolling_event_timeseries_all.csv` exists=yes
- `experiments/results/paper_validation/component-ablation_20260509_041755_523620.jsonl` exists=yes
- `experiments/results/paper_validation/tables/ablation_b2_b3_b4_summary.csv` exists=yes
- `experiments/results/paper_validation/tables/ablation_success_semantics_summary.csv` exists=yes
- `experiments/results/stage1/STAGE1_SUMMARY.md` exists=yes
- `experiments/results/stage1/dynamic/stage_results.csv` exists=yes
- `experiments/results/stage1/rolling/stage_results.csv` exists=yes
- `experiments/results/stage1/static/all_events_metrics.csv` exists=yes
- `experiments/results/stage1_dynamic_command_intervention/results.csv` exists=yes
- `experiments/results/stage1_instruction_static/results.csv` exists=yes
- `experiments/results/stage2/STAGE2_SUMMARY.md` exists=yes
- `experiments/results/stage2_dynamic_command_intervention/summary/dynamic_command_stage2_metrics.json` exists=yes
- `experiments/results/stage2_instruction_static/STAGE2_INSTRUCTION_STATIC_SUMMARY.md` exists=yes
- `experiments/results/stage3/rolling/results.csv` exists=yes
- `experiments/results/stage3_claude_haiku_4_5/rolling/results.csv` exists=yes
- `experiments/results/stage3_dynamic_command_claude/results.csv` exists=yes
- `experiments/results/stage3_dynamic_command_claude/summary/dynamic_command_stage3_metrics.json` exists=yes
- `experiments/results/stage3_dynamic_command_mimo/results.csv` exists=yes
- `experiments/results/stage3_dynamic_command_mimo/summary/dynamic_command_stage3_metrics.json` exists=yes
- `experiments/results/stage3_dynamic_command_mimo/summary/failure_taxonomy.csv` exists=yes
- `experiments/results/stage3_dynamic_command_minimax/results.csv` exists=yes
- `experiments/results/stage3_dynamic_command_minimax/summary/dynamic_command_stage3_metrics.json` exists=yes
- `experiments/results/stage3_dynamic_command_minimax/summary/failure_taxonomy.csv` exists=yes
- `experiments/results/stage3_instruction_static_combined/cross_model_summary.csv` exists=yes
- `experiments/results/stage3_mimo_v25/rolling/results.csv` exists=yes

## Table Sources
- `table5_0_workflow_pseudocode.csv`: `docs/chapter5_results_codex_outline_prompt.md`; `experiments/results/stage1_instruction_static/results.csv`; `experiments/results/stage1_dynamic_command_intervention/results.csv`; `experiments/results/stage1/rolling/stage_results.csv`
- `table5_1_scenario_coverage.csv`: `experiments/results/stage1/STAGE1_SUMMARY.md`; `experiments/results/stage2/STAGE2_SUMMARY.md`; `experiments/results/stage3_instruction_static_combined/cross_model_summary.csv`
- `table5_2_static_results.csv`: `experiments/results/stage1/static/all_events_metrics.csv`; `experiments/results/stage1_instruction_static/results.csv`; `experiments/results/stage2_instruction_static/STAGE2_INSTRUCTION_STATIC_SUMMARY.md`; `experiments/results/stage3_instruction_static_combined/cross_model_summary.csv`
- `table5_3_dynamic_results.csv`: `experiments/results/stage1_dynamic_command_intervention/results.csv`; `experiments/results/stage2_dynamic_command_intervention/summary/dynamic_command_stage2_metrics.json`; `experiments/results/stage3_dynamic_command_mimo/summary/dynamic_command_stage3_metrics.json`; `experiments/results/stage3_dynamic_command_claude/summary/dynamic_command_stage3_metrics.json`; `experiments/results/stage3_dynamic_command_minimax/summary/dynamic_command_stage3_metrics.json`
- `table5_4_rolling_results.csv`: `experiments/results/stage3/rolling/results.csv`; `experiments/results/stage3_mimo_v25/rolling/results.csv`; `experiments/results/stage3_claude_haiku_4_5/rolling/results.csv`
- `table5_5_ablation_results.csv`: `experiments/results/paper_validation/tables/ablation_success_semantics_summary.csv`; `experiments/results/paper_validation/tables/ablation_b2_b3_b4_summary.csv`; `experiments/results/paper_validation/component-ablation_20260509_041755_523620.jsonl`

## Figure Sources
- `fig5_1_static_extension_scenarios`: `experiments/results/stage1_instruction_static/results.csv`; `data/processed/flood_event/2024061623.csv`; `data/processed/flood_event/2010062002.csv`; `data/processed/flood_event/2024061517.csv`; `data/processed/flood_event/2019071011.csv`
- `fig5_2_static_result_evaluation`: `docs/paper/figures/chapter5/tables/table5_2_static_results.csv`
- `fig5_3_dynamic_command_scenarios`: `experiments/results/stage1_dynamic_command_intervention/results.csv`; `data/processed/flood_event/2024061623.csv`
- `fig5_4_dynamic_result_evaluation`: `docs/paper/figures/chapter5/tables/table5_3_dynamic_results.csv`
- `fig5_5_rolling_operation_scenarios`: `experiments/results/paper_ready/operation_effect_figures/rolling_event_timeseries_all.csv`; `experiments/results/stage1/rolling/stage_results.csv`
- `fig5_6_rolling_result_evaluation`: `experiments/results/stage1/rolling/stage_results.csv`; `docs/paper/figures/chapter5/tables/table5_4_rolling_results.csv`
- `fig5_7_ablation_result_evaluation`: `docs/paper/figures/chapter5/tables/table5_5_ablation_results.csv`; `experiments/results/paper_validation/component-ablation_20260509_041755_523620.jsonl`

## Missing Values
- Ablation result tables and raw component-ablation JSONL do not expose downstream_violation/downstream_violations/routing_violation/hecheng_violation fields; table5_5 marks downstream as not evaluated.

## Mismatches Against Known Logs
- None detected by script assertions.

## Manual Confirmation Items
- Static-extension trajectory JSON files contain summary stubs, so Figure 5.1 combines observed inflow series with frozen instruction-static release-family peak releases rather than reconstructed full release trajectories.
