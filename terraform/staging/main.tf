variable "deploy_environment" {}
variable "ssh_fingerprint" {}
variable "do_token" {}

provider "digitalocean" {
  token = var.do_token
}

module "semiphemeral" {
  source             = "../modules/semiphemeral"
  deploy_environment = var.deploy_environment
  ssh_fingerprint    = var.ssh_fingerprint
}

output "app_ip" {
  value = module.semiphemeral.app_ip
}
