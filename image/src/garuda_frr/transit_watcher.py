"""Transit route watcher: polls OSPF LSDB and reconciles kernel PBR routes.

Runs as a background process inside the FRR sidecar container. Discovers
transit provider nexthop IPs from OSPF External LSAs (matched by tag) and
programs them into a dedicated kernel routing table via pyroute2.

Configuration via environment variables:
    PBR_TRANSIT_TAG  (required): OSPF External LSA tag to match.
    PBR_TABLE        (optional, default 201): kernel routing table number.
    POLL_INTERVAL    (optional, default 5): seconds between poll cycles.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

import click

from garuda_frr.utils import csv_split
from garuda_frr.vtysh_client import VtyshError, vtysh_json

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("transit-watcher")

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

# Default kernel routing table number for transit PBR. Overridable via
# PBR_TABLE env.
_PBR_TABLE_DEFAULT = "201"

# FR_ACT_TO_TBL value from <linux/fib_rules.h> — "route to table". pyroute2
# may return rule action as either this integer or the string
# "FR_ACT_TO_TBL"; we accept both.
_FR_ACT_TO_TBL = 1

# ip rule priority. Below the default fallback (32766) but safely above 0,
# chosen so our rules coexist with any FRR-managed rules in the same netns.
_RULE_PRIORITY = 29000


def find_transit_providers(external_db: dict, tag: int) -> list[str]:
    """Extract advertising routers from External LSAs matching the given tag.

    Args:
        external_db: parsed JSON from 'show ip ospf database external json'.
        tag: OSPF External Route Tag to match.

    Returns:
        List of advertising router IDs (strings) with matching tag and
        linkStateId == "0.0.0.0".
    """
    providers: list[str] = []
    for lsa in external_db.get("asExternalLinkStates", []):
        if lsa.get("linkStateId") == "0.0.0.0" and lsa.get("externalRouteTag") == tag:
            router = lsa.get("advertisingRouter")
            if router:
                providers.append(router)
    return providers


def resolve_nexthops(advertising_routers: list[str], neighbor_db: dict) -> list[str]:
    """Resolve advertising router IDs to backbone interface addresses.

    Args:
        advertising_routers: list of OSPF router IDs.
        neighbor_db: parsed JSON from 'show ip ospf neighbor json'.

    Returns:
        List of resolved nexthop IPs (backbone ifaceAddress values).
        Routers not found in the neighbor table are silently skipped.
    """
    neighbors = neighbor_db.get("neighbors", {})
    nexthops: list[str] = []
    for router_id in advertising_routers:
        entries = neighbors.get(router_id, [])
        if entries:
            addr = entries[0].get("ifaceAddress")
            if addr:
                nexthops.append(addr)
    return nexthops


def resolve_nexthops_from_ospf_routes(
    advertising_routers: list[str], ospf_route_db: dict
) -> list[str]:
    """Resolve advertising router IDs through the OSPF route table.

    Fallback for tagged ASBRs that are not direct OSPF neighbors of the
    consumer but are reachable through a direct backbone next-hop. Used
    when the FRR self-LSA on the tag provider carries tag=0 (FRR 10.6
    does not apply route-map set actions to self-originated default
    LSAs), so the watcher cannot find the local ipt-server in the
    External LSA table by tag and must walk the OSPF route table instead.
    """
    nexthops: list[str] = []
    for router_id in advertising_routers:
        route = ospf_route_db.get(router_id, {})
        for nexthop in route.get("nexthops", []):
            if nexthop.get("via") != "backbone":
                continue
            addr = nexthop.get("ip")
            if addr and addr.strip():
                nexthops.append(addr)
    return sorted(set(nexthops))


def resolve_default_nexthops_from_ospf_routes(ospf_route_db: dict) -> list[str]:
    """Resolve the selected OSPF default route through direct backbone next-hops.

    First-line fallback: use the already-selected OSPF default route
    next-hop (the route the local FRR has chosen to install) regardless
    of the LSA tag. This is the cheapest and most accurate way to
    discover the transit provider when its self-LSA tag is wrong.
    """
    default_route = ospf_route_db.get("0.0.0.0/0", {})
    nexthops: list[str] = []
    for nexthop in default_route.get("nexthops", []):
        if nexthop.get("via") != "backbone":
            continue
        addr = nexthop.get("ip")
        if addr and addr.strip():
            nexthops.append(addr)
    return sorted(set(nexthops))


def get_installed_nexthops(ipr: object, table: int) -> list[str]:
    """Read the current default route nexthops from a kernel routing table.

    Args:
        ipr: pyroute2 IPRoute instance.
        table: kernel routing table number.

    Returns:
        Sorted list of nexthop IPs currently installed in the table.
    """
    routes = ipr.get_routes(family=2, table=table, dst_len=0)  # type: ignore[attr-defined]
    nexthops: list[str] = []
    for route in routes:
        attrs = dict(route.get("attrs", []))
        multipath = attrs.get("RTA_MULTIPATH")
        if multipath:
            for mp in multipath:
                gw = mp.get("gateway") or dict(mp.get("attrs", [])).get("RTA_GATEWAY")
                if gw:
                    nexthops.append(gw)
        else:
            gw = attrs.get("RTA_GATEWAY")
            if gw:
                nexthops.append(gw)
    return sorted(nexthops)


def reconcile_route(
    ipr: object,
    desired: list[str],
    installed: list[str],
    table: int,
) -> None:
    """Reconcile kernel route: replace if desired differs from installed.

    Does nothing if desired is empty (graceful degradation) or if desired
    equals installed (no-op).

    Args:
        ipr: pyroute2 IPRoute instance.
        desired: sorted list of desired nexthop IPs.
        installed: sorted list of currently installed nexthop IPs.
        table: kernel routing table number.
    """
    if not desired:
        return
    if sorted(desired) == sorted(installed):
        return

    if len(desired) == 1:
        ipr.route(  # type: ignore[attr-defined]
            "replace", family=2, dst="default", gateway=desired[0], table=table
        )
    else:
        multipath = [{"gateway": ip} for ip in sorted(desired)]
        ipr.route(  # type: ignore[attr-defined]
            "replace", family=2, dst="default", multipath=multipath, table=table
        )
    log.info("route reconciled: %s -> %s (table %d)", installed, desired, table)


def _rule_matches(rule: object, iface: str, table: int) -> bool:
    """Return True if the given pyroute2 rule matches iface and table.

    Args:
        rule: pyroute2 rule object.
        iface: interface name to match on FRA_IIFNAME.
        table: routing table number to match on FRA_TABLE.

    Returns:
        True if rule action is FR_ACT_TO_TBL (1), FRA_IIFNAME equals iface,
        and FRA_TABLE equals table.
    """
    attrs = dict(rule.get("attrs", []))  # type: ignore[union-attr]
    action = rule.get("action")  # type: ignore[union-attr]
    # pyroute2 returns action as integer (1 = FR_ACT_TO_TBL) or string
    action_match = action in (_FR_ACT_TO_TBL, "FR_ACT_TO_TBL")
    return (
        action_match
        and attrs.get("FRA_IIFNAME") == iface
        and attrs.get("FRA_TABLE") == table
    )


def reconcile_rules(
    ipr: object,
    interfaces: list[str],
    table: int,
    has_nexthop: bool,
) -> None:
    """Add or remove ip rules routing interface traffic to a kernel table.

    When has_nexthop is True: ensures a rule exists for each interface.
    When has_nexthop is False: removes any existing rules for the interfaces.

    Does nothing (no add or remove) when the desired state already matches
    installed state.

    Args:
        ipr: pyroute2 IPRoute instance.
        interfaces: list of ingress interface names.
        table: kernel routing table number.
        has_nexthop: True when a transit nexthop is available.
    """
    existing = ipr.get_rules(family=2)  # type: ignore[attr-defined]

    for iface in interfaces:
        installed = any(_rule_matches(r, iface, table) for r in existing)

        if has_nexthop and not installed:
            ipr.rule(  # type: ignore[attr-defined]
                "add",
                iifname=iface,
                table=table,
                priority=_RULE_PRIORITY,
            )
            log.info("ip rule added: iif %s table %d", iface, table)
        elif not has_nexthop and installed:
            ipr.rule(  # type: ignore[attr-defined]
                "del",
                iifname=iface,
                table=table,
                priority=_RULE_PRIORITY,
            )
            log.info("ip rule removed: iif %s table %d", iface, table)


def main() -> None:
    """Main poll loop: resolve desired nexthops from LSDB, reconcile kernel route and rules."""
    tag = int(os.environ["PBR_TRANSIT_TAG"])
    table = int(os.environ.get("PBR_TABLE", _PBR_TABLE_DEFAULT))
    interval = int(os.environ.get("POLL_INTERVAL", "5"))
    raw_ifaces = os.environ.get("PBR_TRANSIT_INTERFACES", "")
    interfaces = csv_split(raw_ifaces)

    log.info(
        "starting: tag=%d table=%d interval=%ds interfaces=%s",
        tag,
        table,
        interval,
        interfaces or "(none)",
    )

    from pyroute2 import IPRoute

    with IPRoute() as ipr:
        while True:
            try:
                external_db = vtysh_json("show ip ospf database external json")
                providers = find_transit_providers(external_db, tag)
                log.debug("providers: %s", providers)

                if providers:
                    neighbor_db = vtysh_json("show ip ospf neighbor json")
                    desired = resolve_nexthops(providers, neighbor_db)
                    if not desired:
                        # FRR 10.6 may emit self-LSA tag=0 for the local
                        # default-information-originate ASBR even when the
                        # provider config sets `set tag 201`. Fall back to
                        # the OSPF route table: first the selected default
                        # route (most accurate), then ASBR routes reached
                        # over the backbone (last resort).
                        ospf_route_db = vtysh_json("show ip ospf route json")
                        desired = resolve_default_nexthops_from_ospf_routes(
                            ospf_route_db
                        )
                        if not desired:
                            desired = resolve_nexthops_from_ospf_routes(
                                providers, ospf_route_db
                            )
                    desired = sorted(set(desired))
                else:
                    desired = []

                installed = get_installed_nexthops(ipr, table)
                log.debug("desired=%s installed=%s", desired, installed)

                reconcile_route(ipr, desired, installed, table)

                if interfaces:
                    reconcile_rules(ipr, interfaces, table, has_nexthop=bool(desired))

            except VtyshError as exc:
                log.warning("vtysh failed: %s", exc)
            except subprocess.TimeoutExpired as exc:
                log.warning("vtysh timed out: %s", exc)
            # Daemon loop must survive every poll cycle — log and continue on any error.
            except Exception as exc:
                log.error("unexpected error in poll cycle: %s", exc, exc_info=True)

            time.sleep(interval)


@click.command()
def cli() -> None:
    """garuda-transit-watcher: poll OSPF LSDB and reconcile kernel PBR routes.

    Configuration via environment variables: PBR_TRANSIT_TAG (required),
    PBR_TABLE (optional, default 201), POLL_INTERVAL (optional, default 5),
    PBR_TRANSIT_INTERFACES (optional, CSV of interface names).
    """
    main()


if __name__ == "__main__":
    main()
