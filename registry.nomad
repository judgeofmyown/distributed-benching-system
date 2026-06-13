job "registry" {
  datacenters = ["dc1"]
  type        = "service"

  group "registry-group" {
    count = 1

    network {
      # This forces Nomad to host the registry on port 5000 of your machine
      port "http" {
        static = 5000
      }
    }

    task "registry-server" {
      driver = "docker"

      config {
        image = "registry:2"
        ports = ["http"]
        mount {
            type = "bind"
            source = "/tmp/nomad-registry"
            target = "/var/lib/registry"
        }
    }

      resources {
        cpu    = 500
        memory = 512
      }
    }
  }
}
