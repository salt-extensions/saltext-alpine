"""
Reboot, shutdown, poweroff, and halt support for Alpine Linux.
"""

import logging

from salt.modules import system as _system

log = logging.getLogger(__name__)

__virtualname__ = "system"

_OVERRIDDEN = ("reboot", "poweroff", "halt", "shutdown")


def __virtual__():
    """
    Confirm this module is running on Alpine Linux
    """
    if __grains__.get("os_family", False) == "Alpine":
        return __virtualname__
    return (False, "Module system (alpine) only works on Alpine Linux based systems")


def _delay_flag(at_time):
    """
    Translate the core module's ``at_time`` (a delay in minutes) into the
    BusyBox ``-d <seconds>`` flag. Returns an empty list when no delay is
    requested, so the applet runs immediately.
    """
    if at_time in (None, "", 0, "0"):
        return []
    try:
        minutes = int(at_time)
    except (TypeError, ValueError):
        log.warning("Ignoring non-numeric at_time value: %r", at_time)
        return []
    return ["-d", str(minutes * 60)]


def reboot(at_time=None):
    """
    Reboot the system using the BusyBox ``reboot`` applet.

    at_time
        Delay in minutes before rebooting. Converted to a BusyBox ``-d`` delay
        in seconds; the minion blocks for the delay.

    CLI Example:

    .. code-block:: bash

        salt '*' system.reboot
        salt '*' system.reboot 5
    """
    cmd = ["reboot"] + _delay_flag(at_time)
    return __salt__["cmd.run"](cmd, python_shell=False)


def poweroff():
    """
    Power off the system using the BusyBox ``poweroff`` applet.

    CLI Example:

    .. code-block:: bash

        salt '*' system.poweroff
    """
    return __salt__["cmd.run"](["poweroff"], python_shell=False)


def halt():
    """
    Halt the system using the BusyBox ``halt`` applet.

    CLI Example:

    .. code-block:: bash

        salt '*' system.halt
    """
    return __salt__["cmd.run"](["halt"], python_shell=False)


def shutdown(at_time=None):
    """
    Shut the system down (power off) using the BusyBox ``poweroff`` applet.

    at_time
        Delay in minutes before shutting down. Converted to a BusyBox ``-d``
        delay in seconds; the minion blocks for the delay.

    CLI Example:

    .. code-block:: bash

        salt '*' system.shutdown
        salt '*' system.shutdown 5
    """
    cmd = ["poweroff"] + _delay_flag(at_time)
    return __salt__["cmd.run"](cmd, python_shell=False)


def _reexport_core_functions():
    """
    Re-export every other ``system.*`` function from the core module unchanged.

    Shipping this file under the ``system`` name replaces the whole core module
    in the loader's ``system`` slot, so without this the remaining functions
    (``get_computer_name``, ``set_system_time``, ``init``, and the rest) would
    disappear on Alpine. The original function objects are bound by reference so
    they keep their own module globals, which means their private helpers and
    loader dunders continue to resolve against the core module.
    """
    for name, obj in vars(_system).items():
        if name.startswith("_") or name in _OVERRIDDEN:
            continue
        if not callable(obj):
            continue
        if getattr(obj, "__module__", None) != _system.__name__:
            continue
        globals()[name] = obj


_reexport_core_functions()
del _reexport_core_functions
