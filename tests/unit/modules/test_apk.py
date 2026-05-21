"""
Unit tests for saltext.alpine.modules.apk
"""

from unittest.mock import MagicMock

import pytest
from salt.exceptions import CommandExecutionError

from saltext.alpine.modules import apk as apk_module

# ---------------------------------------------------------------------------
# Helpers used as side_effects for pkg_resource mocks
# ---------------------------------------------------------------------------


def _add_pkg(pkgs, name, version):
    """Minimal reimplementation of salt.modules.pkg_resource.add_pkg."""
    pkgs.setdefault(name, [])
    pkgs[name].append(version)


def _stringify(pkgs):
    """Minimal reimplementation of salt.modules.pkg_resource.stringify."""
    for key in pkgs:
        if isinstance(pkgs[key], list):
            pkgs[key] = pkgs[key][-1] if pkgs[key] else ""


# ---------------------------------------------------------------------------
# Base fixture: inject salt dunder attributes into the module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def salt_dunders(monkeypatch):
    """
    Inject salt dunder attributes into the module under test.
    Each test gets a fresh set so mutations in one test do not bleed into
    the next.
    """
    salt_mock = {
        "cmd.run": MagicMock(return_value=""),
        "cmd.run_all": MagicMock(return_value={"retcode": 0, "stdout": "", "stderr": ""}),
        "cmd.run_stdout": MagicMock(return_value=""),
        "pkg_resource.version": MagicMock(return_value=""),
        "pkg_resource.add_pkg": MagicMock(side_effect=_add_pkg),
        "pkg_resource.sort_pkglist": MagicMock(),
        "pkg_resource.stringify": MagicMock(side_effect=_stringify),
    }
    monkeypatch.setattr(apk_module, "__salt__", salt_mock, raising=False)
    monkeypatch.setattr(apk_module, "__grains__", {"os_family": "Alpine"}, raising=False)
    monkeypatch.setattr(apk_module, "__context__", {}, raising=False)
    monkeypatch.setattr(apk_module, "__opts__", {}, raising=False)


# ---------------------------------------------------------------------------
# __virtual__
# ---------------------------------------------------------------------------


class TestVirtual:
    def test_returns_virtualname_on_alpine(self):
        assert apk_module.__virtual__() == "pkg"

    def test_returns_false_on_non_alpine(self, monkeypatch):
        monkeypatch.setattr(apk_module, "__grains__", {"os_family": "Debian"}, raising=False)
        result = apk_module.__virtual__()
        assert result[0] is False
        assert "Alpine" in result[1]


# ---------------------------------------------------------------------------
# refresh_db
# ---------------------------------------------------------------------------


class TestRefreshDb:
    def test_returns_true_on_success(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 0,
            "stdout": "",
            "stderr": "",
        }
        assert apk_module.refresh_db() is True

    def test_raises_on_failure(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 1,
            "stdout": "fetch failed",
            "stderr": "",
        }
        with pytest.raises(CommandExecutionError) as exc_info:
            apk_module.refresh_db()
        assert "updating the package database" in str(exc_info.value)

    def test_calls_apk_update(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 0,
            "stdout": "",
            "stderr": "",
        }
        apk_module.refresh_db()
        apk_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["apk", "update"], output_loglevel="trace", python_shell=False
        )


# ---------------------------------------------------------------------------
# list_pkgs
# ---------------------------------------------------------------------------


