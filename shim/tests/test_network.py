"""Tests for the network module stub.

network is a MicroPython core module providing direct Wi-Fi/BT control.
The shim provides a stub that lets imports succeed and offers a coherent
"offline" set of return values — apps that gate online features on
isconnected() will gracefully skip those features.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import warnings

import pytest

from pdeck_sim import _stubs
_stubs.install_all()


# ---------------------------------------------------------------------------
# Module presence
# ---------------------------------------------------------------------------

def test_network_imports():
    """The whole point: import works."""
    import network
    assert network is not None

def test_network_has_interface_constants():
    """STA_IF and AP_IF are the standard mode constants apps reference
    when constructing a WLAN."""
    import network
    assert hasattr(network, "STA_IF")
    assert hasattr(network, "AP_IF")
    # Numeric values match MicroPython's actual constants
    assert network.STA_IF == 0
    assert network.AP_IF == 1


# ---------------------------------------------------------------------------
# WLAN class behavior
# ---------------------------------------------------------------------------

def test_wlan_construction():
    """Standard pattern: wlan = network.WLAN(network.STA_IF)."""
    import network
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wlan = network.WLAN(network.STA_IF)
    assert wlan is not None

def test_wlan_active_setter_and_getter():
    """active() with arg is setter; without arg is getter."""
    import network
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wlan = network.WLAN(network.STA_IF)
        assert wlan.active() is False  # default off
        wlan.active(True)
        assert wlan.active() is True
        wlan.active(False)
        assert wlan.active() is False

def test_wlan_isconnected_returns_false():
    """Always False on shim — this is the device-faithful offline answer.
    Apps gating online features on this will skip them gracefully."""
    import network
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wlan = network.WLAN(network.STA_IF)
        # Even after "connecting", we stay offline
        wlan.connect("MySSID", "password")
        assert wlan.isconnected() is False

def test_wlan_ifconfig_returns_4tuple():
    """ifconfig() returns (ip, netmask, gateway, dns)."""
    import network
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wlan = network.WLAN(network.STA_IF)
        config = wlan.ifconfig()
    assert isinstance(config, tuple)
    assert len(config) == 4
    # All zero — placeholder for offline
    assert all(part == "0.0.0.0" for part in config)

def test_wlan_scan_returns_empty():
    """Scan finds no SSIDs in the offline shim."""
    import network
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wlan = network.WLAN(network.STA_IF)
        result = wlan.scan()
    assert result == []

def test_wlan_methods_dont_crash():
    """All the common methods should accept their args without exception."""
    import network
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wlan = network.WLAN(network.STA_IF)
        wlan.connect("ssid", "password")
        wlan.disconnect()
        wlan.status()
        wlan.config(reconnects=3)


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

def test_status_constants_exist():
    """Apps compare WLAN status against these constants."""
    import network
    for name in ("STAT_IDLE", "STAT_CONNECTING", "STAT_GOT_IP",
                 "STAT_NO_AP_FOUND", "STAT_WRONG_PASSWORD"):
        assert hasattr(network, name), f"Missing constant: {name}"


# ---------------------------------------------------------------------------
# Bluetooth — also under network on ESP32
# ---------------------------------------------------------------------------

def test_bluetooth_class_exists():
    """Some apps construct network.Bluetooth() for BT setup."""
    import network
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bt = network.Bluetooth()
    assert bt is not None

def test_bluetooth_methods_dont_crash():
    """BT method calls should be silent no-ops."""
    import network
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bt = network.Bluetooth()
        bt.active(True)
        bt.gap_advertise(100)
        bt.config(addr_mode=1)


# ---------------------------------------------------------------------------
# Realistic usage pattern — what jp_input.py likely does
# ---------------------------------------------------------------------------

def test_typical_check_for_internet_pattern():
    """Replicate the most common deck pattern: import network, construct
    a WLAN, check isconnected, fall back if not. The whole sequence
    should run without exceptions."""
    import network
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"Online at {ip}")
        else:
            # Apps would do offline fallback here
            pass
    # Test passes if no exception was raised
