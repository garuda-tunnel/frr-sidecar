{{/*
Render an FRR ConfigMap resource.

Usage:
    include "frr-sidecar.configmap" (dict "name" .Values.name "namespace" .Values.namespace "ospf" .Values.ospf)
*/}}
{{- define "frr-sidecar.configmap" -}}
{{- if .ospf -}}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ printf "%s-frr" .name | quote }}
  namespace: {{ .namespace | quote }}
data:
  frr.conf: |
{{ include "frr-sidecar.frrConf" .ospf | indent 4 }}
  daemons: |
    zebra=yes
    ospfd=yes
  vtysh.conf: |
    service integrated-vtysh-config
{{- end -}}
{{- end -}}
