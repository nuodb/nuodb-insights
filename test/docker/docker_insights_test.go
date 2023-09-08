package docker

import (
	"context"
	"testing"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/client"
	"github.com/gruntwork-io/terratest/modules/docker"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func containersContainImage(t *testing.T, containers []types.Container, expectedImage string) bool {
	for _, container := range containers {
		if container.Image == expectedImage {
			return true
		}
	}
	return false
}

func assertInfluxContainsDatabases(t *testing.T, composeFile string) {
	listings, _ := GetDatabaseListings(t, composeFile, INFLUXDB_CONTAINER_NAME)
	assert.Contains(t, listings, "nuodb")
	assert.Contains(t, listings, "nuodb_internal")
}

func TestDockerInsightsInstallSmall(t *testing.T) {
	cli, err := client.NewClientWithOpts(client.FromEnv)
	require.NoError(t, err)

	options := docker.Options{
		WorkingDir: "../..",
	}
	docker.RunDockerCompose(t, &options, "-f", "deploy/monitor-stack.yaml", "up", "-d")
	defer func() {
		docker.RunDockerCompose(t, &options, "-f", "deploy/monitor-stack.yaml", "down")
	}()

	containers, err := cli.ContainerList(context.Background(), types.ContainerListOptions{})
	require.NoError(t, err)

	assert.EqualValues(t, 2, len(containers))
	assert.True(t, containersContainImage(t, containers, INFLUX_VERSION))
	assert.True(t, containersContainImage(t, containers, GRAFANA_VERSION))

}

func TestDockerInsightsInstallComplete(t *testing.T) {
	cli, err := client.NewClientWithOpts(client.FromEnv)
	require.NoError(t, err)

	composeFile := "deploy/docker-compose.yaml"

	options := docker.Options{
		WorkingDir: "../..",
	}
	docker.RunDockerCompose(t, &options, "-f", composeFile, "up", "-d")
	defer func() {
		docker.RunDockerCompose(t, &options, "-f", composeFile, "down")
	}()

	containers, err := cli.ContainerList(context.Background(), types.ContainerListOptions{})
	require.NoError(t, err)

	assert.EqualValues(t, 10, len(containers))
	assert.True(t, containersContainImage(t, containers, INFLUX_VERSION), "Influx container not found")
	assert.True(t, containersContainImage(t, containers, GRAFANA_VERSION), "Grafana container not found")

	AwaitAdminUp(t, composeFile, ADMIN_CONTAINER_NAME)
	AwaitDatabaseUp(t, composeFile, ADMIN_CONTAINER_NAME)

	assertInfluxContainsDatabases(t, composeFile)
}
