variable "do_token" {}
variable "ssh_fingerprint" {}
variable "domain" {}
variable "bastion_ip" {}
variable "db_volume_snapshot_id" {}

provider "digitalocean" {
  token = var.do_token
}

# networking

resource "digitalocean_vpc" "semiphemeral" {
  name   = "semiphemeral-staging"
  region = "nyc1"
}

# app

resource "digitalocean_droplet" "app" {
  name          = "app-staging"
  image         = "ubuntu-22-04-x64"
  region        = "nyc1"
  size          = "s-2vcpu-2gb"
  vpc_uuid      = digitalocean_vpc.semiphemeral.id
  monitoring    = true
  droplet_agent = true
  ssh_keys      = [var.ssh_fingerprint]
}

resource "digitalocean_firewall" "app" {
  name        = "app-staging"
  droplet_ids = [digitalocean_droplet.app.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = [var.bastion_ip]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "icmp"
    source_addresses = ["0.0.0.0/0", "::/0"]
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
    protocol              = "tcp"
    port_range            = "5432"
    destination_addresses = [digitalocean_droplet.db.ipv4_address_private]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "53"
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

# db

resource "digitalocean_droplet" "db" {
  name          = "db-staging"
  image         = "ubuntu-22-04-x64"
  size          = "s-2vcpu-2gb"
  region        = "nyc1"
  vpc_uuid      = digitalocean_vpc.semiphemeral.id
  monitoring    = true
  droplet_agent = true
  ssh_keys      = [var.ssh_fingerprint]
}

resource "digitalocean_volume" "db_data" {
  region      = "nyc1"
  name        = "db-staging"
  size        = 256
  snapshot_id = var.db_volume_snapshot_id
}

resource "digitalocean_volume_attachment" "db_data" {
  droplet_id = digitalocean_droplet.db.id
  volume_id  = digitalocean_volume.db_data.id
}

resource "digitalocean_firewall" "db" {
  name        = "db-staging"
  droplet_ids = [digitalocean_droplet.db.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = [var.bastion_ip]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "5432"
    source_addresses = [digitalocean_droplet.app.ipv4_address_private]
  }

  inbound_rule {
    protocol         = "icmp"
    source_addresses = ["0.0.0.0/0", "::/0"]
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
    protocol              = "tcp"
    port_range            = "53"
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

  outbound_rule {
    protocol              = "tcp"
    port_range            = "22"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

# DNS

resource "digitalocean_domain" "domain" {
  name       = var.domain
  ip_address = digitalocean_droplet.app.ipv4_address
}

# output

output "app_ip" {
  value = digitalocean_droplet.app.ipv4_address
}

output "app_private_ip" {
  value = digitalocean_droplet.app.ipv4_address_private
}

output "db_ip" {
  value = digitalocean_droplet.db.ipv4_address
}

output "db_private_ip" {
  value = digitalocean_droplet.db.ipv4_address_private
}

output "bastion_ip" {
  value = var.bastion_ip
}

output "db_volume_snapshot_id" {
  value = var.db_volume_snapshot_id
}
