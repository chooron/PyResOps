"""Forecast data structures."""

from datetime import datetime

import pandas as pd
from pydantic import BaseModel, Field


class ForecastSeries(BaseModel):
    """单变量预报序列 (Single-variable Forecast Series)."""

    variable: str = Field(description="变量名称 (如 'inflow', 'rainfall')")
    timestamps: list[datetime] = Field(description="时间戳序列")
    values: list[float] = Field(description="预报值序列")
    unit: str = Field(default="", description="单位")

    def to_dataframe(self) -> pd.DataFrame:
        """转换为 Pandas DataFrame."""
        return pd.DataFrame({"timestamp": self.timestamps, self.variable: self.values})


class ForecastBundle(BaseModel):
    """预报数据包 (Forecast Bundle)."""

    forecast_time: datetime = Field(description="预报发布时间")
    series: list[ForecastSeries] = Field(description="预报序列列表")
    metadata: dict[str, str] = Field(default_factory=dict)

    def get_series(self, variable: str) -> ForecastSeries | None:
        """根据变量名获取预报序列."""
        for s in self.series:
            if s.variable == variable:
                return s
        return None

    def to_dataframe(self) -> pd.DataFrame:
        """转换为统一的 DataFrame."""
        if not self.series:
            return pd.DataFrame()

        dfs = [s.to_dataframe().set_index("timestamp") for s in self.series]
        return pd.concat(dfs, axis=1).reset_index()