class TestListPkgs:
    def test_parses_simple_package(self):
        apk_module.__salt__["cmd.run"].return_value = "openssl-3.3.2-r0"
        result = apk_module.list_pkgs()
        assert result == {"openssl": "3.3.2-r0"}

    def test_parses_hyphenated_package_name(self):
        apk_module.__salt__["cmd.run"].return_value = "py3-requests-2.31.0-r1"
        result = apk_module.list_pkgs()
        assert result == {"py3-requests": "2.31.0-r1"}

    def test_parses_multiple_packages(self):
        apk_module.__salt__["cmd.run"].return_value = (
            "musl-1.2.4-r2\nopenssl-3.3.2-r0\npy3-requests-2.31.0-r1"
        )
        result = apk_module.list_pkgs()
        assert result["musl"] == "1.2.4-r2"
        assert result["openssl"] == "3.3.2-r0"
        assert result["py3-requests"] == "2.31.0-r1"

    def test_populates_context_cache(self):
        apk_module.__salt__["cmd.run"].return_value = "openssl-3.3.2-r0"
        apk_module.list_pkgs()
        assert "pkg.list_pkgs" in apk_module.__context__

    def test_returns_from_context_cache(self):
        apk_module.__context__["pkg.list_pkgs"] = {"openssl": ["3.3.2-r0"]}
        apk_module.list_pkgs()
        # cmd.run should not have been called since we have a cached result
        apk_module.__salt__["cmd.run"].assert_not_called()

    def test_skips_removed_flag(self):
        result = apk_module.list_pkgs(removed=True)
        assert not result
        apk_module.__salt__["cmd.run"].assert_not_called()

    def test_skips_purge_desired_flag(self):
        result = apk_module.list_pkgs(purge_desired=True)
        assert not result
        apk_module.__salt__["cmd.run"].assert_not_called()

    def test_versions_as_list_returns_lists(self):
        apk_module.__salt__["cmd.run"].return_value = "openssl-3.3.2-r0"
        result = apk_module.list_pkgs(versions_as_list=True)
        assert result == {"openssl": ["3.3.2-r0"]}

    def test_calls_apk_info_v(self):
        apk_module.__salt__["cmd.run"].return_value = ""
        apk_module.list_pkgs()
        apk_module.__salt__["cmd.run"].assert_called_once_with(
            ["apk", "info", "-v"], output_loglevel="trace", python_shell=False
        )


# ---------------------------------------------------------------------------
# latest_version
# ---------------------------------------------------------------------------


class TestLatestVersion:
    @pytest.fixture(autouse=True)
    def patch_internals(self, monkeypatch):
        """Patch list_pkgs and refresh_db to isolate latest_version logic."""
        monkeypatch.setattr(apk_module, "list_pkgs", MagicMock(return_value={}))
        monkeypatch.setattr(apk_module, "refresh_db", MagicMock())

    def test_returns_empty_string_when_no_names(self):
        assert apk_module.latest_version() == ""

    def test_finds_upgrade_available(self):
        # Real apk upgrade -s output includes a (N/M) progress prefix on each line.
        # The parsing code uses column indices written for that format.
        apk_module.__salt__["cmd.run_stdout"].return_value = (
            "(1/1) Upgrading openssl (3.3.1-r0 -> 3.3.2-r0)"
        )
        result = apk_module.latest_version("openssl", refresh=False)
        assert result == "3.3.2-r0"

    def test_returns_empty_string_when_already_latest(self):
        # upgrade -s shows nothing for this package, search returns same version
        apk_module.list_pkgs.return_value = {"htop": "3.3.0-r0"}
        apk_module.__salt__["cmd.run_stdout"].side_effect = [
            "",  # apk upgrade -s - no upgrades
            "htop-3.3.0-r0",  # apk search htop - same version
        ]
        result = apk_module.latest_version("htop", refresh=False)
        assert result == ""

    def test_finds_newer_version_for_uninstalled_package(self):
        apk_module.__salt__["cmd.run_stdout"].side_effect = [
            "",  # apk upgrade -s - nothing
            "curl-8.5.0-r0",  # apk search curl
        ]
        result = apk_module.latest_version("curl", refresh=False)
        assert result == "8.5.0-r0"

    def test_returns_dict_for_multiple_packages(self):
        apk_module.__salt__["cmd.run_stdout"].side_effect = [
            "(1/1) Upgrading openssl (3.3.1-r0 -> 3.3.2-r0)",  # upgrade -s
            "",  # search htop - nothing found
        ]
        result = apk_module.latest_version("openssl", "htop", refresh=False)
        assert isinstance(result, dict)
        assert result["openssl"] == "3.3.2-r0"

    def test_calls_refresh_db_by_default(self):
        apk_module.__salt__["cmd.run_stdout"].return_value = ""
        apk_module.latest_version("openssl")
        apk_module.refresh_db.assert_called_once()

    def test_skips_refresh_when_disabled(self):
        apk_module.__salt__["cmd.run_stdout"].return_value = ""
        apk_module.latest_version("openssl", refresh=False)
        apk_module.refresh_db.assert_not_called()


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


