{{- define "frr-sidecar.transitTag" -}}201{{- end -}}
{{- define "frr-sidecar.transitMetric" -}}100{{- end -}}
{{- define "frr-sidecar.transitMetricType" -}}2{{- end -}}
{{- define "frr-sidecar.transitRouteMap" -}}TRANSIT_ORIGINATE{{- end -}}
{{/*
Transit constants (tag=201, metric=100, metric-type=2, route-map=TRANSIT_ORIGINATE)
are defined once as named templates above (frr-sidecar.transitTag / transitMetric /
transitMetricType / transitRouteMap) and referenced from both this template and
_container.tpl via include. Live image at modules/frr-sidecar/image/.

Render an FRR `frr.conf` body from an `ospf` dict.

Usage:
    include "frr-sidecar.frrConf" .Values.ospf

Expected dict shape:
    interfaces: [string]
    passive_interfaces: [string]   # optional
    router_id: string
    redistribute: [string]         # optional
    default_originate: bool        # optional
    transit_provider: bool         # optional

Transit-provider mechanism (FRR 10.6, garuda-internal#50, #55):

The compose-era contract (now canonically rendered by this template;
the docker-era injector ospf_block.conf.j2 is removed)
defines:

  route-map TRANSIT_ORIGINATE permit 10
   set tag 201
   set metric 100
   set metric-type type-2

   router ospf
    default-information originate always metric 100 metric-type 2 route-map TRANSIT_ORIGINATE

Live A/B testing against the compose-era hub (same FRR 10.6.0_git
binary) isolated the actual quirk: it is `redistribute kernel` on
the transit provider that breaks the tag, not the inline metric-type
on `default-information originate`. With `redistribute kernel`, ospfd
emits an untagged Type-5 LSA for 0.0.0.0/0 from the kernel
redistribution path which shadows the tagged
`default-information originate ... route-map` emission. The k3s
ipt-server chart therefore deliberately omits `redistribute kernel`
(see modules/ipt_server/kube/charts/ipt-server/templates/configmap-frr.yaml
and deployment.yaml). The compose-era hub appears unaffected by
environmental coincidence: there the kernel default and the
default-information emission point at the same border-egress prefix,
so FRR consolidates the two and the route-map tag survives.

The consumer watcher
(modules/frr-sidecar/image/transit_watcher.py) keeps
a defense-in-depth fallback chain (direct neighbor → selected OSPF
default route → tagged ASBR via backbone) so that any future regression
in the provider-side tagging is contained at the consumer layer.

`zebra nexthop proto only` confines zebra's kernel-nexthop tracking to
its own protocols; without it, zebra reclaims kernel nhids used by
other routes and rewrites them during RIB resolution, overwriting
ipt-server's NHG members within ~1s of installation. Parity with the
docker-era preamble (ospf_injector removed; this template is now the
canonical source).

When `transit_provider=true`, `default_originate` is ignored — the
`default-information originate always ... route-map` advertisement
subsumes it.
*/}}
{{- define "frr-sidecar.frrConf" -}}
frr defaults traditional
log file /tmp/frr.log
zebra nexthop proto only
{{- if .transit_provider }}

route-map {{ include "frr-sidecar.transitRouteMap" . }} permit 10
 set tag {{ include "frr-sidecar.transitTag" . }}
 set metric {{ include "frr-sidecar.transitMetric" . }}
 set metric-type type-{{ include "frr-sidecar.transitMetricType" . }}
{{- end }}
{{ range $iface := .interfaces -}}
interface {{ $iface }}
 ip ospf area 0.0.0.0
{{ if has $iface ($.passive_interfaces | default (list)) -}}
 ip ospf passive
{{ else -}}
 ip ospf hello-interval 5
 ip ospf dead-interval 15
 ip ospf mtu-ignore
{{ end -}}
{{ end -}}
router ospf
 ospf router-id {{ .router_id }}
{{ range $r := .redistribute | default (list) -}}
 redistribute {{ $r }}
{{ end -}}
{{- if .transit_provider }}
 default-information originate always metric {{ include "frr-sidecar.transitMetric" . }} metric-type {{ include "frr-sidecar.transitMetricType" . }} route-map {{ include "frr-sidecar.transitRouteMap" . }}
{{- else if .default_originate }}
 default-information originate
{{- end }}
{{- end }}
