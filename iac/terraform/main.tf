terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "4.80.0" # Provider version
    }
  }
  required_version = "1.9.2" # Terraform version
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Define GKE Cluster
resource "google_container_cluster" "primary" {
  name                     = "${var.project_id}-gke"
  location                 = var.region
  remove_default_node_pool = true
  initial_node_count       = 1

}

# Node Pool for System Services (minio and redis)
resource "google_container_node_pool" "system_services" {
  name       = "${var.project_id}-system-pool"
  location   = var.region
  cluster    = google_container_cluster.primary.name
  node_count = 1

  node_config {
    machine_type = "e2-standard-2"
    disk_size_gb = 50
    preemptible  = false
    labels = {
      workload = "system-services"
    }
  }

  autoscaling {
    min_node_count = 1
    max_node_count = 3
  }
}

# Node Pool for Compute-Heavy Workloads (doc_management_api, chat_api) without GPU
resource "google_container_node_pool" "backend-service" {
  name       = "${var.project_id}-compute-pool"
  location   = var.region
  cluster    = google_container_cluster.primary.name
  node_count = 1

  node_config {
    machine_type = "n1-standard-4" # Use a standard machine type
    disk_size_gb = 100
    preemptible  = false
    labels = {
      workload = "compute-heavy"
    }
  }

  # Optional: Enable autoscaling for better resource utilization
  autoscaling {
    min_node_count = 1
    max_node_count = 3
  }
}



# Node Pool for Frontend
resource "google_container_node_pool" "frontend" {
  name       = "${var.project_id}-frontend-pool"
  location   = var.region
  cluster    = google_container_cluster.primary.name
  node_count = 1

  node_config {
    machine_type = "e2-medium"
    disk_size_gb = 40
    preemptible  = true
    labels = {
      workload = "frontend"
    }
  }

  autoscaling {
    min_node_count = 1
    max_node_count = 3
  }
}

# Outputs
output "kubernetes_cluster_name" {
  value = google_container_cluster.primary.name
}

output "kubernetes_cluster_endpoint" {
  value = google_container_cluster.primary.endpoint
}

output "kubernetes_cluster_ca_certificate" {
  value = google_container_cluster.primary.master_auth.0.cluster_ca_certificate
}
