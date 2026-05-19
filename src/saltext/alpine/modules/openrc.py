"""
Support for OpenRC on Alpine Linux

.. important::
    If you feel that Salt should be using this module to manage services on a
    minion, and it is using a different module (or gives an error similar to
    *'service.start' is not available*), see :ref:`here
    <module-provider-override>`.

"""

import logging

from salt.exceptions import CommandExecutionError

log = logging.getLogger(__name__)

__virtualname__ = "service"

# The runlevel used by default for enable/disable operations.
# Alpine systems use 'default' for services that should start at boot.
_DEFAULT_RUNLEVEL = "default"


def __virtual__():
    """
    Only load on Alpine Linux systems with OpenRC present.
    """
    if __grains__.get("os_family", False) != "Alpine":
        return (False, "Module openrc only works on Alpine Linux based systems")
    return __virtualname__


def _run(cmd):
    """
    Run a command list and return the full result dict from cmd.run_all.
    """
    return __salt__["cmd.run_all"](cmd, python_shell=False)


def start(name, **_):
    """
    Start the named service.

    CLI Example:

    .. code-block:: bash

        salt '*' service.start <service name>
    """
    ret = _run(["rc-service", name, "start"])
    return ret["retcode"] == 0


def stop(name, **_):
    """
    Stop the named service.

    CLI Example:

    .. code-block:: bash

        salt '*' service.stop <service name>
    """
    ret = _run(["rc-service", name, "stop"])
    return ret["retcode"] == 0


def restart(name, **_):
    """
    Restart the named service.

    CLI Example:

    .. code-block:: bash

        salt '*' service.restart <service name>
    """
    ret = _run(["rc-service", name, "restart"])
    return ret["retcode"] == 0


def reload_(name, **_):
    """
    Send a reload signal to the named service. Not all services support
    reload; consult the service's init script to confirm.

    CLI Example:

    .. code-block:: bash

        salt '*' service.reload <service name>
    """
    ret = _run(["rc-service", name, "reload"])
    return ret["retcode"] == 0


def status(name, sig=None, **_):  # pylint: disable=unused-argument
    """
    Return True if the named service is running, False otherwise.

    The sig parameter is accepted for interface compatibility with Salt's
    generic service state but is not used; rc-service status is authoritative.

    CLI Example:

    .. code-block:: bash

        salt '*' service.status <service name>
    """
    ret = _run(["rc-service", name, "status"])
    return ret["retcode"] == 0


def enabled(name, runlevel=None, **_):
    """
    Return True if the named service is enabled in the given runlevel.

    runlevel
        The runlevel to check. Defaults to 'default'.

    CLI Example:

    .. code-block:: bash

        salt '*' service.enabled <service name>
        salt '*' service.enabled <service name> runlevel=boot
    """
    runlevel = runlevel or _DEFAULT_RUNLEVEL
    return name in get_enabled(runlevel=runlevel)


def disabled(name, **kwargs):
    """
    Return True if the named service is disabled in the default runlevel.

    CLI Example:

    .. code-block:: bash

        salt '*' service.disabled <service name>
    """
    return not enabled(name, **kwargs)


def enable(name, runlevel=None, **_):
    """
    Enable the named service in the given runlevel so it starts at boot.

    runlevel
        The runlevel to add the service to. Defaults to 'default'.

    CLI Example:

    .. code-block:: bash

        salt '*' service.enable <service name>
        salt '*' service.enable <service name> runlevel=boot
    """
    runlevel = runlevel or _DEFAULT_RUNLEVEL
    ret = _run(["rc-update", "add", name, runlevel])
    return ret["retcode"] == 0


def disable(name, runlevel=None, **_):
    """
    Disable the named service in the given runlevel.

    runlevel
        The runlevel to remove the service from. Defaults to 'default'.

    CLI Example:

    .. code-block:: bash

        salt '*' service.disable <service name>
        salt '*' service.disable <service name> runlevel=boot
    """
    runlevel = runlevel or _DEFAULT_RUNLEVEL
    ret = _run(["rc-update", "del", name, runlevel])
    return ret["retcode"] == 0


def available(name, **_):
    """
    Return True if the named service exists on the system.

    CLI Example:

    .. code-block:: bash

        salt '*' service.available <service name>
    """
    return name in get_all()


def missing(name, **_):
    """
    Return True if the named service is not available on the system.

    CLI Example:

    .. code-block:: bash

        salt '*' service.missing <service name>
    """
    return not available(name)


def get_all(**_):
    """
    Return a sorted list of all services known to rc-service.

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_all
    """
    ret = _run(["rc-service", "--list"])
    if ret["retcode"] != 0:
        raise CommandExecutionError(
            "Failed to list services",
            info={"stderr": ret.get("stderr", ""), "stdout": ret.get("stdout", "")},
        )
    return sorted(line.strip() for line in ret["stdout"].splitlines() if line.strip())


def get_enabled(runlevel=None, **_):
    """
    Return a sorted list of services enabled in the given runlevel.

    runlevel
        The runlevel to query. Defaults to 'default'.

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_enabled
        salt '*' service.get_enabled runlevel=boot
    """
    runlevel = runlevel or _DEFAULT_RUNLEVEL
    ret = _run(["rc-update", "show", runlevel])
    if ret["retcode"] != 0:
        raise CommandExecutionError(
            f"Failed to list enabled services for runlevel '{runlevel}'",
            info={"stderr": ret.get("stderr", ""), "stdout": ret.get("stdout", "")},
        )
    # Each output line is of the form "    sshd | default"
    # Lines from rc-update that are not service entries (status messages)
    # do not contain the pipe character, so we filter on that.
    result = []
    for line in ret["stdout"].splitlines():
        if "|" not in line:
            continue
        svc = line.split("|")[0].strip()
        if svc:
            result.append(svc)
    return sorted(result)


def get_running(**_):
    """
    Return a sorted list of services that are currently started.

    CLI Example:

    .. code-block:: bash

        salt '*' service.get_running
    """
    # rc-status -a shows services across all runlevels with their status.
    # Service lines look like:
    #  " sshd                                                   [  started  ]"
    # Runlevel header lines look like:
    #  "Runlevel: default" or "Dynamic Runlevel: hotplugged"
    # We filter for lines that contain "started" and begin with whitespace,
    # which excludes headers and blank lines.
    ret = _run(["rc-status", "--nocolor", "-a"])
    if ret["retcode"] != 0:
        raise CommandExecutionError(
            "Failed to query running services",
            info={"stderr": ret.get("stderr", ""), "stdout": ret.get("stdout", "")},
        )
    result = []
    for line in ret["stdout"].splitlines():
        if line and line[0] == " " and "started" in line:
            svc = line.strip().split()[0]
            result.append(svc)
    return sorted(result)
