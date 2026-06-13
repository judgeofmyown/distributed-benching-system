# system job starts after the infra bootup

job "global-telemetry" {
  datacenters = ["dc1"]
  type        = "system"

  group "monitoring-agents" {
    network {
      port "statsd_udp" { static = 8125 }
      port "prom_http"  { static = 9273 }
      port "node_exp"   { static = 9100 } # explicitly mapping, else by default its 9100 itself
    }
    
    # task 1: handle client Bot, push metrices via UDP
    task "telegraf-service" {
      driver = "docker"
      config {
        image   = "telegraf:1.30-alpine"
        volumes = ["local/telegraf.conf:/etc/telegraf/telegraf.conf"]
        ports   = ["stats_udp", "prom_http"]
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

    task "server-node-exporter" {
        # by deafult listens on to  hostIP:9100/metrics

        driver = "docker"
        config {
            image   = "prom/node-exporter:v1.8.0"
            pid     = "host"
            volumes = ["/:/host:ro,rslave"]
            ports   = ["node_exp"]
            args    = ["--path.rootfs=/host"]

        }
        resources {
            cpu     = 200
            memory  = 64
        }
    }
  }
}
