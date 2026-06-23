"""Tests for garuda_frr.transit_watcher: LSDB parsing, neighbor resolution, reconcile."""

from unittest.mock import MagicMock

from garuda_frr.transit_watcher import (
    find_transit_providers,
    get_installed_nexthops,
    reconcile_route,
    reconcile_rules,
    resolve_default_nexthops_from_ospf_routes,
    resolve_nexthops,
    resolve_nexthops_from_ospf_routes,
)

# ---------------------------------------------------------------------------
# LSDB parsing
# ---------------------------------------------------------------------------

EXTERNAL_DB_ONE_MATCH = {
    "asExternalLinkStates": [
        {
            "linkStateId": "0.0.0.0",
            "advertisingRouter": "10.130.30.99",
            "forwardAddress": "0.0.0.0",
            "externalRouteTag": 100,
        }
    ]
}

EXTERNAL_DB_TWO_MATCHES = {
    "asExternalLinkStates": [
        {
            "linkStateId": "0.0.0.0",
            "advertisingRouter": "10.130.30.99",
            "forwardAddress": "0.0.0.0",
            "externalRouteTag": 100,
        },
        {
            "linkStateId": "0.0.0.0",
            "advertisingRouter": "10.130.30.50",
            "forwardAddress": "0.0.0.0",
            "externalRouteTag": 100,
        },
    ]
}

EXTERNAL_DB_NO_MATCH = {
    "asExternalLinkStates": [
        {
            "linkStateId": "0.0.0.0",
            "advertisingRouter": "10.130.30.99",
            "forwardAddress": "0.0.0.0",
            "externalRouteTag": 200,
        }
    ]
}

EXTERNAL_DB_MIXED = {
    "asExternalLinkStates": [
        {
            "linkStateId": "0.0.0.0",
            "advertisingRouter": "10.130.30.99",
            "forwardAddress": "0.0.0.0",
            "externalRouteTag": 100,
        },
        {
            "linkStateId": "0.0.0.0",
            "advertisingRouter": "10.130.30.50",
            "forwardAddress": "0.0.0.0",
            "externalRouteTag": 200,
        },
    ]
}

EXTERNAL_DB_EMPTY = {"asExternalLinkStates": []}

NEIGHBOR_DB = {
    "neighbors": {
        "10.130.30.99": [
            {
                "ifaceAddress": "172.30.0.100",
                "ifaceName": "backbone:172.30.0.10",
            }
        ],
        "10.130.30.50": [
            {
                "ifaceAddress": "172.30.0.200",
                "ifaceName": "backbone:172.30.0.10",
            }
        ],
    }
}


class TestFindTransitProviders:
    """find_transit_providers extracts advertising routers by tag."""

    def test_single_match(self) -> None:
        result = find_transit_providers(EXTERNAL_DB_ONE_MATCH, tag=100)
        assert result == ["10.130.30.99"]

    def test_two_matches(self) -> None:
        result = find_transit_providers(EXTERNAL_DB_TWO_MATCHES, tag=100)
        assert sorted(result) == ["10.130.30.50", "10.130.30.99"]

    def test_no_match(self) -> None:
        result = find_transit_providers(EXTERNAL_DB_NO_MATCH, tag=100)
        assert result == []

    def test_mixed_tags(self) -> None:
        result = find_transit_providers(EXTERNAL_DB_MIXED, tag=100)
        assert result == ["10.130.30.99"]

    def test_empty_db(self) -> None:
        result = find_transit_providers(EXTERNAL_DB_EMPTY, tag=100)
        assert result == []


class TestResolveNexthops:
    """resolve_nexthops maps advertising routers to backbone IPs."""

    def test_single_router(self) -> None:
        result = resolve_nexthops(["10.130.30.99"], NEIGHBOR_DB)
        assert result == ["172.30.0.100"]

    def test_two_routers(self) -> None:
        result = resolve_nexthops(["10.130.30.99", "10.130.30.50"], NEIGHBOR_DB)
        assert sorted(result) == ["172.30.0.100", "172.30.0.200"]

    def test_unknown_router_skipped(self) -> None:
        result = resolve_nexthops(["10.130.30.99", "10.99.99.99"], NEIGHBOR_DB)
        assert result == ["172.30.0.100"]

    def test_all_unknown(self) -> None:
        result = resolve_nexthops(["10.99.99.99"], NEIGHBOR_DB)
        assert result == []

    def test_resolve_nexthops_silently_drops_non_adjacent_advertising_router(
        self,
    ) -> None:
        """L1-segment containment: advertisingRouter not in the neighbor DB → skipped.

        Invariant: a consumer MUST NOT install a PBR next-hop that points at a
        router in a different L1 segment. OSPF neighbor adjacency is L1-only,
        so absent-from-neighbor-DB == non-adjacent.
        """
        neighbor_db = {
            "neighbors": {
                "10.130.30.20": [
                    {"ifaceAddress": "10.9.20.1", "ifaceName": "wg_tik:10.9.20.2"}
                ],
                # Note: 10.130.30.99 (ipt_server router-id) is absent — not adjacent.
            }
        }

        advertised = ["10.130.30.20", "10.130.30.99"]
        result = resolve_nexthops(advertised, neighbor_db)

        assert result == [
            "10.9.20.1"
        ], "non-adjacent advertising router must be silently dropped"


