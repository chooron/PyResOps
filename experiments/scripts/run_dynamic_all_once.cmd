@echo off
REM ============================================================
REM 动态场景批量执行脚本（S01~S05）
REM 含义：仅运行动态阶段，不运行静态基线；rounds=0 表示执行每个场景全部触发阶段。
REM 模型：deepseek（来自 experiments/config/llm_config.yml 的 profile）
REM 输出：experiments/results/dynamic/*_stages.json + scenario_runs_*_dynamic_*.json
REM ============================================================

setlocal

uv run python experiments/run_scenario_experiment.py --scenario ALL --mode dynamic --model deepseek --rounds 0

if errorlevel 1 (
  echo.
  echo [FAILED] 动态场景执行失败，请检查日志与 .env 配置。
  exit /b 1
)

echo.
echo [OK] 动态场景已执行完成。
exit /b 0
