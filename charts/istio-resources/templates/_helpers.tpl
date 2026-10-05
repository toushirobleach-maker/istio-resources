{{/*
Expand the name of the chart.
*/}}
{{- define "istio-resources.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this
(by the DNS naming spec).
*/}}
{{- define "istio-resources.fullname" -}}
{{- printf "%s-%s" .Chart.Name .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "istio-resources.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Optional namespace: falls back to the release namespace when not set in values.
*/}}
{{- define "istio-resources.namespace" -}}
{{- default .Release.Namespace .Values.namespace -}}
{{- end -}}

{{/*
Common labels applied to every resource.
*/}}
{{- define "istio-resources.labels" -}}
helm.sh/chart: {{ include "istio-resources.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: istio
{{- with .Chart.AppVersion }}
app.kubernetes.io/version: {{ . | quote }}
{{- end }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
Selector labels (for resources that support selectors).
*/}}
{{- define "istio-resources.selectorLabels" -}}
app.kubernetes.io/name: {{ include "istio-resources.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Common annotations applied to every resource.
*/}}
{{- define "istio-resources.annotations" -}}
{{- with .Values.commonAnnotations }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/* A non-null spec object replaces the entire generated spec, including {}. */}}
{{- define "istio-resources.hasSpec" -}}
{{- if and (hasKey . "spec") (ne .spec nil) -}}
{{- if not (kindIs "map" .spec) -}}
{{- fail "spec must be a YAML object, or null to use legacy values" -}}
{{- end -}}
true
{{- end -}}
{{- end -}}

{{/* Generated egress children use the effective ServiceEntry hosts and ports. */}}
{{- define "istio-resources.egressConfig" -}}
{{- if include "istio-resources.hasSpec" . -}}
{{- toYaml .spec -}}
{{- else -}}
{{- toYaml . -}}
{{- end -}}
{{- end -}}
