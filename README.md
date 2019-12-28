![Logo](/img/logo-small.png)

# Semiphemeral.com

The hosted version of [semiphemeral](https://github.com/micahflee/semiphemeral).

## Staging and production infrastructure

Install [terraform](https://www.terraform.io/downloads.html) and python 3.7+, and these pip dependencies:

```sh
# from pip
pip3 install --user ansible black click requests
# or from apt
sudo apt install ansible black python3-click python3-requests
```

Copy `vars-terraform-sample` to `.vars-terraform` and edit it to add a DigitalOcean API token, and the fingerprint of an SSH key uploaded to DigitalOcean. Copy `vars-ansible-sample` to `.vars-ansible` and edit it to add Twitter app credentials.

Use `devops.py`. Each command requires passing in either `staging` or `prod`:

```
$ ./devops.py
Usage: devops.py [OPTIONS] COMMAND [ARGS]...

  Deploy semiphemeral.com

Options:
  --help  Show this message and exit.

Commands:
  config   Configure server
  deploy   Deploy infrastructure
  destroy  Destroy infrastructure
  ssh      SSH to server
```