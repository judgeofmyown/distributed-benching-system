job "telemetry-collector" {
  datacenters = ["dc1"]
  type        = "system"

  group "agent-group" {
    network {
      port "statsd_udp" {
        static = 8125
      }
      port "prom_http" {
        static = 9273
      }
    }

    task "telegraf-service" {
      driver = "docker"

      config {
        image = "telegraf:1.30-alpine"

        volumes = [
          "local/telegraf.conf:/etc/telegraf/telegraf.conf"
        ]
      }
      
      template {
        source      = "telemetry/telegraf.conf"
        destination = "local/telegraf.conf"
        
        # automatic reload upon telegraf.cong updation
        change_mode = "restart"
      }
      
      resource {
        cpu     = 300
        memory  = 128
      }
    }
  }
}
