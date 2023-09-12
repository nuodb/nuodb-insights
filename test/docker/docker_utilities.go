package docker

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/gruntwork-io/terratest/modules/docker"
	"github.com/stretchr/testify/require"
)

func executeCommandInContainer(t *testing.T, composeFile string, containerName string, args ...string) string {
	options := docker.Options{
		WorkingDir: "../..",
	}

	return docker.RunDockerCompose(t, &options, append([]string{"-f", composeFile, "exec", "-T", containerName}, args...)...)
}

func AwaitAdminUp(t *testing.T, composeFile string, adminContainerName string) {
	executeCommandInContainer(t, composeFile, adminContainerName, "nuocmd", "check", "servers",
		"--check-leader",
		"--timeout", "120")
}

func AwaitDatabaseUp(t *testing.T, composeFile string, adminContainerName string) {
	executeCommandInContainer(t, composeFile, adminContainerName, "nuocmd", "check", "database",
		"--db-name", "hockey",
		"--num-processes", "3",
		"--check-running",
		"--timeout", "120")
}

func GetDatabaseListings(t *testing.T, composeFile string, influxContainerName string) ([]string, error) {
	jsonData := executeCommandInContainer(t, composeFile, influxContainerName, "influx", "bucket", "list", "--json")
	var bucketList []map[string]interface{}
	var listing []string
	err := json.Unmarshal([]byte(jsonData), &bucketList)
	require.NoError(t, err)
	for _, bucket := range bucketList {
		str, ok := bucket["name"].(string)
		if !ok {
			error:= errors.New("invalid bucket name")
			return nil, error
		} 
		listing = append(listing, str)
	}
	return listing, nil
}
