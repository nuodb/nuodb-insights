package docker

import (
	"github.com/gruntwork-io/terratest/modules/docker"
	"strings"
	"testing"
)

func executeCommandInContainer(t *testing.T, composeFile string, containerName string, args ...string) string {
	options :=  docker.Options {
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

func GetDatabaseListings(t *testing.T, composeFile string, influxContainerName string) []string {
	raw := executeCommandInContainer(t, composeFile, influxContainerName, "influx", "-execute", "show databases")
	databaseListing := strings.Split(raw, "----")[1]
	return strings.Split(databaseListing, "\n")
}