class TestReconcileRoute:
    """reconcile_route compares desired vs installed and calls pyroute2."""

    def test_desired_equals_installed_noop(self) -> None:
        ipr = MagicMock()
        reconcile_route(
            ipr, desired=["172.30.0.100"], installed=["172.30.0.100"], table=201
        )
        ipr.route.assert_not_called()

    def test_desired_differs_from_installed_replaces(self) -> None:
        ipr = MagicMock()
        reconcile_route(
            ipr, desired=["172.30.0.100"], installed=["172.30.0.200"], table=201
        )
        ipr.route.assert_called_once()
        args = ipr.route.call_args
        assert args[0][0] == "replace"

    def test_desired_empty_installed_non_empty_noop(self) -> None:
        ipr = MagicMock()
        reconcile_route(ipr, desired=[], installed=["172.30.0.100"], table=201)
        ipr.route.assert_not_called()

    def test_desired_non_empty_installed_empty_replaces(self) -> None:
        ipr = MagicMock()
        reconcile_route(ipr, desired=["172.30.0.100"], installed=[], table=201)
        ipr.route.assert_called_once()

    def test_single_nexthop_uses_gateway(self) -> None:
        ipr = MagicMock()
        reconcile_route(ipr, desired=["172.30.0.100"], installed=[], table=201)
        kwargs = ipr.route.call_args[1]
        assert kwargs["family"] == 2
        assert kwargs["gateway"] == "172.30.0.100"
        assert "multipath" not in kwargs

    def test_multiple_nexthops_uses_multipath(self) -> None:
        ipr = MagicMock()
        reconcile_route(
            ipr,
            desired=["172.30.0.100", "172.30.0.200"],
            installed=[],
            table=201,
        )
        kwargs = ipr.route.call_args[1]
        assert kwargs["family"] == 2
        assert "multipath" in kwargs
        assert len(kwargs["multipath"]) == 2


class TestReconcileRules:
    """reconcile_rules adds/removes ip rules for PBR interface-to-table routing."""

    def test_rule_added_when_nexthop_present_and_no_rule_yet(self) -> None:
        """ip rule added for interface when nexthop is present and rule is absent."""
        ipr = MagicMock()
        ipr.get_rules.return_value = []
        reconcile_rules(ipr, interfaces=["wg-firezone"], table=201, has_nexthop=True)
        ipr.rule.assert_called_once()
        args = ipr.rule.call_args
        assert args[0][0] == "add"

    def test_rule_not_added_when_no_nexthop(self) -> None:
        """ip rule not added when has_nexthop is False, even if no rule exists."""
        ipr = MagicMock()
        ipr.get_rules.return_value = []
        reconcile_rules(ipr, interfaces=["wg-firezone"], table=201, has_nexthop=False)
        ipr.rule.assert_not_called()

    def test_rule_removed_when_nexthop_gone(self) -> None:
        """ip rule deleted when has_nexthop is False and rule exists."""
        rule = MagicMock()
        rule.get.side_effect = lambda k, d=None: {
            "attrs": [("FRA_IIFNAME", "wg-firezone"), ("FRA_TABLE", 201)],
            "action": "FR_ACT_TO_TBL",
        }.get(k, d)
        ipr = MagicMock()
        ipr.get_rules.return_value = [rule]
        reconcile_rules(ipr, interfaces=["wg-firezone"], table=201, has_nexthop=False)
        ipr.rule.assert_called_once()
        args = ipr.rule.call_args
        assert args[0][0] == "del"

    def test_noop_when_rule_present_and_nexthop_present(self) -> None:
        """No rule changes when rule already installed and nexthop is present."""
        rule = MagicMock()
        rule.get.side_effect = lambda k, d=None: {
            "attrs": [("FRA_IIFNAME", "wg-firezone"), ("FRA_TABLE", 201)],
            "action": "FR_ACT_TO_TBL",
        }.get(k, d)
        ipr = MagicMock()
        ipr.get_rules.return_value = [rule]
        reconcile_rules(ipr, interfaces=["wg-firezone"], table=201, has_nexthop=True)
        ipr.rule.assert_not_called()

    def test_noop_when_rule_present_with_numeric_action(self) -> None:
        """No rule changes when rule has numeric action=1 (pyroute2 real format)."""
        rule = MagicMock()
        rule.get.side_effect = lambda k, d=None: {
            "attrs": [("FRA_IIFNAME", "wg-firezone"), ("FRA_TABLE", 201)],
            "action": 1,  # pyroute2 returns integer, not string
        }.get(k, d)
        ipr = MagicMock()
        ipr.get_rules.return_value = [rule]
        reconcile_rules(ipr, interfaces=["wg-firezone"], table=201, has_nexthop=True)
        ipr.rule.assert_not_called()

    def test_multiple_interfaces(self) -> None:
        """ip rule added for each interface when nexthop present."""
        ipr = MagicMock()
        ipr.get_rules.return_value = []
        reconcile_rules(
            ipr,
            interfaces=["wg-firezone", "wg_tik"],
            table=201,
            has_nexthop=True,
        )
        assert ipr.rule.call_count == 2


