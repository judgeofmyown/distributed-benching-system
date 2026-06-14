job "registry" {
  datacenters = ["dc1"]
  type        = "service"

  group "registry-group" {
    count = 1

    network {
      # Use host network mode so port 5000 attaches directly to your WSL IP interface
      mode = "host"
      port "http" {
        static = 5000
      }
    }

    service {
      name      = "docker-registry"
      port      = "http"
      provider  = "consul"

      check {
        type     = "http"
        path     = "/v2/"
        interval = "10s"
        timeout  = "2s"
      }
    }

    task "registry-server" {
      driver = "docker"

      config {
        image = "registry:2"
        ports = ["http"]
        
        # Ensure your local directory exists before running
        mount {
          type   = "bind"
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
