@echo off
REM ============================================================
REM 动态场景单例执行脚本（S01）
REM 含义：仅跑一个场景的动态实验；rounds=0 表示执行该场景全部动态阶段。
REM 模型：deepseek
REM ============================================================

setlocal

uv run python experiments/run_scenario_experiment.py --scenario S01 --mode dynamic --model deepseek --rounds 0

if errorlevel 1 (
  echo.
  echo [FAILED] S01 动态场景执行失败。
  exit /b 1
)

echo.
echo [OK] S01 动态场景已执行完成。
exit /b 0