class TestInstall:
    @pytest.fixture(autouse=True)
    def patch_internals(self, monkeypatch):
        """Patch list_pkgs and refresh_db to isolate install logic."""
        self.old_pkgs = {}
        self.new_pkgs = {}
        list_pkgs_mock = MagicMock(
            side_effect=lambda **kw: (
                self.new_pkgs if apk_module.__context__.get("_install_ran") else self.old_pkgs
            )
        )
        monkeypatch.setattr(apk_module, "list_pkgs", list_pkgs_mock)
        monkeypatch.setattr(apk_module, "refresh_db", MagicMock())

    def _mark_install_ran(self):
        """Helper: make list_pkgs return new_pkgs after the install command."""
        original_run_all = apk_module.__salt__["cmd.run_all"]

        def side_effect(cmd, **kwargs):
            if cmd[0:2] == ["apk", "add"]:
                apk_module.__context__["_install_ran"] = True
            return original_run_all(cmd, **kwargs)

        apk_module.__salt__["cmd.run_all"].side_effect = side_effect

    def test_install_single_package_calls_apk_add(self):
        apk_module.install(name="htop")
        apk_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["apk", "add", "htop"], output_loglevel="trace", python_shell=False
        )

    def test_install_comma_separated_names(self):
        apk_module.install(name="htop,curl")
        call_args = apk_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert "htop" in cmd
        assert "curl" in cmd

    def test_install_pkgs_list(self):
        apk_module.install(pkgs=[{"htop": ""}, {"curl": ""}])
        call_args = apk_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert "htop" in cmd
        assert "curl" in cmd

    def test_install_no_packages_returns_empty_dict(self):
        result = apk_module.install()
        assert not result
        apk_module.__salt__["cmd.run_all"].assert_not_called()

    def test_install_adds_upgrade_flag_for_existing_package(self):
        self.old_pkgs = {"htop": "3.2.0-r0"}
        apk_module.install(name="htop")
        call_args = apk_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert "-u" in cmd

    def test_install_no_upgrade_flag_for_new_package(self):
        self.old_pkgs = {}
        apk_module.install(name="htop")
        call_args = apk_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert "-u" not in cmd

    def test_install_calls_refresh_db_when_requested(self):
        apk_module.install(name="htop", refresh=True)
        apk_module.refresh_db.assert_called_once()

    def test_install_does_not_call_refresh_db_by_default(self):
        apk_module.install(name="htop")
        apk_module.refresh_db.assert_not_called()

    def test_install_raises_on_stderr(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 1,
            "stdout": "",
            "stderr": "package not found",
        }
        with pytest.raises(CommandExecutionError) as exc_info:
            apk_module.install(name="notapackage")
        assert "installing" in str(exc_info.value)

    def test_install_clears_context_cache(self):
        apk_module.__context__["pkg.list_pkgs"] = {"openssl": "3.3.2-r0"}
        apk_module.install(name="htop")
        assert "pkg.list_pkgs" not in apk_module.__context__


# ---------------------------------------------------------------------------
# purge
# ---------------------------------------------------------------------------


class TestPurge:
    def test_purge_delegates_to_remove_with_purge_true(self, monkeypatch):
        remove_mock = MagicMock(return_value={})
        monkeypatch.setattr(apk_module, "remove", remove_mock)
        apk_module.purge(name="htop")
        remove_mock.assert_called_once_with(name="htop", pkgs=None, purge=True)


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


class TestRemove:
    @pytest.fixture(autouse=True)
    def patch_internals(self, monkeypatch):
        monkeypatch.setattr(apk_module, "list_pkgs", MagicMock(return_value={}))

    def test_remove_single_package(self):
        apk_module.remove(name="htop")
        apk_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["apk", "del", "htop"], output_loglevel="trace", python_shell=False
        )

    def test_remove_comma_separated_names(self):
        apk_module.remove(name="htop,curl")
        call_args = apk_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert "htop" in cmd
        assert "curl" in cmd

    def test_remove_pkgs_list(self):
        apk_module.remove(pkgs=["htop", "curl"])
        call_args = apk_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert "htop" in cmd
        assert "curl" in cmd

    def test_remove_with_purge_adds_flag(self):
        apk_module.remove(name="htop", purge=True)
        call_args = apk_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert "--purge" in cmd

    def test_remove_without_purge_no_flag(self):
        apk_module.remove(name="htop")
        call_args = apk_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert "--purge" not in cmd

    def test_remove_no_packages_returns_empty_dict(self):
        result = apk_module.remove()
        assert not result
        apk_module.__salt__["cmd.run_all"].assert_not_called()

    def test_remove_raises_on_stderr(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 1,
            "stdout": "",
            "stderr": "ERROR: No such package",
        }
        with pytest.raises(CommandExecutionError):
            apk_module.remove(name="notapackage")

    def test_remove_clears_context_cache(self):
        apk_module.__context__["pkg.list_pkgs"] = {"htop": "3.3.0-r0"}
        apk_module.remove(name="htop")
        assert "pkg.list_pkgs" not in apk_module.__context__


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


