variable "do_token" {}
variable "ssh_fingerprint" {}
variable "domain" {}

provider "digitalocean" {
  token = var.do_token
}

# networking

resource "digitalocean_vpc" "semiphemeral" {
  name   = "semiphemeral-production"
  region = "nyc1"
}

# bastion

resource "digitalocean_droplet" "bastion" {
  name          = "bastion"
  image         = "ubuntu-22-04-x64"
  region        = "nyc1"
  size          = "s-1vcpu-512mb-10gb"
  vpc_uuid      = digitalocean_vpc.semiphemeral.id
  monitoring    = true
  droplet_agent = true
  ssh_keys      = [var.ssh_fingerprint]
}

resource "digitalocean_firewall" "bastion" {
  name        = "bastion"
  droplet_ids = [digitalocean_droplet.bastion.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "icmp"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "22"
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

# app

resource "digitalocean_droplet" "app" {
  name          = "app-production"
  image         = "ubuntu-22-04-x64"
  region        = "nyc1"
  size          = "s-2vcpu-2gb"
  vpc_uuid      = digitalocean_vpc.semiphemeral.id
  monitoring    = true
  droplet_agent = true
  ssh_keys      = [var.ssh_fingerprint]
}

resource "digitalocean_firewall" "app" {
  name        = "app-production"
  droplet_ids = [digitalocean_droplet.app.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = [digitalocean_droplet.bastion.ipv4_address_private]
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
  name          = "db-production"
  image         = "ubuntu-22-04-x64"
  size          = "s-2vcpu-2gb"
  region        = "nyc1"
  vpc_uuid      = digitalocean_vpc.semiphemeral.id
  monitoring    = true
  droplet_agent = true
  ssh_keys      = [var.ssh_fingerprint]
}

resource "digitalocean_volume" "db_data" {
  region                  = "nyc1"
  name                    = "db-production"
  size                    = 256
  initial_filesystem_type = "ext4"
}

resource "digitalocean_volume_attachment" "db_data" {
  droplet_id = digitalocean_droplet.db.id
  volume_id  = digitalocean_volume.db_data.id
}

resource "digitalocean_firewall" "db" {
  name        = "db-production"
  droplet_ids = [digitalocean_droplet.db.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = [digitalocean_droplet.bastion.ipv4_address_private]
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
    # destination_addresses = ["10.0.0.0/8"]
  }
}

# DNS

resource "digitalocean_domain" "domain" {
  name       = var.domain
  ip_address = digitalocean_droplet.app.ipv4_address
}

resource "digitalocean_record" "helm_txt1" {
  domain = digitalocean_domain.domain.name
  type   = "TXT"
  name   = "@"
  value  = "v=spf1 include:hush.blue -all"
  ttl    = "3600"
}

resource "digitalocean_record" "helm_txt2" {
  domain = digitalocean_domain.domain.name
  type   = "TXT"
  name   = "_dmarc"
  value  = "v=DMARC1; p=reject; sp=reject; pct=100; aspf=r; fo=0; rua=mailto:postmaster@semiphemeral.com"
  ttl    = "3600"
}

resource "digitalocean_record" "helm_mx" {
  domain   = digitalocean_domain.domain.name
  type     = "MX"
  name     = "@"
  value    = "helm.hush.blue."
  priority = 10
  ttl      = "3600"
}

resource "digitalocean_record" "helm_cname" {
  domain = digitalocean_domain.domain.name
  type   = "CNAME"
  name   = "mail._domainkey"
  value  = "mail._domainkey.hush.blue."
  ttl    = "3600"
}

# output

output "bastion_ip" {
  value = digitalocean_droplet.bastion.ipv4_address
}

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
