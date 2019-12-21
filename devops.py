#!/usr/bin/env python3
import click
import subprocess
import os
import datetime


def _validate_env(env):
    if env != "staging" and env != "prod":
        click.echo("The environment must be either 'staging' or 'prod'")
        return False
    return True


def _variables(mode):
    do_vars = ["-var", f"deploy_environment={mode}"]
    with open(os.path.join(_get_root_dir(), ".vars")) as f:
        for line in f.readlines():
            do_vars.append("-var")
            do_vars.append(line.strip())
    return do_vars


def _get_root_dir():
    return os.path.dirname(os.path.realpath(__file__))


def _deploy(mode):
    cwd = os.path.join(_get_root_dir(), f"terraform/{mode}")

    # terraform init
    p = subprocess.run(["terraform", "init"], cwd=cwd)
    if p.returncode != 0:
        click.echo("Error running terraform init")
        return

    # terraform apply
    p = subprocess.run(["terraform", "apply"] + _variables(mode), cwd=cwd)
    if p.returncode != 0:
        click.echo("Error running terraform apply")
        return


def _destroy(mode):
    cwd = os.path.join(_get_root_dir(), f"terraform/{mode}")

    # terraform destroy
    p = subprocess.run(["terraform", "destroy"] + _variables(mode), cwd=cwd)
    if p.returncode != 0:
        click.echo("Error running terraform destroy")
        return


def _configure(mode):
    inventory_filename = _write_ansible_inventory(mode)

    # Run ansible playbook
    p = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            inventory_filename,
            "-e",
            f"mode={mode}",
            "playbook.yaml",
        ],
        cwd=os.path.join(_get_root_dir(), "ansible"),
    )
    if p.returncode != 0:
        click.echo("Error running ansible playbook")
        return


def _ssh(mode):
    ip = _get_ip(mode)
    if not ip:
        return

    # SSH into the server
    p = subprocess.run(["ssh", "-i", f"~/.ssh/semiphemeral", f"root@{ip}"])
    if p.returncode != 0:
        click.echo("Error SSHing")
        return


def _get_ip(mode):
    # Get the terraform output
    terraform_output = {}
    try:
        cwd = os.path.join(_get_root_dir(), f"terraform/{mode}")
        out = subprocess.check_output(["terraform", "output"], cwd=cwd).decode()
    except subprocess.CalledProcessError:
        print("Did you run `terraform apply` successfully?")
        return
    for line in out.split("\n"):
        if "=" in line:
            parts = line.split("=")
            terraform_output[parts[0].strip()] = parts[1].strip()

    # Make sure the IP is in there
    if "app_ip" not in terraform_output:
        print(
            "Terraform output is missing `app_ip`. Did you run `terraform apply` successfully?"
        )
        return False

    return terraform_output["app_ip"]


def _write_ansible_inventory(mode):
    ip = _get_ip(mode)
    if not ip:
        return

    # Create the ansible inventory file
    inventory_filename = os.path.join(_get_root_dir(), f"ansible/inventory-{mode}")
    with open(inventory_filename, "w") as f:
        f.write(f"[eotk]\n")
        f.write(f"{ip} ssh_private_key_file=~/.ssh/onions-{mode}.pem\n")

    return inventory_filename


@click.group()
def main():
    """Deploy semiphemeral.com"""


@main.command()
@click.argument("env", nargs=1)
def deploy(env):
    """Deploy infrastructure"""
    if not _validate_env(env):
        return
    _deploy(env)


@main.command()
@click.argument("env", nargs=1)
def destroy(env):
    """Destroy infrastructure"""
    if not _validate_env(env):
        return
    _destroy(env)


@main.command()
@click.argument("env", nargs=1)
def config(env):
    """Configure server"""
    if not _validate_env(env):
        return
    _configure(env)


@main.command()
@click.argument("env", nargs=1)
def ssh(env):
    """SSH to server"""
    if not _validate_env(env):
        return
    _ssh(env)


if __name__ == "__main__":
    main()
