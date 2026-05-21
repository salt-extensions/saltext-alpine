"""
Unit tests for saltext.alpine.modules.openrc
"""

from unittest.mock import MagicMock

import pytest
from salt.exceptions import CommandExecutionError

from saltext.alpine.modules import openrc as openrc_module

# ---------------------------------------------------------------------------
# Base fixture: inject salt dunder attributes into the module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def salt_dunders(monkeypatch):
    """
    Inject salt dunder attributes into the module under test.
    cmd.run_all defaults to a successful no-output response so individual
    tests only need to override what they care about.
    """
    salt_mock = {
        "cmd.run_all": MagicMock(return_value={"retcode": 0, "stdout": "", "stderr": ""}),
    }
    monkeypatch.setattr(openrc_module, "__salt__", salt_mock, raising=False)
    monkeypatch.setattr(openrc_module, "__grains__", {"os_family": "Alpine"}, raising=False)
    monkeypatch.setattr(openrc_module, "__opts__", {}, raising=False)


def _run_all_ok(stdout=""):
    return {"retcode": 0, "stdout": stdout, "stderr": ""}


def _run_all_fail(stdout="", stderr=""):
    return {"retcode": 1, "stdout": stdout, "stderr": stderr}


# ---------------------------------------------------------------------------
# __virtual__
# ---------------------------------------------------------------------------


class TestVirtual:
    def test_returns_virtualname_on_alpine(self):
        assert openrc_module.__virtual__() == "service"

    def test_returns_false_on_non_alpine(self, monkeypatch):
        monkeypatch.setattr(openrc_module, "__grains__", {"os_family": "Debian"}, raising=False)
        result = openrc_module.__virtual__()
        assert result[0] is False
        assert "Alpine" in result[1]


# ---------------------------------------------------------------------------
# start / stop / restart / reload_
# ---------------------------------------------------------------------------


