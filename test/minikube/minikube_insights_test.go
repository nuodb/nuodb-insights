package minikube

import (
	"fmt"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/gruntwork-io/terratest/modules/helm"
	"github.com/gruntwork-io/terratest/modules/k8s"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"github.com/nuodb/nuodb-helm-charts/v3/test/testlib"
)

const YCSB_CONTROLLER_NAME = "ycsb-load"

func startAndScaleYCSB(t *testing.T, namespaceName string, options *helm.Options) {
	testlib.StartYCSBWorkload(t, namespaceName, options)
	ycsbNrReplicas := 1
	if options.SetValues["ycsb.replicas"] != "" {
		replicas, err := strconv.Atoi(options.SetValues["ycsb.replicas"])
		if err == nil {
			ycsbNrReplicas = replicas
		}
	}

	if ycsbNrReplicas > 0 {
		kubectlOptions := k8s.NewKubectlOptions("", "", namespaceName)

		testlib.AddDiagnosticTeardown(testlib.TEARDOWN_YCSB, t, func() {
			_ = k8s.RunKubectlE(t, kubectlOptions, "describe", "replicationcontroller", YCSB_CONTROLLER_NAME)
		})

		testlib.AwaitNrReplicasScheduled(t, namespaceName, YCSB_CONTROLLER_NAME, ycsbNrReplicas)

		// find at least 1 YCSB pod
		podName := testlib.GetPodName(t, namespaceName, YCSB_CONTROLLER_NAME)

		testlib.AddDiagnosticTeardown(testlib.TEARDOWN_YCSB, t, func() {
			_ = k8s.RunKubectlE(t, kubectlOptions, "describe", "pod", podName)
		})

		testlib.AwaitPodUp(t, namespaceName, podName, 300*time.Second)

		// wait for any other replicas to come up
		testlib.AwaitNrReplicasReady(t, namespaceName, YCSB_CONTROLLER_NAME, ycsbNrReplicas)
	}
}

func checkMetricPresent(t *testing.T, namespace string, influxPodName string, influxDatabase string,
	measurement string, database string, host string, metric string) bool {
	queryString := fmt.Sprintf("select count(%s) from \"%s\" where host = '%s'", metric, measurement, host)
	dbTagName := "db"
	if influxDatabase == "nuodb_internal" {
		// DB tag name is different in nuodb_internal database
		dbTagName = "dbname"
	}
	if measurement != "nuodb_thread" {
		// There is no db tag for nuodb_thread measurement
		queryString = fmt.Sprintf("%s and %s = '%s'", queryString, dbTagName, database)
	}
	output, err := ExcuteInfluxDBQueryE(t, namespace, influxPodName, queryString, "-database", influxDatabase, "-format", "csv")
	if err != nil {
		t.Logf("Unexpected error received from InfluxDB: %s", err)
		return false
	}
	lines := strings.Split(output, "\n")
	if len(lines) > 1 {
		// The output format will be `name,time,count`
		count, err := strconv.Atoi(strings.Split(lines[1], ",")[2])
		require.NoError(t, err)
		if int(count) > 0 {
			t.Logf("Found %d lines for measurement=%s, metric=%s, db=%s, host=%s", count, measurement, metric, database, host)
			return true
		}
	}

	return false
}

func checkMeasurementsPresent(t *testing.T, namespace string, influxPodName string, influxDatabase string, measurements []string) bool {
	output, err := ExcuteInfluxDBQueryE(t, namespace, influxPodName, "show measurements", "-database", influxDatabase)
	if err != nil {
		t.Logf("Unexpected error received from InfluxDB: %s", err)
		return false
	}
	matches := 0
	for _, m := range measurements {
		if strings.Contains(output, m) {
			t.Logf("Measurement %s in database %s found", m, influxDatabase)
			matches++
		}
	}
	return len(measurements) == matches
}

func verifyMeasurementsPresent(t *testing.T, namespace string, influxPodName string, influxDatabase string,
	measurements []string, timeout time.Duration) {
	testlib.Await(t, func() bool {
		return checkMeasurementsPresent(t, namespace, influxPodName, influxDatabase, measurements)
	}, timeout)
}

func verifyNuoDBDatabasesPresent(t *testing.T, namespace string, influxPodName string) {
	output, err := ExcuteInfluxDBQueryE(t, namespace, influxPodName, "show databases")
	require.NoError(t, err)
	assert.Contains(t, output, "nuodb")
	assert.Contains(t, output, "nuodb_internal")
	assert.Contains(t, output, "telegraf")
}

func verifyEngineMetricsPresent(t *testing.T, namespace string, influxPodName string, influxDatabase string,
	measurement string, database string, metric string, timeout time.Duration) {
	options := k8s.NewKubectlOptions("", "", namespace)
	pods := k8s.ListPods(t, options, metav1.ListOptions{
		LabelSelector: fmt.Sprintf("database=%s,component in (sm, te)", database),
	})
	for _, pod := range pods {
		t.Logf("Searching for %s in %s for pod %s", metric, measurement, pod.Name)
		testlib.Await(t, func() bool {
			return checkMetricPresent(t, namespace, influxPodName, influxDatabase, measurement, database, pod.Name, metric)
		}, timeout)
	}
}

