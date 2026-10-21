"""
Unit tests for saltext.alpine.modules.system
"""

from unittest.mock import MagicMock

import pytest

from saltext.alpine.modules import system as system_module

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
    }
    monkeypatch.setattr(system_module, "__salt__", salt_mock, raising=False)
    monkeypatch.setattr(system_module, "__grains__", {"os_family": "Alpine"}, raising=False)
    monkeypatch.setattr(system_module, "__context__", {}, raising=False)
    monkeypatch.setattr(system_module, "__opts__", {}, raising=False)


def _run_mock():
    return system_module.__salt__["cmd.run"]


# ---------------------------------------------------------------------------
# __virtual__
# ---------------------------------------------------------------------------


class TestVirtual:
    def test_returns_virtualname_on_alpine(self):
        assert system_module.__virtual__() == "system"

    def test_returns_false_on_non_alpine(self, monkeypatch):
        monkeypatch.setattr(system_module, "__grains__", {"os_family": "Debian"}, raising=False)
        result = system_module.__virtual__()
        assert result[0] is False
        assert "Alpine" in result[1]


# ---------------------------------------------------------------------------
# Power-state functions
# ---------------------------------------------------------------------------


class TestReboot:
    def test_immediate(self):
        system_module.reboot()
        _run_mock().assert_called_once_with(["reboot"], python_shell=False)

    def test_delayed_converts_minutes_to_seconds(self):
        system_module.reboot(at_time=5)
        _run_mock().assert_called_once_with(["reboot", "-d", "300"], python_shell=False)

    def test_non_numeric_at_time_is_ignored(self):
        system_module.reboot(at_time="soon")
        _run_mock().assert_called_once_with(["reboot"], python_shell=False)


class TestShutdown:
    def test_immediate_powers_off(self):
        system_module.shutdown()
        _run_mock().assert_called_once_with(["poweroff"], python_shell=False)

    def test_delayed(self):
        system_module.shutdown(at_time=2)
        _run_mock().assert_called_once_with(["poweroff", "-d", "120"], python_shell=False)


class TestPoweroffHalt:
    def test_poweroff(self):
        system_module.poweroff()
        _run_mock().assert_called_once_with(["poweroff"], python_shell=False)

    def test_halt(self):
        system_module.halt()
        _run_mock().assert_called_once_with(["halt"], python_shell=False)


# ---------------------------------------------------------------------------
# Re-exports: the override replaces the whole core module, so the remaining
# system.* functions must survive, and our four must win over core's.
# ---------------------------------------------------------------------------


class TestReexports:
    @pytest.mark.parametrize("name", ["get_computer_name", "set_computer_name", "init"])
    def test_core_function_present(self, name):
        assert callable(getattr(system_module, name, None))

    @pytest.mark.parametrize("name", ["reboot", "poweroff", "halt", "shutdown"])
    def test_overrides_are_local(self, name):
        # The power-state functions must be this module's, not the core ones.
        assert getattr(system_module, name).__module__ == system_module.__name__
