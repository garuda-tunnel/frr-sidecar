#!/bin/sh
# FRR sidecar entrypoint.
# Configuration is delivered exclusively via a mounted ConfigMap at
# /etc/frr-source/ (frr.conf, daemons, vtysh.conf). The legacy env-vars
# path (FRR_CONF_B64/DAEMONS_B64/VTYSH_CONF_B64) was removed in
# garuda-internal#46 after all consumers migrated to ConfigMap+volume.

set -e

mkdir -p /etc/frr

if [ ! -f /etc/frr-source/frr.conf ]; then
    echo "FATAL: no FRR config at /etc/frr-source/frr.conf (ConfigMap+volume required since #46)" >&2
    exit 1
fi

echo "Using ConfigMap configuration from /etc/frr-source/"
cp /etc/frr-source/frr.conf    /etc/frr/frr.conf
cp /etc/frr-source/daemons     /etc/frr/daemons
cp /etc/frr-source/vtysh.conf  /etc/frr/vtysh.conf

# Resolve actual backbone interface name.
if [ -n "${BACKBONE_IP:-}" ]; then
    actual_iface=$(ip -j -4 addr show | python3 -c "
import json, sys
data = json.load(sys.stdin)
ip = '$BACKBONE_IP'
for iface in data:
    for addr in iface.get('addr_info', []):
        if addr.get('local', '') == ip:
            print(iface['ifname'])
            sys.exit(0)
")
    if [ -n "$actual_iface" ] && [ "$actual_iface" != "backbone" ]; then
        echo "backbone interface resolved: backbone -> $actual_iface (IP=$BACKBONE_IP)"
        sed -i "s/^interface backbone$/interface $actual_iface/" /etc/frr/frr.conf
    elif [ -z "$actual_iface" ]; then
        echo "WARNING: could not find interface for BACKBONE_IP=$BACKBONE_IP" >&2
    fi
fi

# Set correct ownership and permissions
chown -R frr:frr /etc/frr
chmod 640 /etc/frr/frr.conf /etc/frr/daemons /etc/frr/vtysh.conf

# Start transit watcher if PBR_TRANSIT_TAG is configured.
# The watcher polls OSPF LSDB for tagged default routes and programs
# the corresponding nexthop into the PBR kernel routing table.
if [ -n "${PBR_TRANSIT_TAG:-}" ]; then
    python3 /usr/lib/frr/transit_watcher.py &
fi

# Start vty HTTP bridge: exposes vtysh to sister containers on 127.0.0.1:7890.
python3 /usr/lib/frr/vty_bridge.py &

# Start FRR via its standard Docker entrypoint
exec /usr/lib/frr/docker-start
