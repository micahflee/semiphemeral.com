variable "deploy_environment" {}
variable "ssh_fingerprint" {}
variable "ssh_ips" {}
variable "inbound_ips" {}

resource "digitalocean_droplet" "app" {
  name               = "app-${var.deploy_environment}"
  image              = "debian-10-x64"
  region             = "nyc1"
  size               = "s-1vcpu-2gb"
  private_networking = true
  ssh_keys = [
    var.ssh_fingerprint
  ]
}

resource "digitalocean_firewall" "app" {
  name        = "only-22-80-and-443"
  droplet_ids = [digitalocean_droplet.app.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = jsondecode(var.ssh_ips)
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = jsondecode(var.inbound_ips)
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = jsondecode(var.inbound_ips)
  }

  inbound_rule {
    protocol         = "icmp"
    source_addresses = jsondecode(var.inbound_ips)
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "53"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "80"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "443"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "53"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

output "app_ip" {
  value = digitalocean_droplet.app.ipv4_address
}