class TestUpgrade:
    @pytest.fixture(autouse=True)
    def patch_internals(self, monkeypatch):
        monkeypatch.setattr(apk_module, "list_pkgs", MagicMock(return_value={}))
        monkeypatch.setattr(apk_module, "refresh_db", MagicMock())

    def test_upgrade_all_calls_apk_upgrade(self):
        apk_module.upgrade()
        call_args = apk_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert cmd == ["apk", "upgrade"]

    def test_upgrade_specific_package_calls_apk_add_u(self):
        apk_module.upgrade(name="openssl")
        call_args = apk_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert "-u" in cmd
        assert "openssl" in cmd

    def test_upgrade_pkgs_list(self):
        apk_module.upgrade(pkgs=["openssl", "musl"])
        call_args = apk_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert "-u" in cmd
        assert "openssl" in cmd
        assert "musl" in cmd

    def test_upgrade_failure_sets_result_false(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 1,
            "stdout": "fetch error",
            "stderr": "",
        }
        result = apk_module.upgrade(refresh=False)
        assert result["result"] is False
        assert result["comment"] == "fetch error"

    def test_upgrade_calls_refresh_db_by_default(self):
        apk_module.upgrade()
        apk_module.refresh_db.assert_called_once()

    def test_upgrade_skips_refresh_when_disabled(self):
        apk_module.upgrade(refresh=False)
        apk_module.refresh_db.assert_not_called()

    def test_upgrade_clears_context_cache(self):
        apk_module.__context__["pkg.list_pkgs"] = {"openssl": "3.3.1-r0"}
        apk_module.upgrade(refresh=False)
        assert "pkg.list_pkgs" not in apk_module.__context__


# ---------------------------------------------------------------------------
# list_upgrades
# ---------------------------------------------------------------------------


class TestListUpgrades:
    @pytest.fixture(autouse=True)
    def patch_refresh(self, monkeypatch):
        monkeypatch.setattr(apk_module, "refresh_db", MagicMock())

    def test_parses_upgrade_output(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 0,
            "stdout": "(1/1) Upgrading openssl (3.3.1-r0 -> 3.3.2-r0)",
            "stderr": "",
        }
        result = apk_module.list_upgrades(refresh=False)
        assert result == {"openssl": "3.3.2-r0"}

    def test_parses_multiple_upgrades(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 0,
            "stdout": (
                "(1/2) Upgrading openssl (3.3.1-r0 -> 3.3.2-r0)\n"
                "(2/2) Upgrading musl (1.2.3-r0 -> 1.2.4-r0)"
            ),
            "stderr": "",
        }
        result = apk_module.list_upgrades(refresh=False)
        assert result["openssl"] == "3.3.2-r0"
        assert result["musl"] == "1.2.4-r0"

    def test_returns_empty_dict_when_no_upgrades(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 0,
            "stdout": "",
            "stderr": "",
        }
        result = apk_module.list_upgrades(refresh=False)
        assert not result

    def test_raises_on_command_failure(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 1,
            "stdout": "fetch failed",
            "stderr": "network error",
        }
        with pytest.raises(CommandExecutionError):
            apk_module.list_upgrades(refresh=False)

    def test_calls_refresh_by_default(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 0,
            "stdout": "",
            "stderr": "",
        }
        apk_module.list_upgrades()
        apk_module.refresh_db.assert_called_once()


# ---------------------------------------------------------------------------
# file_list
# ---------------------------------------------------------------------------


class TestFileList:
    def test_returns_flat_list_of_files(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 0,
            "stdout": "openssl contains:\nusr/bin/openssl\nusr/lib/libssl.so",
            "stderr": "",
        }
        result = apk_module.file_list("openssl")
        assert isinstance(result, list)
        assert "usr/bin/openssl" in result
        assert "usr/lib/libssl.so" in result

    def test_does_not_include_contains_header_line(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 0,
            "stdout": "openssl contains:\nusr/bin/openssl",
            "stderr": "",
        }
        result = apk_module.file_list("openssl")
        assert not any("contains:" in f for f in result)

    def test_merges_files_from_multiple_packages(self):
        apk_module.__salt__["cmd.run_all"].side_effect = [
            {"retcode": 0, "stdout": "openssl contains:\nusr/bin/openssl", "stderr": ""},
            {"retcode": 0, "stdout": "musl contains:\nlib/libc.musl-x86_64.so.1", "stderr": ""},
        ]
        result = apk_module.file_list("openssl", "musl")
        assert "usr/bin/openssl" in result
        assert "lib/libc.musl-x86_64.so.1" in result

    def test_returns_error_string_when_no_packages(self):
        result = apk_module.file_list()
        assert isinstance(result, str)
        assert "Package name" in result


