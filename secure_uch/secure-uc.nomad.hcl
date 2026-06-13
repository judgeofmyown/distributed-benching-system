# didnt used this (used in backend as payload in JSON text)j

variable "submission_id" {
    type=string
}

variable "runtime_image" {
    type=string
}
variable "runtime_target_mount" {
    type=string
}
variable "clean_source_path" {
    type=string
}

job "submission-${var.submission_id}" {
  datacenters = ["dc1"]
  type        = "batch"

  group "runner" {
    count = 1

    network {
      mode = "host"
      port "exchange_port" {
        static = 8888
      }
    }

    service {
      name     = "user-code-server"
      port     = "exchange_port"
      provider = "consul"
      tags     = ["id-${var.submission_id}", "execution"]
    }

    task "executor" {
      driver = "docker"

      config {
        image   = var.runtime_image"
        runtime = "runc"
        ports   = ["exchange_port"]

        mount {
          type     = "bind"
          target   = var.runtime_target_mount
          source   = var.clean_source_path
          readonly = true
        }
      }

      resources {
        cpu    = 1000
        memory = 1024
      }

      restart {
        attempts = 0
        mode     = "fail"
      }
    }
  }
}
