job "secure-exchange" {
  datacenters = ["dc1"]
  type        = "service"

  group "engine-group" {
    network {
      port "exchange" { to = 8888 }
    }

    task "secure-orderbook" {
      driver = "docker"

      config {
        image = ""
        ports ["exchange"]
        
        runtime = "runsc"
      }
      
      service {
        name = "matching-engine"
        prot = "exchange"
      }

      resources {
        cpu     = 2000
        memory  = 512
      }
    }
  }
}