# ---------------------------------------------------------------------------
# file_dict
# ---------------------------------------------------------------------------


class TestFileDict:
    def test_returns_grouped_structure(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 0,
            "stdout": "openssl contains:\nusr/bin/openssl\nusr/lib/libssl.so",
            "stderr": "",
        }
        result = apk_module.file_dict("openssl")
        assert "packages" in result
        assert "errors" in result
        assert "openssl" in result["packages"]
        assert "usr/bin/openssl" in result["packages"]["openssl"]

    def test_skips_contains_header_line(self):
        apk_module.__salt__["cmd.run_all"].return_value = {
            "retcode": 0,
            "stdout": "openssl contains:\nusr/bin/openssl",
            "stderr": "",
        }
        result = apk_module.file_dict("openssl")
        assert not any("contains:" in f for f in result["packages"].get("openssl", []))

    def test_returns_error_string_when_no_packages(self):
        result = apk_module.file_dict()
        assert isinstance(result, str)
        assert "Package name" in result


# ---------------------------------------------------------------------------
# _pkg_name_from_apk_string
# ---------------------------------------------------------------------------


class TestPkgNameFromApkString:
    @pytest.mark.parametrize(
        "apk_string, expected",
        [
            ("openssl-3.3.2-r0", "openssl"),
            ("musl-1.2.4-r2", "musl"),
            ("py3-requests-2.31.0-r1", "py3-requests"),
            ("py3-setuptools-65.5.0-r0", "py3-setuptools"),
            ("ca-certificates-20240226-r0", "ca-certificates"),
            ("util-linux-misc-2.39.3-r0", "util-linux-misc"),
            ("libc-utils-0.7.2-r5", "libc-utils"),
            ("alpine-baselayout-data-3.4.3-r2", "alpine-baselayout-data"),
        ],
    )
    def test_extracts_name(self, apk_string, expected):
        assert apk_module._pkg_name_from_apk_string(apk_string) == expected


# ---------------------------------------------------------------------------
# owner
# ---------------------------------------------------------------------------


class TestOwner:
    def test_returns_error_string_when_no_paths(self):
        result = apk_module.owner()
        assert isinstance(result, str)
        assert "path" in result.lower()

    def test_strips_version_from_simple_package(self):
        apk_module.__salt__["cmd.run_stdout"].return_value = (
            "/usr/bin/openssl is owned by openssl-3.3.2-r0"
        )
        result = apk_module.owner("/usr/bin/openssl")
        assert result == {"/usr/bin/openssl": "openssl"}

    def test_strips_version_from_hyphenated_package(self):
        apk_module.__salt__["cmd.run_stdout"].return_value = (
            "/usr/lib/python3/site-packages/requests is owned by py3-requests-2.31.0-r1"
        )
        result = apk_module.owner("/usr/lib/python3/site-packages/requests")
        path = "/usr/lib/python3/site-packages/requests"
        assert result[path] == "py3-requests"

    def test_handles_error_output(self):
        apk_module.__salt__["cmd.run_stdout"].return_value = (
            "ERROR: /nonexistent: Could not find owner package"
        )
        result = apk_module.owner("/nonexistent")
        assert result["/nonexistent"] == "Could not find owner package"

    def test_returns_dict_for_multiple_paths(self):
        apk_module.__salt__["cmd.run_stdout"].side_effect = [
            "/usr/bin/openssl is owned by openssl-3.3.2-r0",
            "/bin/busybox is owned by busybox-1.36.1-r15",
        ]
        result = apk_module.owner("/usr/bin/openssl", "/bin/busybox")
        assert isinstance(result, dict)
        assert result["/usr/bin/openssl"] == "openssl"
        assert result["/bin/busybox"] == "busybox"

    def test_handles_empty_output(self):
        apk_module.__salt__["cmd.run_stdout"].return_value = ""
        result = apk_module.owner("/nonexistent")
        assert "/nonexistent" in result
        assert "Error" in result["/nonexistent"]
