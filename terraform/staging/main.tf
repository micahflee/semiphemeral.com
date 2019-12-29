variable "deploy_environment" {}
variable "ssh_fingerprint" {}
variable "do_token" {}
variable "ssh_ips" {}
variable "inbound_ips" {}
variable "frontend_domain" {}
variable "backend_domain" {}

provider "digitalocean" {
  token = var.do_token
}

module "semiphemeral" {
  source             = "../modules/semiphemeral"
  deploy_environment = var.deploy_environment
  ssh_fingerprint    = var.ssh_fingerprint
  ssh_ips            = var.ssh_ips
  inbound_ips        = var.inbound_ips
  frontend_domain    = var.frontend_domain
  backend_domain     = var.backend_domain
}

output "app_ip" {
  value = module.semiphemeral.app_ip
}
