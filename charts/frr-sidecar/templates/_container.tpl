{{/*
Render the FRR/OSPF sidecar container as a single list element.

Usage (inside spec.template.spec.containers, with 8-space indent):
    {{- include "frr-sidecar.container" (dict
          "image" .Values.images.frr
          "ospf" .Values.ospf
          "transit" .Values.transit
        ) | nindent 8 }}

The template is a no-op when `.ospf` is nil. Callers MUST include
unconditionally (no caller-side {{- if .Values.ospf }} wrapper).

Required dict keys:
    image:   container image reference (string; empty/omitted ⇒ frr-sidecar.defaultImage tag)
    ospf:    dict consumed by frr-sidecar.frrConf
    transit: dict with `interfaces: [string]` (optional)

PBR_TRANSIT_TAG is sourced from the shared named template frr-sidecar.transitTag
defined in _frrconf.tpl (single source of truth; the docker-era ospf_injector
config.py is removed). The transit_watcher.py (modules/frr-sidecar/image/)
keys off this tag to install `ip rule iif <iface> lookup 201`.

Capability set NET_ADMIN/NET_RAW/SYS_ADMIN matches the historical
ospf_injector consumer.py contract; without SYS_ADMIN the FRR daemons
fail `cap_set_proc` on startup.
*/}}
{{- define "frr-sidecar.container" -}}
{{- if and (and .ospf .ospf.transit_provider) (and .transit (gt (len (default (list) .transit.interfaces)) 0)) -}}
{{- fail (printf "frr-sidecar: workload cannot be both transit provider (ospf.transit_provider=true) and transit consumer (transit.interfaces=%v) at the same time. See modules/frr-sidecar/charts/frr-sidecar/templates/_container.tpl." .transit.interfaces) -}}
{{- end -}}
{{- if .ospf -}}
- name: frr-sidecar
  image: {{ (default "" .image | trim) | default (include "frr-sidecar.defaultImage" . | trim) | quote }}
  imagePullPolicy: IfNotPresent
  {{- with .transit }}
  {{- if .interfaces }}
  env:
    - name: PBR_TRANSIT_TAG
      value: {{ include "frr-sidecar.transitTag" . | quote }}
    - name: PBR_TRANSIT_INTERFACES
      value: {{ join "," .interfaces | quote }}
  {{- end }}
  {{- end }}
  volumeMounts:
    - name: frr-source
      mountPath: /etc/frr-source
      readOnly: true
  securityContext:
    capabilities:
      add: ["NET_ADMIN", "NET_RAW", "SYS_ADMIN"]
{{- end -}}
{{- end }}
