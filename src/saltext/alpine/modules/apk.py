"""
Package management for Alpine Linux via ``apk``.

This module registers under Salt's ``pkg`` virtual name and is loaded
automatically on Alpine minions. Existing states such as ``pkg.installed``
and ``pkg.removed`` work without any changes to your state files.

.. important::
    If Salt is not using this module on an Alpine minion (or you see an error
    such as *'pkg.install' is not available*), see :ref:`here
    <module-provider-override>`.

Version strings
---------------

Alpine packages follow the ``version-revision`` convention, for example
``3.3.2-r0``. This is what :py:func:`list_pkgs`, :py:func:`version`, and
related functions return.

Hyphenated package names such as ``py3-requests`` and ``ca-certificates``
are handled correctly throughout. The module identifies the boundary between
name and version by locating the first dash-separated component that begins
with a digit.

Known limitations
-----------------

- Installing a specific package version is not yet supported. The version
  component of any ``pkgs`` dict entry is accepted but silently ignored.
- Package hold and pin operations are not yet implemented.
- Repository management (adding, removing, or listing ``/etc/apk/repositories``
  entries) is not yet implemented.
"""

import copy
import logging

import salt.utils.data
import salt.utils.itertools
from salt.exceptions import CommandExecutionError

log = logging.getLogger(__name__)

# Define the module's virtual name
__virtualname__ = "pkg"


def __virtual__():
    """
    Confirm this module is running on an Alpine Linux distribution
    """
    if __grains__.get("os_family", False) == "Alpine":
        return __virtualname__
    return (False, "Module apk only works on Alpine Linux based systems")


# def autoremove(list_only=False, purge=False):
#    return 'Not available'
# def hold(name=None, pkgs=None, sources=None, **kwargs):  # pylint: disable=W0613
#    return 'Not available'
# def unhold(name=None, pkgs=None, sources=None, **kwargs):  # pylint: disable=W0613
#    return 'Not available'
# def upgrade_available(name):
#    return 'Not available'
# def version_cmp(pkg1, pkg2, ignore_epoch=False):
#    return 'Not available'
# def list_repos():
#    return 'Not available'
# def get_repo(repo, **kwargs):
#    return 'Not available'
# def del_repo(repo, **kwargs):
#    return 'Not available'
# def del_repo_key(name=None, **kwargs):
#    return 'Not available'
# def mod_repo(repo, saltenv='base', **kwargs):
#    return 'Not available'
# def expand_repo_def(**kwargs):
#    return 'Not available'
# def get_selections(pattern=None, state=None):
#    return 'Not available'
# def set_selections(path=None, selection=None, clear=False, saltenv='base'):
#    return 'Not available'
# def info_installed(*names):
#    return 'Not available'


def version(*names, **kwargs):
    """
    Returns a string representing the package version or an empty string if not
    installed. If more than one package name is specified, a dict of
    name/version pairs is returned.

    CLI Example:

    .. code-block:: bash

        salt '*' pkg.version <package name>
        salt '*' pkg.version <package1> <package2> <package3> ...
    """
    return __salt__["pkg_resource.version"](*names, **kwargs)


def refresh_db(**kwargs):
    """
    Updates the package list

    - ``True``: Database updated successfully
    - ``False``: Problem updating database

    CLI Example:

    .. code-block:: bash

        salt '*' pkg.refresh_db
    """
    ret = {}
    cmd = ["apk", "update"]
    call = __salt__["cmd.run_all"](cmd, output_loglevel="trace", python_shell=False)
    if call["retcode"] == 0:
        errors = []
        ret = True
    else:
        errors = [call["stdout"]]
        ret = False

    if errors:
        raise CommandExecutionError(
            "Problem encountered updating the package database",
            info={"errors": errors, "changes": ret},
        )

    return ret


def _list_pkgs_from_context(versions_as_list):
    """
    Use pkg list from __context__
    """
    if versions_as_list:
        return __context__["pkg.list_pkgs"]
    ret = copy.deepcopy(__context__["pkg.list_pkgs"])
    __salt__["pkg_resource.stringify"](ret)
    return ret


