![Logo](/img/logo-small.png)

# Semiphemeral.com

The hosted version of [semiphemeral](https://github.com/micahflee/semiphemeral).

## Staging and production infrastructure

Install [terraform](https://www.terraform.io/downloads.html) and python 3.7+, and these pip dependencies:

```sh
pip3 install --user click ansible black
```

Copy `vars-sample` to `.vars` and edit it to add a DigitalOcean API token, and the fingerprint of an SSH key uploaded to DigitalOcean.

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