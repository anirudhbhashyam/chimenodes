"""chimenodes: MolecularNodes-style rendering and glow for ChimeraX.

Package ``chimerax.chimenodes``. The bundle API only delegates; every delegation is guarded
so a problem in one module (command, tool, state) never prevents ChimeraX from starting.
"""
from __future__ import annotations

__version__ = "1.0.6"

try:
    from chimerax.core.toolshed import BundleAPI
except ImportError:  # plain CPython (unit tests import sibling modules only)
    class BundleAPI(object):  # type: ignore
        pass


class _MyAPI(BundleAPI):
    api_version = 1

    _commands_registered = False

    @staticmethod
    def initialize(session, bundle_info):
        """Called once at startup (customInit): register session state, never raise."""
        try:
            from . import state
            state.register_state(session)
        except Exception as e:
            _warn(session, "state registration failed (%s)" % e)

    @staticmethod
    def finish(session, bundle_info):
        """Called when the bundle is unloaded: restore stock rendering."""
        try:
            from . import hook
            hook.uninstall(session)
        except Exception:
            pass

    @staticmethod
    def register_command(bundle_info, command_info, logger):
        if _MyAPI._commands_registered:
            return
        try:
            from . import cmd
            cmd.register_commands(logger)
            _MyAPI._commands_registered = True
        except Exception as e:
            try:
                logger.warning("chimenodes: could not register commands (%s)" % e)
            except Exception:
                pass

    @staticmethod
    def start_tool(session, bundle_info, tool_info):
        try:
            from . import tool
            return tool.show_tool(session)
        except Exception as e:
            _warn(session, "panel unavailable (%s)" % e)
            return None

    @staticmethod
    def get_class(class_name):
        return None


def _warn(session, msg):
    try:
        session.logger.warning("chimenodes: " + msg)
    except Exception:
        pass


bundle_api = _MyAPI()
