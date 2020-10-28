	package minikube

import (
	"fmt"
	"github.com/gruntwork-io/terratest/modules/k8s"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"testing"

	"github.com/gruntwork-io/terratest/modules/helm"

	"github.com/nuodb/nuodb-helm-charts/test/testlib"
)


func verifyNuoDBDatabasesPresent(t *testing.T, namespace string, influxPodName string) {
	kubectlOptions := k8s.NewKubectlOptions("", "", namespace)

	output, err := k8s.RunKubectlAndGetOutputE(t, kubectlOptions, "exec", influxPodName, "--",
		"influx", "-execute", "show databases")

	require.NoError(t, err)
	assert.Contains(t, output, "nuodb")
	assert.Contains(t, output, "nuodb_internal")
	assert.Contains(t, output, "nuolog")
	assert.Contains(t, output, "telegraf")
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
