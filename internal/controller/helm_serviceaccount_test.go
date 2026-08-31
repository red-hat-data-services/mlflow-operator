/*
Copyright 2026.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package controller

import (
	"testing"

	gomega "github.com/onsi/gomega"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"

	mlflowv1 "github.com/opendatahub-io/mlflow-operator/api/v1"
)

const irsaRoleArnAnnotation = "eks.amazonaws.com/role-arn"
const irsaRoleArn = "arn:aws:iam::123456789012:role/mlflow-s3"

func TestMlflowToHelmValues_ServiceAccountAnnotations(t *testing.T) {
	renderer := &HelmRenderer{}

	t.Run("no annotations - key should not exist", func(t *testing.T) {
		g := gomega.NewWithT(t)

		mlflow := &mlflowv1.MLflow{
			ObjectMeta: metav1.ObjectMeta{Name: "test"},
			Spec: mlflowv1.MLflowSpec{
				BackendStoreURI: ptr(testBackendStoreURI),
			},
		}

		values, err := renderer.mlflowToHelmValues(mlflow, "test-namespace", RenderOptions{}, nil)
		g.Expect(err).NotTo(gomega.HaveOccurred())

		sa, ok := values["serviceAccount"].(map[string]interface{})
		g.Expect(ok).To(gomega.BeTrue())
		g.Expect(sa).NotTo(gomega.HaveKey("annotations"))
	})

	t.Run("annotations copied to main SA and enabled GC and trace-archival SAs", func(t *testing.T) {
		g := gomega.NewWithT(t)

		mlflow := &mlflowv1.MLflow{
			ObjectMeta: metav1.ObjectMeta{Name: "test"},
			Spec: mlflowv1.MLflowSpec{
				BackendStoreURI: ptr(testBackendStoreURI),
				ServiceAccountAnnotations: map[string]string{
					irsaRoleArnAnnotation: irsaRoleArn,
				},
				GarbageCollection: &mlflowv1.GarbageCollectionSpec{
					Schedule: "0 2 * * 0",
				},
				TraceArchival: &mlflowv1.TraceArchivalSpec{
					Enabled:  true,
					Schedule: ptr("0 */6 * * *"),
				},
			},
		}

		values, err := renderer.mlflowToHelmValues(mlflow, "test-namespace", RenderOptions{}, nil)
		g.Expect(err).NotTo(gomega.HaveOccurred())

		assertSAAnnotations(t, values["serviceAccount"])

		gc, ok := values["garbageCollection"].(map[string]interface{})
		g.Expect(ok).To(gomega.BeTrue())
		assertSAAnnotations(t, gc["serviceAccount"])

		ta, ok := values["traceArchival"].(map[string]interface{})
		g.Expect(ok).To(gomega.BeTrue())
		assertSAAnnotations(t, ta["serviceAccount"])
	})
}

func TestRenderChart_ServiceAccountAnnotations(t *testing.T) {
	g := gomega.NewWithT(t)
	renderer := NewHelmRenderer("../../charts/mlflow")

	mlflow := &mlflowv1.MLflow{
		ObjectMeta: metav1.ObjectMeta{Name: "mlflow"},
		Spec: mlflowv1.MLflowSpec{
			BackendStoreURI: ptr(testBackendStoreURI),
			ServiceAccountAnnotations: map[string]string{
				irsaRoleArnAnnotation: irsaRoleArn,
			},
			GarbageCollection: &mlflowv1.GarbageCollectionSpec{
				Schedule: "0 2 * * 0",
			},
			TraceArchival: &mlflowv1.TraceArchivalSpec{
				Enabled:  true,
				Schedule: ptr("0 */6 * * *"),
			},
		},
	}

	objs, err := renderer.RenderChart(mlflow, "test-ns", RenderOptions{}, nil)
	g.Expect(err).NotTo(gomega.HaveOccurred())

	for _, name := range []string{ServiceAccountName, GCServiceAccountName, TraceArchivalServiceAccountName} {
		sa := findObject(objs, "ServiceAccount", name)
		g.Expect(sa).NotTo(gomega.BeNil(), "ServiceAccount %s should be rendered", name)

		annotations, found, err := unstructured.NestedStringMap(sa.Object, "metadata", "annotations")
		g.Expect(err).NotTo(gomega.HaveOccurred())
		g.Expect(found).To(gomega.BeTrue(), "ServiceAccount %s should have annotations", name)
		g.Expect(annotations).To(gomega.HaveKeyWithValue(irsaRoleArnAnnotation, irsaRoleArn))
	}
}

func assertSAAnnotations(t *testing.T, raw interface{}) {
	t.Helper()
	g := gomega.NewWithT(t)

	sa, ok := raw.(map[string]interface{})
	g.Expect(ok).To(gomega.BeTrue())
	annotations, ok := sa["annotations"].(map[string]string)
	g.Expect(ok).To(gomega.BeTrue())
	g.Expect(annotations).To(gomega.HaveKeyWithValue(irsaRoleArnAnnotation, irsaRoleArn))
}
