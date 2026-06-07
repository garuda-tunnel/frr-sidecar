"""Smoke tests for tests/_frr_config_parser.py.

Validates that ciscoconfparse2 correctly models the FRR syntax we care
about (interface blocks, router ospf children, route-map with
permit/deny seq). If any of these fail, switch the affected query to a
regex-based fallback before relying on it for rendering-test migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _frr_config_parser import (  # noqa: E402
    has_interface,
    iface_block,
    iface_is_active,
    iface_is_passive,
    interface_names_in_order,
    parse_frr,
    route_map_block,
    router_ospf_block,
)


_SAMPLE = """\
frr defaults traditional
log syslog informational
hostname wg_tik-frr

interface backbone
 ip ospf area 0.0.0.0
 ip ospf hello-interval 5
 ip ospf dead-interval 15
 ip ospf mtu-ignore

interface wg_tik
 ip ospf area 0.0.0.0
 ip ospf passive

route-map TRANSIT-DEFAULT-TAG permit 10
 set tag 201

router ospf
 ospf router-id 10.130.30.20
 redistribute connected
 default-information originate always metric 10 metric-type 2 route-map TRANSIT-DEFAULT-TAG

line vty
"""


def test_iface_block_returns_children():
    parse = parse_frr(_SAMPLE)
    block = iface_block(parse, "backbone")
    assert "ip ospf area 0.0.0.0" in block
    assert "ip ospf hello-interval 5" in block


def test_router_ospf_block_returns_children():
    parse = parse_frr(_SAMPLE)
    block = router_ospf_block(parse)
    assert "ospf router-id 10.130.30.20" in block
    assert any(line.startswith("default-information originate") for line in block)


def test_route_map_block_returns_children():
    """Validates ciscoconfparse2 can model 'route-map NAME permit SEQ' as parent."""
    parse = parse_frr(_SAMPLE)
    block = route_map_block(parse, "TRANSIT-DEFAULT-TAG")
    assert "set tag 201" in block


def test_interface_names_in_order_backbone_first():
    parse = parse_frr(_SAMPLE)
    assert interface_names_in_order(parse) == ["backbone", "wg_tik"]


def test_iface_is_active_detects_backbone():
    parse = parse_frr(_SAMPLE)
    assert iface_is_active(parse, "backbone") is True
    assert iface_is_passive(parse, "backbone") is False


def test_iface_is_passive_detects_wg_tik():
    parse = parse_frr(_SAMPLE)
    assert iface_is_passive(parse, "wg_tik") is True
    assert iface_is_active(parse, "wg_tik") is False


def test_has_interface_true_for_present_false_for_absent():
    parse = parse_frr(_SAMPLE)
    assert has_interface(parse, "backbone") is True
    assert has_interface(parse, "nonexistent") is False
