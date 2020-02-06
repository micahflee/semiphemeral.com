#!/usr/bin/env python3
import click
import subprocess
import os
import datetime
import shutil
import tempfile
import tarfile
import json
import pipes

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
    with open(filename) as f:
        variables = json.loads(f.read())
    return variables


def _terraform_variables(deploy_environment):
    variables = _get_variables(os.path.join(_get_root_dir(), ".vars-terraform.json"))
    variables["deploy_environment"] = deploy_environment

    ansible_variables = _get_variables(
        os.path.join(_get_root_dir(), ".vars-ansible.json")
    )
    variables["domain"] = ansible_variables[deploy_environment]["domain"]

    terraform_vars = []
    for key in variables:
        terraform_vars.append("-var")
        terraform_vars.append(f"{key}={variables[key]}")

    return terraform_vars


def _ansible_variables(deploy_environment):
    ansible_vars = []

    # Add variables from .vars-ansible.json
    all_variables = _get_variables(os.path.join(_get_root_dir(), ".vars-ansible.json"))
    variables = all_variables[deploy_environment]
    variables["deploy_environment"] = deploy_environment

    for key in variables:
        ansible_vars.append("-e")
        ansible_vars.append(f"{key}={variables[key]}")

    # Add variables from terraform
    terraform_output = _get_terraform_output(deploy_environment)
    ansible_vars.append("-e")
    ansible_vars.append(f"database_uri={terraform_output['database_uri']}")

    return ansible_vars


def _get_root_dir():
    return os.path.dirname(os.path.realpath(__file__))


def _get_devops_ip():
    # get the current IP address
    r = requests.get("https://ifconfig.co/ip")
    if r.status_code != 200:
        click.echo("Error loading https://ifconfig.co/ip")
        return
    devops_ip = r.text.strip()
    return devops_ip


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
        return False

    return True


def _ansible_apply(deploy_environment, update_only=False):
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

    # Write the inventory file
    inventory_filename = _write_ansible_inventory(deploy_environment)

    # Run deploy playbook
    if not update_only:
        p = subprocess.run(
            ["ansible-playbook", "-i", inventory_filename]
            + _ansible_variables(deploy_environment)
            + ["deploy.yaml"],
            cwd=os.path.join(_get_root_dir(), "ansible"),
        )
        if p.returncode != 0:
            click.echo("Error running deploy ansible playbook")
            return False

    # Run update app playbook
    p = subprocess.run(
        ["ansible-playbook", "-i", inventory_filename, "-e", f"app_tgz={app_tgz}",]
        + _ansible_variables(deploy_environment)
        + ["update_app.yaml"],
        cwd=os.path.join(_get_root_dir(), "ansible"),
    )
    if p.returncode != 0:
        click.echo("Error running deploy ansible playbook")
        return False

    return True


def _ssh(deploy_environment, args=None):
    ip = _get_ip(deploy_environment)
    if not ip:
        return

    if not args:
        args = []
    args = ["ssh"] + args + [f"root@{ip}"]

    # SSH into the server
    args_str = " ".join(pipes.quote(s) for s in args)
    print(f"Executing: {args_str}")
    p = subprocess.run(args)
    if p.returncode != 0:
        click.echo("Error SSHing")
        return


def _get_terraform_output(deploy_environment):
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

    return terraform_output


def _get_ip(deploy_environment):
    # Make sure the IP is in there
    terraform_output = _get_terraform_output(deploy_environment)
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

    devops_ip = _get_devops_ip()

    # deploy with terraform, allowing all IPs for 80 and 443 for Let's Encrypt
    if not _terraform_apply(deploy_environment, [devops_ip], ["0.0.0.0/0", "::/0"]):
        return

    # configure the server
    if not _ansible_apply(deploy_environment):
        return

    # deploy with terraform again, this time only allowing the devops IP to access 80 and 443
    # (but all all IPs for production)
    if deploy_environment == "staging":
        if not _terraform_apply(deploy_environment, [devops_ip], [devops_ip]):
            return


@main.command()
@click.argument("deploy_environment", nargs=1)
def update_app(deploy_environment):
    """Just update the app on already-deployed infrastructure"""
    if not _validate_env(deploy_environment):
        return

    # configure the server
    _ansible_apply(deploy_environment, update_only=True)


@main.command()
@click.argument("deploy_environment", nargs=1)
@click.option(
    "--open-firewall",
    is_flag=True,
    default=False,
    help="Allow any IPs to connect, even if this is staging",
)
def terraform(deploy_environment, open_firewall):
    """Re-apply terraform (uses current IP for devops IP)"""
    if not _validate_env(deploy_environment):
        return

    devops_ip = _get_devops_ip()

    if open_firewall or deploy_environment == "production":
        _terraform_apply(deploy_environment, [devops_ip], ["0.0.0.0/0", "::/0"])
    else:
        _terraform_apply(deploy_environment, [devops_ip], [devops_ip])


@main.command()
@click.argument("deploy_environment", nargs=1)
def destroy(deploy_environment):
    """Destroy infrastructure"""
    if not _validate_env(deploy_environment):
        return

    cwd = os.path.join(_get_root_dir(), f"terraform/{deploy_environment}")
    devops_ip = _get_devops_ip()

    if deploy_environment == "staging":
        ip_vars = [
            "-var",
            f"ssh_ips={json.dumps([devops_ip])}",
            "-var",
            f"inbound_ips={json.dumps([devops_ip])}",
        ]
    else:
        ip_vars = [
            "-var",
            f"ssh_ips={json.dumps([devops_ip])}",
            "-var",
            f'inbound_ips=["0.0.0.0/0","::/0"]',
        ]

    # terraform destroy
    p = subprocess.run(
        ["terraform", "destroy"] + _terraform_variables(deploy_environment) + ip_vars,
        cwd=cwd,
    )
    if p.returncode != 0:
        click.echo("Error running terraform destroy")
        return


@main.command()
@click.argument("deploy_environment", nargs=1)
def ssh(deploy_environment):
    """SSH to server"""
    if not _validate_env(deploy_environment):
        return
    _ssh(deploy_environment)


@main.command()
@click.argument("deploy_environment", nargs=1)
def forward_postgres(deploy_environment):
    """Forward the postgres port to localhost, using SSH"""
    if not _validate_env(deploy_environment):
        return
    _ssh(deploy_environment, ["-N", "-L", "5432:localhost:5432"])


if __name__ == "__main__":
    main()
