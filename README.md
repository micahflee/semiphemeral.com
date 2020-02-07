![Logo](/img/logo.png)

# Semiphemeral.com

The hosted version of [semiphemeral](https://github.com/micahflee/semiphemeral).

## Staging and production infrastructure

To backup and restore, you need `postgresql-client` installed.

Install [terraform](https://www.terraform.io/downloads.html) and python 3.7+, and these pip dependencies:

```sh
# from pip
pip3 install --user ansible black click requests
# or from apt
sudo apt install ansible black python3-click python3-requests
```

Copy `vars-terraform-sample.json` to `.vars-terraform.json` and edit it to add a DigitalOcean API token, and the fingerprint of an SSH key uploaded to DigitalOcean. Copy `vars-ansible-sample.json` to `.vars-ansible.json` and edit it to add Twitter app credentials.

Use `devops.py`. Each command requires passing in either `staging` or `prod`:

```
$ ./devops.py
Usage: devops.py [OPTIONS] COMMAND [ARGS]...

  Deploy semiphemeral.com

Options:
  --help  Show this message and exit.

Commands:
  deploy   Deploy and configure infrastructure
  destroy  Destroy infrastructure
  ssh      SSH to server
```

When you run deploy, it will use terraform to deploy/update DigitalOcean infrastructure, and then use ansible to ensure the server is configured.

It also detects your current IP address, and configures the firewall to only allow SSHing from this IP address (so if you need to SSH from another IP, you must re-run deploy). Likewise, only your current IP will be able to connect to the staging server (except during the deploy, when all IPs are allowed, to make Let's Encrypt work).