class TestGetInstalledNexthops:
    """get_installed_nexthops reads nexthops from pyroute2 kernel routes."""

    def _make_route(
        self, gateway: str | None = None, multipath: list | None = None
    ) -> MagicMock:
        """Build a mock pyroute2 route object."""
        attrs = []
        if gateway:
            attrs.append(("RTA_GATEWAY", gateway))
        if multipath:
            attrs.append(("RTA_MULTIPATH", multipath))
        route = MagicMock()
        route.get.side_effect = lambda key, default=None: dict(
            [
                ("attrs", attrs),
            ]
        ).get(key, default)
        return route

    def test_single_gateway_route(self) -> None:
        ipr = MagicMock()
        ipr.get_routes.return_value = [self._make_route(gateway="172.30.0.100")]
        result = get_installed_nexthops(ipr, table=201)
        assert result == ["172.30.0.100"]

    def test_multipath_route(self) -> None:
        mp_entries = [
            {"gateway": "172.30.0.100", "attrs": []},
            {"gateway": "172.30.0.200", "attrs": []},
        ]
        ipr = MagicMock()
        ipr.get_routes.return_value = [self._make_route(multipath=mp_entries)]
        result = get_installed_nexthops(ipr, table=201)
        assert sorted(result) == ["172.30.0.100", "172.30.0.200"]

    def test_empty_table(self) -> None:
        ipr = MagicMock()
        ipr.get_routes.return_value = []
        result = get_installed_nexthops(ipr, table=201)
        assert result == []

    def test_returns_sorted(self) -> None:
        mp_entries = [
            {"gateway": "172.30.0.200", "attrs": []},
            {"gateway": "172.30.0.100", "attrs": []},
        ]
        ipr = MagicMock()
        ipr.get_routes.return_value = [self._make_route(multipath=mp_entries)]
        result = get_installed_nexthops(ipr, table=201)
        assert result == ["172.30.0.100", "172.30.0.200"]


# ---------------------------------------------------------------------------
# resolve_nexthops_from_ospf_routes (recursive ASBR fallback)
# ---------------------------------------------------------------------------

OSPF_ROUTE_DB_BACKBONE_ASBRS = {
    "10.130.30.23": {
        "routeType": "R ",
        "cost": 20,
        "area": "0.0.0.0",
        "routerType": "asbr",
        "nexthops": [{"ip": "192.0.2.5", "via": "backbone"}],
    },
    "10.130.30.33": {
        "routeType": "R ",
        "cost": 20,
        "area": "0.0.0.0",
        "routerType": "asbr",
        "nexthops": [{"ip": "192.0.2.4", "via": "backbone"}],
    },
    "10.9.20.2": {
        "routeType": "R ",
        "cost": 10,
        "area": "0.0.0.0",
        "routerType": "asbr",
        "nexthops": [{"ip": "10.9.20.2", "via": "wg-hub-ros"}],
    },
    "0.0.0.0/0": {
        "routeType": "N E2",
        "cost": 10,
        "type2cost": 100,
        "tag": 0,
        "nexthops": [
            {
                "ip": "192.0.2.2",
                "via": "backbone",
                "advertisedRouter": "10.130.30.99",
            }
        ],
    },
}


class TestResolveNexthopsFromOspfRoutes:
    """resolve_nexthops_from_ospf_routes maps ASBR router routes to next-hops."""

    def test_resolves_non_adjacent_provider_router_ids_via_ospf_routes(self) -> None:
        result = resolve_nexthops_from_ospf_routes(
            ["10.130.30.23", "10.130.30.33"], OSPF_ROUTE_DB_BACKBONE_ASBRS
        )

        assert sorted(result) == ["192.0.2.4", "192.0.2.5"]

    def test_skips_provider_routes_not_reached_over_backbone(self) -> None:
        result = resolve_nexthops_from_ospf_routes(
            ["10.9.20.2"], OSPF_ROUTE_DB_BACKBONE_ASBRS
        )

        assert result == []


class TestResolveDefaultNexthopsFromOspfRoutes:
    """resolve_default_nexthops_from_ospf_routes maps the selected default."""

    def test_resolves_selected_default_route_nexthop(self) -> None:
        result = resolve_default_nexthops_from_ospf_routes(OSPF_ROUTE_DB_BACKBONE_ASBRS)

        assert result == ["192.0.2.2"]

    def test_skips_default_routes_not_reached_over_backbone(self) -> None:
        route_db = {
            "0.0.0.0/0": {
                "nexthops": [{"ip": "10.9.20.2", "via": "wg-hub-ros"}],
            }
        }

        result = resolve_default_nexthops_from_ospf_routes(route_db)

        assert result == []
