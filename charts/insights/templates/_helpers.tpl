{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "insights.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "insights.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "insights.influxdb_url" -}}
{{- $context  := dict "Values" .Values.influxdb "Chart" (dict "Name" "influxdb") "Release" .Release  "Capabilities" .Capabilities -}}
{{- if and .Values.influxdb .Values.influxdb.enabled -}}
{{-   $influxdb := include "influxdb.fullname" $context -}}
{{-   $hostname := default (printf "%s.%s.svc" $influxdb .Release.Namespace) .Values.nuoca.influxdb.host -}}
{{-   $port     := default 8086 .Values.nuoca.influxdb.port -}}
{{-   printf "http://%s:%d" $hostname $port -}}
{{- else -}}
{{-   $hostname := default (printf "influxdb.%s.svc" .Release.Namespace) .Values.nuoca.influxdb.host -}}
{{-   $port     := default 8086 .Values.nuoca.influxdb.port -}}
{{-   printf "http://%s:%d" $hostname $port -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "insights.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "insights.labels" -}}
helm.sh/chart: {{ include "insights.chart" . }}
{{ include "insights.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "insights.selectorLabels" -}}
app.kubernetes.io/name: {{ include "insights.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Namespace for the dashboards, this should be same as namespace for
grafana is grafana location is overridded.
*/}}
{{- define "insights.namespace" -}}
  {{ default .Release.Namespace .Values.grafana.namespaceOverride }}
{{- end -}}
