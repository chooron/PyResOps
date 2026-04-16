@echo off
REM ============================================================
REM 静态场景单例执行脚本（S01）
REM 含义：仅跑一个场景的静态基线，适合调试与快速冒烟验证。
REM 模型：deepseek
REM ============================================================

setlocal

uv run python experiments/run_scenario_experiment.py --scenario S01 --mode static --model deepseek

if errorlevel 1 (
  echo.
  echo [FAILED] S01 静态场景执行失败。
  exit /b 1
)

echo.
echo [OK] S01 静态场景已执行完成。
exit /b 0
