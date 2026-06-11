job "swarm_cluster" {
  datacenters = ["dc1"]
  type        = "service"

  group "market-makers" {
    
    count = 5

    task "swarm" {
      driver = "docker"

      config {
        image = "" #  image registry 
      }

      template {
        data = <<EOH
        {{ range service "matching-engine" }}
        SERVER_HOST = "{{ .Address }}"
        SERVER_PORT = "{{ .Port }}"
        {{ end }}
        EOH

        destination = "secrets/env"
        env         = true
      }

      env {
        NUM_BOTS            = "50"        
        PROB_BUY            = "0.45"
        PROB_SELL           = "0.45"
        PROB_CANCEL         = "0.10"
        ASSET_INITIAL_PRICE = "50000"
        STD_DEV             = "2.5"
        SLEEP_TIMEOUT       = "0.005"  # High speed (5 milliseconds sleep)
        TELEMETRY_HOST      = "${attr.unique.network.ip-address}"
        TELEMETRY_PORT      = "8125"
      }
      
      resources {
        cpu     = 1500  # Mhz (approx 1.5 cores)
        memory  = 512   # MB 
      }
    }
  }
  
  group "trend-followers" {
    # buyers

    count = 5

    task "swarm" {
      driver = "docker"

      config {
        image = "" #  image registry 
      }
 
      template {
        data = <<EOH
        {{ range service "matching-engine" }}
        SERVER_HOST = "{{ .Address }}"
        SERVER_PORT = "{{ .Port }}"
        {{ end }}
        EOH

        destination = "secrets/env"
        env         = true
      }

      env {
        NUM_BOTS            = "50"
        SERVER_HOST         = ""
        SERVER_PORT         = ""
        
        PROB_BUY            = "0.75"
        PROB_SELL           = "0.15"
        PROB_CANCEL         = "0.10"
        
        ASSET_INITIAL_PRICE = "50000"
        STD_DEV             = "5.0"     # Higher volatility behavior
        SLEEP_TIMEOUT       = "0.015"   # Medium speed

        TELEMETRY_HOST      = "${attr.unique.network.ip-address}"
        TELEMETRY_PORT      = "8125"      }
      
      resources {
        cpu     = 1500
        memory  = 512
      }
    }
  }

  group "liquidators" {
    # sellers

    count = 5

    task "swarm" {
      driver = "docker"

      config {
        image = "" #  image registry 
      }
       
      template {
        data = <<EOH
        {{ range service "matching-engine" }}
        SERVER_HOST = "{{ .Address }}"
        SERVER_PORT = "{{ .Port }}"
        {{ end }}
        EOH

        destination = "secrets/env"
        env         = true
      }

      env {
        NUM_BOTS            = "50"
        SERVER_HOST         = ""
        SERVER_PORT         = ""
        
        PROB_BUY            = "0.15"
        PROB_SELL           = "0.75"
        PROB_CANCEL         = "0.10"
        
        ASSET_INITIAL_PRICE = "50000"
        STD_DEV             = "4.0"
        SLEEP_TIMEOUT       = "0.01"

        TELEMETRY_HOST      = "${attr.unique.network.ip-address}"
        TELEMETRY_PORT      = "8125"      }
      
      resources {
        cpu     = 1500
        memory  = 512
      }
    }
  }

}
