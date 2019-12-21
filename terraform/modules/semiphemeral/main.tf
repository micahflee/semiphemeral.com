variable "deploy_environment" {}
variable "ssh_fingerprint" {}

resource "digitalocean_droplet" "app" {
  name               = "app-${var.deploy_environment}"
  image              = "debian-10-x64"
  region             = "nyc1"
  size               = "512mb"
  private_networking = true
  ssh_keys = [
    var.ssh_fingerprint
  ]
}


output "app_ip" {
  value = digitalocean_droplet.app.ipv4_address
}
