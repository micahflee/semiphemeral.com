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
  size               = "s-2vcpu-4gb"
  private_networking = true
  ssh_keys = [
    var.ssh_fingerprint
  ]
}

resource "digitalocean_firewall" "app" {
  name        = "ssh-http-https-postgresql-${var.deploy_environment}"
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

  # DigitalOcean postgresql database cluster's connection pool
  # I can't seem to restrict it to a hostname, and I don't know the cluster's IP
  outbound_rule {
    protocol              = "tcp"
    port_range            = "25060"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "25061"
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

resource "digitalocean_database_cluster" "db" {
  name       = "db-${var.deploy_environment}"
  engine     = "pg"
  version    = "12"
  size       = "db-s-1vcpu-1gb"
  region     = "nyc1"
  node_count = 1
}

resource "digitalocean_database_firewall" "fw" {
  cluster_id = digitalocean_database_cluster.db.id

  rule {
    type  = "droplet"
    value = digitalocean_droplet.app.id
  }
}

resource "digitalocean_database_connection_pool" "pool" {
  cluster_id = digitalocean_database_cluster.db.id
  name       = "pool-01-${var.deploy_environment}"
  mode       = "session"
  size       = 20
  db_name    = digitalocean_database_cluster.db.database
  user       = digitalocean_database_cluster.db.user
}

output "app_ip" {
  value = digitalocean_droplet.app.ipv4_address
}

output "database_uri" {
  value = digitalocean_database_connection_pool.pool.private_uri
}

output "database_host" {
  value = digitalocean_database_connection_pool.pool.private_host
}

output "database_port" {
  value = digitalocean_database_connection_pool.pool.port
}

output "database_name" {
  value = digitalocean_database_connection_pool.pool.name
}

output "database_user" {
  value = digitalocean_database_connection_pool.pool.user
}

output "database_password" {
  value = digitalocean_database_connection_pool.pool.password
}

output "postbird_url" {
  value = "postgresql://doadmin:${digitalocean_database_cluster.db.password}@localhost:5432/defaultdb?ssl=true"
}