def list_pkgs(versions_as_list=False, **kwargs):
    """
    List the packages currently installed in a dict::

        {'<package_name>': '<version>'}

    CLI Example:

    .. code-block:: bash

        salt '*' pkg.list_pkgs
        salt '*' pkg.list_pkgs versions_as_list=True
    """
    versions_as_list = salt.utils.data.is_true(versions_as_list)
    # not yet implemented or not applicable
    if any(salt.utils.data.is_true(kwargs.get(x)) for x in ("removed", "purge_desired")):
        return {}

    if "pkg.list_pkgs" in __context__ and kwargs.get("use_context", True):
        return _list_pkgs_from_context(versions_as_list)

    cmd = ["apk", "info", "-v"]
    ret = {}
    out = __salt__["cmd.run"](cmd, output_loglevel="trace", python_shell=False)
    for line in salt.utils.itertools.split(out, "\n"):
        pkg_version = "-".join(line.split("-")[-2:])
        pkg_name = "-".join(line.split("-")[:-2])
        __salt__["pkg_resource.add_pkg"](ret, pkg_name, pkg_version)

    __salt__["pkg_resource.sort_pkglist"](ret)
    __context__["pkg.list_pkgs"] = copy.deepcopy(ret)
    if not versions_as_list:
        __salt__["pkg_resource.stringify"](ret)
    return ret


def latest_version(*names, **kwargs):
    """
    Return the latest version of the named package available for upgrade or
    installation. If more than one package name is specified, a dict of
    name/version pairs is returned.

    If the latest version of a given package is already installed, an empty
    string will be returned for that package.

    CLI Example:

    .. code-block:: bash

        salt '*' pkg.latest_version <package name>
        salt '*' pkg.latest_version <package name>
        salt '*' pkg.latest_version <package1> <package2> <package3> ...
    """
    refresh = salt.utils.data.is_true(kwargs.pop("refresh", True))

    if not names:
        return ""

    ret = {}
    for name in names:
        ret[name] = ""
    pkgs = list_pkgs()

    # Refresh before looking for the latest version available
    if refresh:
        refresh_db()

    # Upgrade check
    cmd = ["apk", "upgrade", "-s"]
    out = __salt__["cmd.run_stdout"](cmd, output_loglevel="trace", python_shell=False)
    for line in salt.utils.itertools.split(out, "\n"):
        try:
            name = line.split(" ")[2]
            _oldversion = line.split(" ")[3].strip("(")
            newversion = line.split(" ")[5].strip(")")
            if name in names:
                ret[name] = newversion
        except (ValueError, IndexError):
            pass

    # If version is empty, the package may not be installed; search for it
    for pkg, current_version in ret.items():
        if not current_version:
            installed = pkgs.get(pkg)
            cmd = ["apk", "search", pkg]
            out = __salt__["cmd.run_stdout"](cmd, output_loglevel="trace", python_shell=False)
            for line in salt.utils.itertools.split(out, "\n"):
                try:
                    pkg_version = "-".join(line.split("-")[-2:])
                    pkg_name = "-".join(line.split("-")[:-2])
                    if pkg == pkg_name:
                        if installed == pkg_version:
                            ret[pkg] = ""
                        else:
                            ret[pkg] = pkg_version
                except ValueError:
                    pass

    # Return a string if only one package name passed
    if len(names) == 1:
        return ret[names[0]]
    return ret


# TODO: Support specific version installation
def install(name=None, refresh=False, pkgs=None, sources=None, **kwargs):
    """
    Install the passed package, add refresh=True to update the apk database.

    name
        The name of the package to be installed. Note that this parameter is
        ignored if either "pkgs" or "sources" is passed. Additionally, please
        note that this option can only be used to install packages from a
        software repository. To install a package file manually, use the
        "sources" option.

        CLI Example:

        .. code-block:: bash

            salt '*' pkg.install <package name>

    refresh
        Whether or not to refresh the package database before installing.


    Multiple Package Installation Options:

    pkgs
        A list of packages to install from a software repository. Must be
        passed as a python list.

        CLI Example:

        .. code-block:: bash

            salt '*' pkg.install pkgs='["foo", "bar"]'

    sources
        A list of .apk packages to install. Must be passed as a list of dicts,
        with the keys being package names, and the values being the source URI
        or local path to the package. Dependencies are automatically resolved
        and marked as auto-installed.

        CLI Example:

        .. code-block:: bash

            salt '*' pkg.install sources='[{"foo": "salt://foo.apk"},{"bar": "salt://bar.apk"}]'

    Returns a dict containing the new package names and versions::

        {'<package>': {'old': '<old-version>',
                       'new': '<new-version>'}}
    """
    refreshdb = salt.utils.data.is_true(refresh)
    pkg_to_install = []

    old = list_pkgs()

    if name and not (pkgs or sources):
        if "," in name:
            pkg_to_install = name.split(",")
        else:
            pkg_to_install = [name]

    if pkgs:
        # Specific version installation is not yet supported, so extract
        # just the package name from any dict entries in the list.
        pkgs = [next(iter(p)) for p in pkgs if isinstance(p, dict)]
        pkg_to_install.extend(pkgs)

    if not pkg_to_install:
        return {}

    if refreshdb:
        refresh_db()

    cmd = ["apk", "add"]

    # Add the upgrade flag if any requested package is already installed,
    # since apk will otherwise treat the install as a no-op for those packages.
    for _pkg in pkg_to_install:
        if old.get(_pkg):
            cmd.append("-u")
            break

    cmd.extend(pkg_to_install)

    out = __salt__["cmd.run_all"](cmd, output_loglevel="trace", python_shell=False)

    if out["retcode"] != 0 and out["stderr"]:
        errors = [out["stderr"]]
    else:
        errors = []

    __context__.pop("pkg.list_pkgs", None)
    new = list_pkgs()
    ret = salt.utils.data.compare_dicts(old, new)

    if errors:
        raise CommandExecutionError(
            "Problem encountered installing package(s)",
            info={"errors": errors, "changes": ret},
        )

    return ret