func TestKubernetesInsightsInstall(t *testing.T) {
	defer testlib.VerifyTeardown(t)
	defer testlib.Teardown(testlib.TEARDOWN_ADMIN)
	defer testlib.Teardown(TEARDOWN_INSIGHTS)

	options := helm.Options{
		SetValues: map[string]string{},
	}

	helmChartReleaseName, namespaceName := StartInsights(t, &options, "")

	influxPodName := fmt.Sprintf("%s-influxdb-0", helmChartReleaseName)

	t.Run("verifyDatabasesPresent", func(t *testing.T) {
		verifyNuoDBDatabasesPresent(t, namespaceName, influxPodName)
	})

}

func TestKubernetesInsightsMetricsCollection(t *testing.T) {
	defer testlib.VerifyTeardown(t)
	defer testlib.Teardown(testlib.TEARDOWN_ADMIN)
	defer testlib.Teardown(testlib.TEARDOWN_DATABASE)
	defer testlib.Teardown(TEARDOWN_INSIGHTS)
	defer testlib.Teardown(testlib.TEARDOWN_YCSB)

	options := helm.Options{
		SetValues: map[string]string{
			"nuocollector.enabled":                  "true",
			"database.sm.resources.requests.cpu":    testlib.MINIMAL_VIABLE_ENGINE_CPU,
			"database.sm.resources.requests.memory": "256Mi",
			"database.te.resources.requests.cpu":    testlib.MINIMAL_VIABLE_ENGINE_CPU,
			"database.te.resources.requests.memory": "256Mi",
			"ycsb.replicas":                         "1",
		},
	}
	InjectNuoDBHelmChartsVersion(t, &options)

	// Start Database
	adminReleaseName, namespaceName := testlib.StartAdmin(t, &options, 1, "")
	admin0 := fmt.Sprintf("%s-nuodb-cluster0-0", adminReleaseName)
	testlib.StartDatabase(t, namespaceName, admin0, &options)

	// Start Insights
	helmChartReleaseName, _ := StartInsights(t, &helm.Options{
		SetValues: map[string]string{
			// Disable Grafana as we don't use it in this test
			"grafana.enabled": "false",
		},
	}, namespaceName)
	influxPodName := fmt.Sprintf("%s-influxdb-0", helmChartReleaseName)

	// Start YCSB Load Generator
	startAndScaleYCSB(t, namespaceName, &options)
	waitTime := 60*time.Second
	time.Sleep(waitTime) // give some time to YCSB

	t.Run("verifyNuoDBMetricsStored", func(t *testing.T) {
		// Verify 6 out of 190+ measurements
		verifyMeasurementsPresent(t, namespaceName, influxPodName, "nuodb",
			[]string{"Objects", "SqlListenerThrottleTime", "CurrentCommittedTransactions", "PercentCpuTime", "ChairmanMigration", "Summary.CPU"}, waitTime)
		// Objects measurement has unit type 1 (MONITOR_COUNT)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "Objects", "demo", "raw", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "Objects", "demo", "rate", waitTime)

		// SqlListenerThrottleTime measurement has unit type 2 (MONITOR_MILLISECOND)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "SqlListenerThrottleTime", "demo", "raw", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "SqlListenerThrottleTime", "demo", "value", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "SqlListenerThrottleTime", "demo", "normvalue", waitTime)

		// No measurements have unit type 3 (MONITOR_STATE)

		// CurrentCommittedTransactions measurement has unit type 4 (MONITOR_NUMBER)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "CurrentCommittedTransactions", "demo", "raw", waitTime)

		// PercentCpuTime measurement has unit type 5 (MONITOR_PERCENT)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "PercentCpuTime", "demo", "raw", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "PercentCpuTime", "demo", "norm", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "PercentCpuTime", "demo", "ncores", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "PercentCpuTime", "demo", "idle", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "PercentCpuTime", "demo", "nidle", waitTime)

		// Measurements with unit type 6 (MONITOR_IDENTIFIER) are not stored

		// ChairmanMigration measurement has unit type 6 (MONITOR_DELTA)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "ChairmanMigration", "demo", "raw", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "ChairmanMigration", "demo", "rate", waitTime)

		// Summary measurement are calculated based on other measurement values
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "Summary.CPU", "demo", "raw", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "Summary.CPU", "demo", "value", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb", "Summary.CPU", "demo", "normvalue", waitTime)
	})

	t.Run("verifyNuoDBInternalMetricsStored", func(t *testing.T) {
		verifyMeasurementsPresent(t, namespaceName, influxPodName, "nuodb_internal",
			[]string{"nuodb_msgtrace", "nuodb_thread", "nuodb_synctrace"}, waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb_internal", "nuodb_msgtrace", "demo", "maxStallTime", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb_internal", "nuodb_thread", "demo", "stime", waitTime)
		verifyEngineMetricsPresent(t, namespaceName, influxPodName, "nuodb_internal", "nuodb_synctrace", "demo", "numLocks", waitTime)
	})
}
