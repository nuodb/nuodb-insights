package docker

import (
	"context"
	"github.com/docker/docker/api/types"
	"github.com/docker/docker/client"
	"github.com/gruntwork-io/terratest/modules/docker"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"testing"
)

func containersContainImage(t *testing.T, containers []types.Container, expectedImage string) bool {
	for _, container := range containers {
		if container.Image == expectedImage {
			return true
		}
	}

	return false
}

func TestDockerInsightsInstallSmall(t *testing.T) {
	cli, err := client.NewClientWithOpts(client.FromEnv)
	require.NoError(t, err)

	options :=  docker.Options {
		WorkingDir: "../..",
	}
	docker.RunDockerCompose(t, &options, "-f", "deploy/monitor-stack.yaml", "up", "-d")
	defer func() {
		docker.RunDockerCompose(t, &options, "-f", "deploy/monitor-stack.yaml", "down")
	}()

	containers, err := cli.ContainerList(context.Background(), types.ContainerListOptions{})
	require.NoError(t, err)

	assert.EqualValues(t, 2, len(containers))
	assert.True(t, containersContainImage(t, containers, "influxdb:1.8"))
	assert.True(t, containersContainImage(t, containers, "grafana/grafana:latest"))

}

func TestDockerInsightsInstallComplete(t *testing.T) {
	cli, err := client.NewClientWithOpts(client.FromEnv)
	require.NoError(t, err)

	options :=  docker.Options {
		WorkingDir: "../..",
	}
	docker.RunDockerCompose(t, &options, "-f", "deploy/docker-compose.yaml", "up", "-d")
	defer func() {
		docker.RunDockerCompose(t, &options, "-f", "deploy/docker-compose.yaml", "down")
	}()

	containers, err := cli.ContainerList(context.Background(), types.ContainerListOptions{})
	require.NoError(t, err)

	assert.EqualValues(t, 8, len(containers))
	assert.True(t, containersContainImage(t, containers, "influxdb:1.8"), "Influx container not found")
	assert.True(t, containersContainImage(t, containers, "grafana/grafana:latest"), "Grafana container not found")

}