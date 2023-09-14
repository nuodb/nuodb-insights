package minikube

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/gruntwork-io/terratest/modules/helm"
	"github.com/gruntwork-io/terratest/modules/k8s"
	"github.com/gruntwork-io/terratest/modules/random"
	"github.com/nuodb/nuodb-helm-charts/v3/test/testlib"
	v1 "k8s.io/api/core/v1"
)

func getFunctionCallerName() string {
	pc, _, _, _ := runtime.Caller(3)
	nameFull := runtime.FuncForPC(pc).Name() // main.foo
	nameEnd := filepath.Ext(nameFull)        // .foo
	name := strings.TrimPrefix(nameEnd, ".") // foo

	return name
}

func StartInsights(t *testing.T, options *helm.Options, namespace string) (string, string) {
	return startInsightsTemplate(t, options, namespace, func(t *testing.T, options *helm.Options, helmChartReleaseName string) {
		if options.Version == "" {
			helm.Install(t, options, INSIGHTS_HELM_CHART_PATH, helmChartReleaseName)
		} else {
			helm.Install(t, options, "nuodb/insights ", helmChartReleaseName)
		}
	})
}

type InsightsInstallationStep func(t *testing.T, options *helm.Options, helmChartReleaseName string)

func startInsightsTemplate(t *testing.T, options *helm.Options, namespace string, installStep InsightsInstallationStep) (helmChartReleaseName string, namespaceName string) {
	randomSuffix := strings.ToLower(random.UniqueId())

	helmChartReleaseName = fmt.Sprintf("insights-%s", randomSuffix)

	if namespace == "" {
		callerName := getFunctionCallerName()
		namespaceName = fmt.Sprintf("%s-%s", strings.ToLower(callerName), randomSuffix)

		testlib.CreateNamespace(t, namespaceName)
	} else {
		namespaceName = namespace
	}

	kubectlOptions := k8s.NewKubectlOptions("", "", namespaceName)
	options.KubectlOptions = kubectlOptions
	options.KubectlOptions.Namespace = namespaceName

	installStep(t, options, helmChartReleaseName)

	testlib.AddTeardown(TEARDOWN_INSIGHTS, func() {
		helm.Delete(t, options, helmChartReleaseName, true)
	})

	if options.SetValues["grafana.enabled"] != "false" {
		testlib.AwaitNrReplicasScheduled(t, namespaceName, "grafana", 1)
		grafanaPodName := testlib.GetPodName(t, namespaceName, "grafana")
		testlib.AwaitPodUp(t, namespaceName, grafanaPodName, 300*time.Second)
		go testlib.GetAppLog(t, namespaceName, grafanaPodName, "datasources",
			&v1.PodLogOptions{Follow: true, Container: "grafana-sc-datasources"})
	}
	if options.SetValues["influxdb.enabled"] != "false" {
		testlib.AwaitNrReplicasScheduled(t, namespaceName, "influxdb", 1)
		influxPodName := fmt.Sprintf("%s-influxdb2-0", helmChartReleaseName)
		testlib.AwaitPodUp(t, namespaceName, influxPodName, 300*time.Second)
		go testlib.GetAppLog(t, namespaceName, influxPodName, "", &v1.PodLogOptions{Follow: true})
	}
	return
}

func InjectNuoDBHelmChartsVersion(t *testing.T, options *helm.Options) {
	if options.Version == "" {
		version := os.Getenv("NUODB_HELM_CHARTS_VERSION")
		if matched, _ := regexp.MatchString(`^([0-9]+\.?){1,3}$`, version); matched {
			// Use already released version
			t.Logf("Testing with NuoDB Helm Charts v%s", version)
			options.Version = version
		}
	}
}

func ExcuteInfluxDBQueryE(t *testing.T, namespace string, influxPodName string, query string, influxArgs ...string) (string, error) {
	kubectlOptions := k8s.NewKubectlOptions("", "", namespace)
	var kubectlArgs []string
	kubectlArgs = append(kubectlArgs, "exec", influxPodName, "--", "influx", "query", query)
	kubectlArgs = append(kubectlArgs, influxArgs...)
	return k8s.RunKubectlAndGetOutputE(t, kubectlOptions, kubectlArgs...)
}
