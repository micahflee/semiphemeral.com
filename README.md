![Logo](/img/logo.png)

# Semiphemeral.com

The hosted version of [semiphemeral](https://github.com/micahflee/semiphemeral).

## Staging and production infrastructure

To backup and restore, you need `postgresql-client` installed.

Install:
- [terraform](https://www.terraform.io/downloads.html) (`snap install terraform`)
- [doctl](https://docs.digitalocean.com/reference/doctl/how-to/install/) (`snap install doctl`), and authenticate
- Python 3+, and these pip dependencies:

```sh
poetry install
```

Copy `vars-terraform-sample.json` to `vars-terraform.json` and edit it to add a DigitalOcean API token, and the fingerprint of an SSH key uploaded to DigitalOcean. Copy `vars-ansible-sample.json` to `vars-ansible.json` and edit it to add Twitter app credentials.

Use `devops.py`. Each command requires passing in either `staging` or `prod`:

```
$ poetry run ./devops.py
Usage: devops.py [OPTIONS] COMMAND [ARGS]...

  Deploy semiphemeral.com

Options:
  --help  Show this message and exit.

Commands:
  ansible-app             Deploy and configure infrastructure app server
  ansible-app-update      Update the app on already-deployed app server
  ansible-db              Deploy and configure infrastructure db server
  backup-prod-to-staging  Create backup on prod, restore it to
  backup-restore-app      Restore app backup
  backup-restore-db       Restore db backup
  backup-save-app         Save app backup
  backup-save-db          Save db backup
  destroy-staging         Destroy staging infrastructure
  forward-postgres        Forward the postgres port to localhost, using SSH
  ssh-app                 SSH to app server
  ssh-db                  SSH to db server
```

When you run deploy, it will use terraform to deploy/update DigitalOcean infrastructure, and then use ansible to ensure the server is configured.

## Deploy staging

```
poetry shell
./devops.py staging-create
./devops.py ansible-db staging
./devops.py ansible-app staging
./devops.py ansible-app-update staging
```