class TestServiceActions:
    @pytest.mark.parametrize(
        "func, action",
        [
            ("start", "start"),
            ("stop", "stop"),
            ("restart", "restart"),
            ("reload_", "reload"),
        ],
    )
    def test_returns_true_on_success(self, func, action):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok()
        result = getattr(openrc_module, func)("sshd")
        assert result is True

    @pytest.mark.parametrize(
        "func, action",
        [
            ("start", "start"),
            ("stop", "stop"),
            ("restart", "restart"),
            ("reload_", "reload"),
        ],
    )
    def test_returns_false_on_failure(self, func, action):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_fail()
        result = getattr(openrc_module, func)("sshd")
        assert result is False

    @pytest.mark.parametrize(
        "func, action",
        [
            ("start", "start"),
            ("stop", "stop"),
            ("restart", "restart"),
            ("reload_", "reload"),
        ],
    )
    def test_calls_rc_service_with_correct_action(self, func, action):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok()
        getattr(openrc_module, func)("sshd")
        openrc_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["rc-service", "sshd", action], python_shell=False
        )


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_returns_true_when_service_running(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok()
        assert openrc_module.status("sshd") is True

    def test_returns_false_when_service_stopped(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_fail()
        assert openrc_module.status("sshd") is False

    def test_calls_rc_service_status(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok()
        openrc_module.status("sshd")
        openrc_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["rc-service", "sshd", "status"], python_shell=False
        )

    def test_sig_parameter_does_not_affect_result(self):
        # sig is accepted for interface compatibility but rc-service is authoritative
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok()
        assert openrc_module.status("sshd", sig="sshd") is True
        openrc_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["rc-service", "sshd", "status"], python_shell=False
        )


# ---------------------------------------------------------------------------
# enabled / disabled
# ---------------------------------------------------------------------------


class TestEnabled:
    RC_UPDATE_OUTPUT = "      sshd | default\n  chronyd | default\n"

    def test_returns_true_when_service_in_runlevel(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok(self.RC_UPDATE_OUTPUT)
        assert openrc_module.enabled("sshd") is True

    def test_returns_false_when_service_not_in_runlevel(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok(self.RC_UPDATE_OUTPUT)
        assert openrc_module.enabled("nginx") is False

    def test_uses_default_runlevel_by_default(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok("")
        openrc_module.enabled("sshd")
        call_args = openrc_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert cmd == ["rc-update", "show", "default"]

    def test_uses_custom_runlevel_when_specified(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok("")
        openrc_module.enabled("sshd", runlevel="boot")
        call_args = openrc_module.__salt__["cmd.run_all"].call_args
        cmd = call_args[0][0]
        assert cmd == ["rc-update", "show", "boot"]


class TestDisabled:
    def test_disabled_is_inverse_of_enabled(self, monkeypatch):
        monkeypatch.setattr(openrc_module, "enabled", MagicMock(return_value=True))
        assert openrc_module.disabled("sshd") is False

    def test_disabled_true_when_not_enabled(self, monkeypatch):
        monkeypatch.setattr(openrc_module, "enabled", MagicMock(return_value=False))
        assert openrc_module.disabled("sshd") is True


# ---------------------------------------------------------------------------
# enable / disable
# ---------------------------------------------------------------------------


class TestEnable:
    def test_returns_true_on_success(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok()
        assert openrc_module.enable("sshd") is True

    def test_returns_false_on_failure(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_fail()
        assert openrc_module.enable("sshd") is False

    def test_calls_rc_update_add_with_default_runlevel(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok()
        openrc_module.enable("sshd")
        openrc_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["rc-update", "add", "sshd", "default"], python_shell=False
        )

    def test_uses_custom_runlevel(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok()
        openrc_module.enable("syslog", runlevel="boot")
        openrc_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["rc-update", "add", "syslog", "boot"], python_shell=False
        )


class TestDisableFunc:
    def test_returns_true_on_success(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok()
        assert openrc_module.disable("sshd") is True

    def test_returns_false_on_failure(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_fail()
        assert openrc_module.disable("sshd") is False

    def test_calls_rc_update_del_with_default_runlevel(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok()
        openrc_module.disable("sshd")
        openrc_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["rc-update", "del", "sshd", "default"], python_shell=False
        )

    def test_uses_custom_runlevel(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok()
        openrc_module.disable("syslog", runlevel="boot")
        openrc_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["rc-update", "del", "syslog", "boot"], python_shell=False
        )


# ---------------------------------------------------------------------------
# available / missing
# ---------------------------------------------------------------------------


class TestAvailable:
    def test_returns_true_when_service_in_list(self, monkeypatch):
        monkeypatch.setattr(openrc_module, "get_all", MagicMock(return_value=["chronyd", "sshd"]))
        assert openrc_module.available("sshd") is True

    def test_returns_false_when_service_not_in_list(self, monkeypatch):
        monkeypatch.setattr(openrc_module, "get_all", MagicMock(return_value=["chronyd", "sshd"]))
        assert openrc_module.available("nginx") is False


class TestMissing:
    def test_missing_is_inverse_of_available(self, monkeypatch):
        monkeypatch.setattr(openrc_module, "available", MagicMock(return_value=True))
        assert openrc_module.missing("sshd") is False

    def test_missing_true_when_not_available(self, monkeypatch):
        monkeypatch.setattr(openrc_module, "available", MagicMock(return_value=False))
        assert openrc_module.missing("nginx") is True


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


class TestGetAll:
    def test_returns_sorted_list(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok("sshd\nchronyd\nnginx\n")
        result = openrc_module.get_all()
        assert result == ["chronyd", "nginx", "sshd"]

    def test_strips_blank_lines(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok("\nsshd\n\nchronyd\n")
        result = openrc_module.get_all()
        assert "" not in result

    def test_raises_on_failure(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_fail(
            stderr="command not found"
        )
        with pytest.raises(CommandExecutionError) as exc_info:
            openrc_module.get_all()
        assert "list services" in str(exc_info.value)

    def test_calls_rc_service_list(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok("")
        openrc_module.get_all()
        openrc_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["rc-service", "--list"], python_shell=False
        )


# ---------------------------------------------------------------------------
# get_enabled
# ---------------------------------------------------------------------------


class TestGetEnabled:
    RC_UPDATE_DEFAULT = (
        "      sshd | default\n"
        "   chronyd | default\n"
        " * Caching service dependencies ...    [ ok ]\n"
        "networking | default\n"
    )

    def test_parses_pipe_separated_lines(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok(self.RC_UPDATE_DEFAULT)
        result = openrc_module.get_enabled()
        assert "sshd" in result
        assert "chronyd" in result
        assert "networking" in result

    def test_skips_non_pipe_lines(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok(self.RC_UPDATE_DEFAULT)
        result = openrc_module.get_enabled()
        # The caching status line should not appear in results
        assert not any("Caching" in svc for svc in result)
        assert not any("ok" in svc for svc in result)

    def test_returns_sorted_list(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok(
            "   sshd | default\nchronyd | default\n"
        )
        result = openrc_module.get_enabled()
        assert result == sorted(result)

    def test_uses_default_runlevel_by_default(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok("")
        openrc_module.get_enabled()
        call_args = openrc_module.__salt__["cmd.run_all"].call_args
        assert call_args[0][0] == ["rc-update", "show", "default"]

    def test_uses_custom_runlevel(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok("")
        openrc_module.get_enabled(runlevel="boot")
        call_args = openrc_module.__salt__["cmd.run_all"].call_args
        assert call_args[0][0] == ["rc-update", "show", "boot"]

    def test_raises_on_failure(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_fail()
        with pytest.raises(CommandExecutionError) as exc_info:
            openrc_module.get_enabled()
        assert "default" in str(exc_info.value)

    def test_raises_with_runlevel_in_message_for_custom_runlevel(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_fail()
        with pytest.raises(CommandExecutionError) as exc_info:
            openrc_module.get_enabled(runlevel="boot")
        assert "boot" in str(exc_info.value)


# ---------------------------------------------------------------------------
# get_running
# ---------------------------------------------------------------------------


class TestGetRunning:
    RC_STATUS_OUTPUT = (
        "Runlevel: default\n"
        " sshd                                                    [  started  ]\n"
        " chronyd                                                 [  started  ]\n"
        " nginx                                                   [  stopped  ]\n"
        "Dynamic Runlevel: hotplugged\n"
    )

    def test_returns_only_started_services(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok(self.RC_STATUS_OUTPUT)
        result = openrc_module.get_running()
        assert "sshd" in result
        assert "chronyd" in result

    def test_excludes_stopped_services(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok(self.RC_STATUS_OUTPUT)
        result = openrc_module.get_running()
        assert "nginx" not in result

    def test_excludes_runlevel_header_lines(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok(self.RC_STATUS_OUTPUT)
        result = openrc_module.get_running()
        assert not any("Runlevel" in svc for svc in result)

    def test_returns_sorted_list(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok(
            " zebra          [  started  ]\n alpha          [  started  ]\n"
        )
        result = openrc_module.get_running()
        assert result == sorted(result)

    def test_raises_on_failure(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_fail(
            stderr="rc-status: command not found"
        )
        with pytest.raises(CommandExecutionError) as exc_info:
            openrc_module.get_running()
        assert "running" in str(exc_info.value)

    def test_calls_rc_status_with_correct_flags(self):
        openrc_module.__salt__["cmd.run_all"].return_value = _run_all_ok("")
        openrc_module.get_running()
        openrc_module.__salt__["cmd.run_all"].assert_called_once_with(
            ["rc-status", "--nocolor", "-a"], python_shell=False
        )
