from kairon.exceptions import AppException
from kairon.shared.constants import PluginTypes
from kairon.shared.plugins.gpt import Gpt
from kairon.shared.plugins.ipinfo import IpInfoTracker


class PluginFactory:

    __plugins = {
        PluginTypes.ip_info: IpInfoTracker,
        PluginTypes.gpt: Gpt
    }

    @staticmethod
    def get_instance(plugin_type: PluginTypes):
        """
        Factory to retrieve implementation of plugins

        :param plugin_type: valid plugin type
        """
        if plugin_type not in PluginFactory.__plugins.keys():
            valid_plugins = [plugin for plugin in PluginTypes]
            raise AppException(f"{plugin_type} is not a valid event. Accepted event types: {valid_plugins}")
        return PluginFactory.__plugins[plugin_type]()
