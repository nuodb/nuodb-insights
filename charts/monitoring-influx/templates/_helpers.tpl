{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "monitoring-influx.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "monitoring-influx.fullname" -}}
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

{{- define "monitoring-influx.influxdb_url" -}}
{{- $cluster  := "cluster.local" -}}
{{- $hostname := default (printf "%s-influxdb.%s.svc.%s" .Release.Name .Release.Namespace $cluster) .Values.nuoca.influxdb.host -}}
{{- $port     := default 8086 .Values.nuoca.influxdb.port -}}
{{- printf "http://%s:%d" $hostname $port -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "monitoring-influx.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "monitoring-influx.labels" -}}
helm.sh/chart: {{ include "monitoring-influx.chart" . }}
{{ include "monitoring-influx.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "monitoring-influx.selectorLabels" -}}
app.kubernetes.io/name: {{ include "monitoring-influx.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Namespace for the dashboards, this should be same as namespace for
grafana is grafana location is overridded.
*/}}
{{- define "monitoring-influx.namespace" -}}
  {{ default .Release.Namespace .Values.grafana.namespaceOverride }}
{{- end -}}