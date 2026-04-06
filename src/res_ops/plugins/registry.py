"""Plugin registry."""

from .base import PluginBase


class PluginRegistry:
    """插件注册表 (Plugin Registry)."""

    def __init__(self):
        """初始化注册表."""
        self._plugins: dict[str, PluginBase] = {}

    def register(self, plugin: PluginBase) -> None:
        """注册插件."""
        name = plugin.get_name()
        self._plugins[name] = plugin
        plugin.initialize()

    def get_plugin(self, name: str) -> PluginBase | None:
        """获取插件."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[str]:
        """列出所有插件."""
        return list(self._plugins.keys())
