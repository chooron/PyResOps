"""Plugin base class."""

from abc import ABC, abstractmethod


class PluginBase(ABC):
    """插件基类 (Plugin Base Class)."""

    @abstractmethod
    def initialize(self) -> None:
        """初始化插件."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """获取插件名称."""
        pass
