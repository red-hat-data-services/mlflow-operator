package main

import (
	"testing"
)

func TestInferPodNamespaceFromEnv(t *testing.T) {
	t.Setenv("POD_NAMESPACE", "custom-apps")
	if got := inferPodNamespace(); got != "custom-apps" {
		t.Fatalf("inferPodNamespace() = %q, want %q", got, "custom-apps")
	}
}

func TestInferPodNamespaceFallsBackOutsideCluster(t *testing.T) {
	t.Setenv("POD_NAMESPACE", "")
	if got := inferPodNamespace(); got != defaultNamespace {
		t.Fatalf("inferPodNamespace() = %q, want %q (fallback when env is unset)", got, defaultNamespace)
	}
}
