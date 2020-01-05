# staging or prod
variable "deploy_environment" {}

# fingerprint of SSH key to add to new droplet
variable "ssh_fingerprint" {}

# for firewall rules
variable "ssh_ips" {}
variable "inbound_ips" {}

# for DNS records
variable "frontend_domain" {}
variable "backend_domain" {}

resource "digitalocean_droplet" "app" {
  name               = "app-${var.deploy_environment}"
  image              = "fedora-31-x64"
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

resource "digitalocean_domain" "frontend" {
  name       = var.frontend_domain
  ip_address = digitalocean_droplet.app.ipv4_address
}

resource "digitalocean_domain" "backend" {
  name       = var.backend_domain
  ip_address = digitalocean_droplet.app.ipv4_address
}

output "app_ip" {
  value = digitalocean_droplet.app.ipv4_address
}
