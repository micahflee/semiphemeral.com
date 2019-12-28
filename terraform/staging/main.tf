variable "deploy_environment" {}
variable "ssh_fingerprint" {}
variable "do_token" {}
variable "ssh_ips" {}
variable "inbound_ips" {}

provider "digitalocean" {
  token = var.do_token
}

module "semiphemeral" {
  source             = "../modules/semiphemeral"
  deploy_environment = var.deploy_environment
  ssh_fingerprint    = var.ssh_fingerprint
  ssh_ips            = var.ssh_ips
  inbound_ips        = var.inbound_ips
}

output "app_ip" {
  value = module.semiphemeral.app_ip
}
