{{/*
Render the FRR sidecar volume entries.

Usage (inside spec.template.spec.volumes):
    include "frr-sidecar.volume" (dict "name" .Values.name "ospf" .Values.ospf)

Emits the `frr-source` ConfigMap volume when `.ospf` is set. Returns
empty otherwise so the caller's `volumes:` field is omitted entirely.
*/}}
{{- define "frr-sidecar.volume" -}}
{{- if .ospf -}}
- name: frr-source
  configMap:
    name: {{ printf "%s-frr" .name }}
{{- end -}}
{{- end -}}
