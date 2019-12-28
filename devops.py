#!/usr/bin/env python3
import click
import subprocess
import os
import datetime
import shutil
import tempfile
import tarfile
import json

import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import requests


def _validate_env(deploy_environment):
    if deploy_environment != "staging" and deploy_environment != "prod":
        click.echo("The environment must be either 'staging' or 'prod'")
        return False
    return True


def _get_variables(filename):
    variables = {}
    with open(filename) as f:
        for line in f.readlines():
            if line.strip() == "" or line.strip().startswith("#"):
                pass
            parts = line.strip().split("=")
            variables[parts[0].strip()] = parts[1].strip()
    return variables


def _terraform_variables(deploy_environment):
    variables = _get_variables(os.path.join(_get_root_dir(), ".vars-terraform"))
    variables["deploy_environment"] = deploy_environment

    terraform_vars = []
    for key in variables:
        terraform_vars.append("-var")
        terraform_vars.append(f"{key}={variables[key]}")

    return terraform_vars


def _ansible_variables(deploy_environment):
    variables = _get_variables(os.path.join(_get_root_dir(), ".vars-ansible"))
    variables["deploy_environment"] = deploy_environment

    ansible_vars = []
    for key in variables:
        ansible_vars.append("-e")
        ansible_vars.append(f"{key}={variables[key]}")

    return ansible_vars


def _get_root_dir():
    return os.path.dirname(os.path.realpath(__file__))


def _terraform_apply(deploy_environment, ssh_ips, inbound_ips):
    cwd = os.path.join(_get_root_dir(), f"terraform/{deploy_environment}")

    # terraform init
    p = subprocess.run(["terraform", "init"], cwd=cwd)
    if p.returncode != 0:
        click.echo("Error running terraform init")
        return

    # terraform apply
    p = subprocess.run(
        [
            "terraform",
            "apply",
            "-var",
            f"ssh_ips={json.dumps(ssh_ips)}",
            "-var",
            f"inbound_ips={json.dumps(inbound_ips)}",
        ]
        + _terraform_variables(deploy_environment),
        cwd=cwd,
    )
    if p.returncode != 0:
        click.echo("Error running terraform apply")
        return


def _configure(deploy_environment):
    # Move node_modules away
    tmp_dir = tempfile.TemporaryDirectory()
    frontend_node_modules_dir = os.path.join(
        _get_root_dir(), "app/frontend/node_modules"
    )
    frontend_node_modules_dir_exists = os.path.exists(frontend_node_modules_dir)
    if frontend_node_modules_dir_exists:
        shutil.move(frontend_node_modules_dir, tmp_dir.name)

    # Compress the app folder
    app_tgz = os.path.join(tmp_dir.name, "app.tgz")
    with tarfile.TarFile(app_tgz, mode="w") as tar:
        tar.add(os.path.join(_get_root_dir(), "app"), arcname="app")

    # Move node_modules back
    if frontend_node_modules_dir_exists:
        shutil.move(
            os.path.join(tmp_dir.name, "node_modules"), frontend_node_modules_dir
        )

    # Frontend and backend domains
    if deploy_environment == "staging":
        frontend_domain = "staging.semiphemeral.com"
        backend_domain = "api.staging.semiphemeral.com"
    else:
        frontend_domain = "semiphemeral.com"
        backend_domain = "api.semiphemeral.com"

    # Run ansible playbook
    inventory_filename = _write_ansible_inventory(deploy_environment)
    p = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            inventory_filename,
            "-e",
            f"app_tgz={app_tgz}",
            "-e",
            f"frontend_domain={frontend_domain}",
            "-e",
            f"backend_domain={backend_domain}",
        ]
        + _ansible_variables(deploy_environment)
        + ["playbook.yaml"],
        cwd=os.path.join(_get_root_dir(), "ansible"),
    )
    if p.returncode != 0:
        click.echo("Error running ansible playbook")


def _deploy(deploy_environment):
    # get the current IP address
    r = requests.get("https://ifconfig.co/ip")
    if r.status_code != 200:
        click.echo("Error loading https://ifconfig.co/ip")
        return
    devops_ip = r.text.strip()

    # deploy with terraform, allowing all IPs for 80 and 443 for Let's Encrypt
    _terraform_apply(deploy_environment, [devops_ip], ["0.0.0.0/0", "::/0"])

    # configure the server
    _configure(deploy_environment)

    # deploy with terraform again, this time only allowing the devops IP to access 80 and 443
    # (but all all IPs for production)
    if deploy_environment == "staging":
        _terraform_apply(deploy_environment, [devops_ip], [devops_ip])


def _destroy(deploy_environment):
    cwd = os.path.join(_get_root_dir(), f"terraform/{deploy_environment}")

    # terraform destroy
    p = subprocess.run(
        ["terraform", "destroy"] + _terraform_variables(deploy_environment), cwd=cwd
    )
    if p.returncode != 0:
        click.echo("Error running terraform destroy")
        return


def _ssh(deploy_environment):
    ip = _get_ip(deploy_environment)
    if not ip:
        return

    # SSH into the server
    p = subprocess.run(["ssh", f"root@{ip}"])
    if p.returncode != 0:
        click.echo("Error SSHing")
        return


def _get_ip(deploy_environment):
    # Get the terraform output
    terraform_output = {}
    try:
        cwd = os.path.join(_get_root_dir(), f"terraform/{deploy_environment}")
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


def _write_ansible_inventory(deploy_environment):
    ip = _get_ip(deploy_environment)
    if not ip:
        return

    # Create the ansible inventory file
    inventory_filename = os.path.join(
        _get_root_dir(), f"ansible/inventory-{deploy_environment}"
    )
    with open(inventory_filename, "w") as f:
        f.write(f"[app]\n")
        f.write(f"{ip}\n")

    return inventory_filename


@click.group()
def main():
    """Deploy semiphemeral.com"""


@main.command()
@click.argument("deploy_environment", nargs=1)
def deploy(deploy_environment):
    """Deploy and configure infrastructure"""
    if not _validate_env(deploy_environment):
        return
    _deploy(deploy_environment)


@main.command()
@click.argument("deploy_environment", nargs=1)
def destroy(deploy_environment):
    """Destroy infrastructure"""
    if not _validate_env(deploy_environment):
        return
    _destroy(deploy_environment)


@main.command()
@click.argument("deploy_environment", nargs=1)
def ssh(deploy_environment):
    """SSH to server"""
    if not _validate_env(deploy_environment):
        return
    _ssh(deploy_environment)


if __name__ == "__main__":
    main()
