# staging or prod
variable "deploy_environment" {}

# fingerprint of SSH key to add to new droplet
variable "ssh_fingerprint" {}

# for firewall rules
variable "ssh_ips" {}
variable "inbound_ips" {}

# for DNS records
variable "domain" {}

resource "digitalocean_droplet" "app" {
  name               = "app-${var.deploy_environment}"
  image              = "ubuntu-18-04-x64"
  region             = "nyc1"
  size               = "s-2vcpu-2gb"
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

  # DigitalOcean postgresql database cluster
  # I can't seem to restrict it to a hostname, and I don't know the cluster's IP
  outbound_rule {
    protocol              = "tcp"
    port_range            = "25060"
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

resource "digitalocean_domain" "domain" {
  name       = var.domain
  ip_address = digitalocean_droplet.app.ipv4_address
}

resource "digitalocean_database_cluster" "db" {
  name       = "db-${var.deploy_environment}"
  engine     = "pg"
  version    = "11"
  size       = "db-s-1vcpu-1gb"
  region     = "nyc1"
  node_count = 1
}

resource "digitalocean_database_user" "user" {
  cluster_id = digitalocean_database_cluster.db.id
  name       = "semiphemeral"
}

resource "digitalocean_database_firewall" "fw" {
  cluster_id = digitalocean_database_cluster.db.id

  rule {
    type  = "droplet"
    value = digitalocean_droplet.app.id
  }
}

output "app_ip" {
  value = digitalocean_droplet.app.ipv4_address
}

output "database_uri" {
  value = digitalocean_database_cluster.db.private_uri
}

output "database_host" {
  value = digitalocean_database_cluster.db.private_host
}

output "database_name" {
  value = digitalocean_database_cluster.db.database
}

output "database_user" {
  value = digitalocean_database_cluster.db.user
}

output "database_password" {
  value = digitalocean_database_cluster.db.password
}
