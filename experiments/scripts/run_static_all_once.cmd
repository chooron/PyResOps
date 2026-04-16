@echo off
REM ============================================================
REM 静态场景批量执行脚本（S01~S05）
REM 含义：仅运行静态基线，不运行动态阶段；用于快速验证静态链路。
REM 模型：deepseek（来自 experiments/config/llm_config.yml 的 profile）
REM 输出：experiments/results/static/*.json + scenario_runs_*_static_*.json
REM ============================================================

setlocal

uv run python experiments/run_scenario_experiment.py --scenario ALL --mode static --model deepseek

if errorlevel 1 (
  echo.
  echo [FAILED] 静态场景执行失败，请检查日志与 .env 配置。
  exit /b 1
)

echo.
echo [OK] 静态场景已执行完成。
exit /b 0