def purge(name=None, pkgs=None, **kwargs):
    """
    Remove packages and their configuration files using ``apk del --purge``.

    name
        The name of the package to be purged.

    pkgs
        A list of packages to purge. Must be passed as a python list. The
        ``name`` parameter will be ignored if this option is passed.

    Returns a dict containing the changes.

    CLI Example:

    .. code-block:: bash

        salt '*' pkg.purge <package name>
        salt '*' pkg.purge pkgs='["foo", "bar"]'
    """
    return remove(name=name, pkgs=pkgs, purge=True)


def remove(name=None, pkgs=None, purge=False, **kwargs):  # pylint: disable=unused-argument
    """
    Remove packages using ``apk del``.

    name
        The name of the package to be deleted.


    Multiple Package Options:

    pkgs
        A list of packages to delete. Must be passed as a python list. The
        ``name`` parameter will be ignored if this option is passed.

    Returns a dict containing the changes.

    CLI Example:

    .. code-block:: bash

        salt '*' pkg.remove <package name>
        salt '*' pkg.remove <package1>,<package2>,<package3>
        salt '*' pkg.remove pkgs='["foo", "bar"]'
    """
    old = list_pkgs()
    pkg_to_remove = []

    if name:
        if "," in name:
            pkg_to_remove = name.split(",")
        else:
            pkg_to_remove = [name]

    if pkgs:
        pkg_to_remove.extend(pkgs)

    if not pkg_to_remove:
        return {}

    if purge:
        cmd = ["apk", "del", "--purge"]
    else:
        cmd = ["apk", "del"]

    cmd.extend(pkg_to_remove)

    out = __salt__["cmd.run_all"](cmd, output_loglevel="trace", python_shell=False)
    if out["retcode"] != 0 and out["stderr"]:
        errors = [out["stderr"]]
    else:
        errors = []

    __context__.pop("pkg.list_pkgs", None)
    new = list_pkgs()
    ret = salt.utils.data.compare_dicts(old, new)

    if errors:
        raise CommandExecutionError(
            "Problem encountered removing package(s)",
            info={"errors": errors, "changes": ret},
        )

    return ret


def upgrade(name=None, pkgs=None, refresh=True, **kwargs):
    """
    Upgrades all packages via ``apk upgrade`` or a specific package if name or
    pkgs is specified. Name is ignored if pkgs is specified

    Returns a dict containing the changes.

        {'<package>':  {'old': '<old-version>',
                        'new': '<new-version>'}}

    CLI Example:

    .. code-block:: bash

        salt '*' pkg.upgrade
    """
    ret = {
        "changes": {},
        "result": True,
        "comment": "",
    }

    if salt.utils.data.is_true(refresh):
        refresh_db()

    old = list_pkgs()

    pkg_to_upgrade = []

    if name and not pkgs:
        if "," in name:
            pkg_to_upgrade = name.split(",")
        else:
            pkg_to_upgrade = [name]

    if pkgs:
        pkg_to_upgrade.extend(pkgs)

    if pkg_to_upgrade:
        cmd = ["apk", "add", "-u"]
        cmd.extend(pkg_to_upgrade)
    else:
        cmd = ["apk", "upgrade"]

    call = __salt__["cmd.run_all"](
        cmd, output_loglevel="trace", python_shell=False, redirect_stderr=True
    )

    if call["retcode"] != 0:
        ret["result"] = False
        if call["stdout"]:
            ret["comment"] = call["stdout"]

    __context__.pop("pkg.list_pkgs", None)
    new = list_pkgs()
    ret["changes"] = salt.utils.data.compare_dicts(old, new)

    return ret


def list_upgrades(refresh=True, **kwargs):
    """
    List all available package upgrades.

    CLI Example:

    .. code-block:: bash

        salt '*' pkg.list_upgrades
    """
    ret = {}
    if salt.utils.data.is_true(refresh):
        refresh_db()

    cmd = ["apk", "upgrade", "-s"]
    call = __salt__["cmd.run_all"](cmd, output_loglevel="trace", python_shell=False)

    if call["retcode"] != 0:
        comment = ""
        if "stderr" in call:
            comment += call["stderr"]
        if "stdout" in call:
            comment += call["stdout"]
        raise CommandExecutionError(comment)
    out = call["stdout"]

    for line in out.splitlines():
        if "Upgrading" in line:
            name = line.split(" ")[2]
            _oldversion = line.split(" ")[3].strip("(")
            newversion = line.split(" ")[5].strip(")")
            ret[name] = newversion

    return ret


def file_list(*packages, **kwargs):
    """
    List the files that belong to a package as a flat list. Not specifying
    any packages will return a list of every file on the system's package
    database (not generally recommended).

    CLI Examples:

    .. code-block:: bash

        salt '*' pkg.file_list httpd
        salt '*' pkg.file_list httpd postfix
        salt '*' pkg.file_list
    """
    if not packages:
        return "Package name should be provided"
    result = file_dict(*packages)
    files = []
    for pkg_files in result.get("packages", {}).values():
        files.extend(pkg_files)
    return files


def file_dict(*packages, **kwargs):
    """
    List the files that belong to a package, grouped by package. Not
    specifying any packages will return a list of every file on the system's
    package database (not generally recommended).

    CLI Examples:

    .. code-block:: bash

        salt '*' pkg.file_dict httpd
        salt '*' pkg.file_dict httpd postfix
        salt '*' pkg.file_dict
    """
    errors = []
    ret = {}
    cmd_files = ["apk", "info", "-L"]

    if not packages:
        return "Package name should be provided"

    for package in packages:
        files = []
        cmd = cmd_files[:]
        cmd.append(package)
        out = __salt__["cmd.run_all"](cmd, output_loglevel="trace", python_shell=False)
        for line in out["stdout"].splitlines():
            if line.endswith("contains:"):
                continue
            files.append(line)
        if files:
            ret[package] = files

    return {"errors": errors, "packages": ret}


def _pkg_name_from_apk_string(pkg_string):
    """
    Extract the package name from a string in apk's name-version-revision
    format (e.g. 'openssl-3.3.2-r0' -> 'openssl',
    'py3-requests-2.28.0-r0' -> 'py3-requests').

    Alpine package names never start a component with a digit, so the name
    ends at the first dash-separated component that begins with a digit.
    """
    parts = pkg_string.split("-")
    name_parts = []
    for part in parts:
        if part and part[0].isdigit():
            break
        name_parts.append(part)
    return "-".join(name_parts) if name_parts else pkg_string


def owner(*paths, **kwargs):
    """
    Return the name of the package that owns the file. Multiple file paths can
    be passed. Like :mod:`pkg.version <salt.modules.apk.version`, if a single
    path is passed, a string will be returned, and if multiple paths are passed,
    a dictionary of file/package name pairs will be returned.

    If the file is not owned by a package, or is not present on the minion,
    then an empty string will be returned for that path.

    CLI Example:

    .. code-block:: bash

        salt '*' pkg.owner /usr/bin/apachectl
        salt '*' pkg.owner /usr/bin/apachectl /usr/bin/basename
    """
    if not paths:
        return "You must provide a path"

    ret = {}
    cmd_search = ["apk", "info", "-W"]
    for path in paths:
        cmd = cmd_search[:]
        cmd.append(path)
        output = __salt__["cmd.run_stdout"](cmd, output_loglevel="trace", python_shell=False)
        if output:
            if "ERROR:" in output:
                ret[path] = "Could not find owner package"
            else:
                # apk outputs "<path> is owned by <name>-<version>-<revision>"
                pkg_full = output.split("by ")[1].strip()
                ret[path] = _pkg_name_from_apk_string(pkg_full)
        else:
            ret[path] = f"Error running {cmd}"

    return ret
