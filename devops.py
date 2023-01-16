#!/usr/bin/env python3
import click
import subprocess
import os
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
    variables = _get_variables(os.path.join(_get_root_dir(), "vars-terraform.json"))

    ansible_variables = _get_variables(
        os.path.join(_get_root_dir(), "vars-ansible.json")
    )
    variables["domain"] = ansible_variables[deploy_environment]["domain"]

    terraform_vars = []
    for key in variables:
        terraform_vars.append("-var")
        terraform_vars.append(f"{key}={variables[key]}")

    return terraform_vars


def _ansible_variables(deploy_environment):
    ansible_vars = []

    # Add variables from vars-ansible.json
    all_variables = _get_variables(os.path.join(_get_root_dir(), "vars-ansible.json"))
    variables = all_variables[deploy_environment]
    variables["deploy_environment"] = deploy_environment

    for key in variables:
        ansible_vars.append("-e")
        ansible_vars.append(f"{key}={variables[key]}")

    # Add variables from terraform
    terraform_output = _get_terraform_output(deploy_environment)
    ansible_vars.append("-e")
    ansible_vars.append(f"db_private_ip={terraform_output['db_private_ip']}")

    return ansible_vars


def _get_root_dir():
    return os.path.dirname(os.path.realpath(__file__))


def _terraform_apply(deploy_environment, extra_vars=None):
    cwd = os.path.join(_get_root_dir(), f"terraform/{deploy_environment}")

    # terraform init
    p = subprocess.run(["terraform", "init"], cwd=cwd)
    if p.returncode != 0:
        click.echo("Error running terraform init")
        return

    # format extra_vars
    terraform_vars = []
    if extra_vars:
        for key in extra_vars:
            terraform_vars.append("-var")
            terraform_vars.append(f"{key}={extra_vars[key]}")

    # terraform apply
    cmd = (
        [
            "terraform",
            "apply",
        ]
        + _terraform_variables(deploy_environment)
        + terraform_vars
    )
    print(cmd)
    p = subprocess.run(
        cmd,
        cwd=cwd,
    )
    if p.returncode != 0:
        click.echo("Error running terraform apply")
        return False

    return True


def _ansible_apply(deploy_environment, playbook, extra_args=[]):
    if playbook not in [
        "deploy-app.yaml",
        "deploy-db.yaml",
        "update-app.yaml",
        "deploy-bastion.yaml",
    ]:
        click.echo("Invalid playbook")
        return False

    # Write the inventory file
    inventory_filename = _write_ansible_inventory(deploy_environment)

    # Run the playbook
    p = subprocess.run(
        ["ansible-playbook", "-i", inventory_filename]
        + extra_args
        + _ansible_variables(deploy_environment)
        + [playbook],
        cwd=os.path.join(_get_root_dir(), "ansible"),
    )
    if p.returncode != 0:
        click.echo("Error running deploy ansible playbook")
        return False

    return True


def _ssh(deploy_environment, server, args=None, check_output=False, cmds=None):
    terraform_output = _get_terraform_output("prod")
    bastion_ip = terraform_output["bastion_ip"]

    app_ip, app_private_ip, db_ip, db_private_ip = _get_ips(deploy_environment)
    if not app_ip or not db_ip:
        return

    if deploy_environment == "prod":
        if server == "app":
            ip = app_private_ip
        elif server == "db":
            ip = db_private_ip
    elif deploy_environment == "staging":
        if server == "app":
            ip = app_ip
        elif server == "db":
            ip = db_ip

    if not args:
        args = []
    args = ["ssh", "-J", f"root@{bastion_ip}"] + args + [f"root@{ip}"]

    if not cmds:
        cmds = []
    args = args + cmds

    # SSH into the server
    args_str = " ".join(pipes.quote(s) for s in args)
    print(f"Executing: {args_str}")
    if check_output:
        return subprocess.check_output(args)
    else:
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
            key = line.split("=")[0].strip()
            val = "=".join(line.split("=")[1:]).strip()
            terraform_output[key] = val.lstrip('"').rstrip('"')

    return terraform_output


def _get_ips(deploy_environment):
    terraform_output = _get_terraform_output(deploy_environment)
    if (
        ("app_ip" not in terraform_output)
        or ("app_private_ip" not in terraform_output)
        or ("db_ip" not in terraform_output)
        or ("db_private_ip" not in terraform_output)
    ):
        print("Missing terraform output. Did you run `terraform apply` successfully?")
        return False

    return (
        terraform_output["app_ip"],
        terraform_output["app_private_ip"],
        terraform_output["db_ip"],
        terraform_output["db_private_ip"],
    )


def _write_ansible_inventory(deploy_environment):
    terraform_output = _get_terraform_output("prod")
    bastion_ip = terraform_output["bastion_ip"]

    app_ip, app_private_ip, db_ip, db_private_ip = _get_ips(deploy_environment)
    if not app_ip or not db_ip:
        return

    # Create the ansible inventory file
    inventory_filename = os.path.join(
        _get_root_dir(), f"ansible/inventory-{deploy_environment}"
    )
    with open(inventory_filename, "w") as f:
        f.write("[app]\n")
        if deploy_environment == "staging":
            f.write(f"{app_ip}\n")
        else:
            f.write(f"{app_private_ip}\n")
        f.write("[app:vars]\n")
        f.write(f"ansible_ssh_common_args='-J root@{bastion_ip}'\n")
        f.write("\n")
        f.write("[db]\n")
        if deploy_environment == "staging":
            f.write(f"{db_ip}\n")
        else:
            f.write(f"{db_private_ip}\n")
        f.write("[db:vars]\n")
        f.write(f"ansible_ssh_common_args='-J root@{bastion_ip}'\n")
        f.write("\n")

        if deploy_environment == "prod":
            f.write("[bastion]\n")
            f.write(f"{bastion_ip}\n")

    return inventory_filename


@click.group()
def main():
    """Deploy semiphemeral.com"""


@main.command()
def ansible_bastion():
    """Deploy and configure bastion server"""
    _ansible_apply("prod", "deploy-bastion.yaml")


@main.command()
@click.argument("deploy_environment", nargs=1)
def ansible_app(deploy_environment):
    """Deploy and configure app server"""
    if not _validate_env(deploy_environment):
        return

    if not _ansible_apply(deploy_environment, "deploy-app.yaml"):
        return


@main.command()
@click.argument("deploy_environment", nargs=1)
def ansible_db(deploy_environment):
    """Deploy and configure db server"""
    if not _validate_env(deploy_environment):
        return

    if not _ansible_apply(deploy_environment, "deploy-db.yaml"):
        return


@main.command()
@click.argument("deploy_environment", nargs=1)
def ansible_app_update(deploy_environment):
    """Update the app on already-deployed app server"""
    if not _validate_env(deploy_environment):
        return

    # Move node_modules away
    tmp_dir = tempfile.TemporaryDirectory()
    frontend_node_modules_dir = os.path.join(
        _get_root_dir(), "app/src/frontend/node_modules"
    )
    frontend_node_modules_dir_exists = os.path.exists(frontend_node_modules_dir)
    if frontend_node_modules_dir_exists:
        shutil.move(frontend_node_modules_dir, tmp_dir.name)
    admin_tmp_dir = tempfile.TemporaryDirectory()
    admin_frontend_node_modules_dir = os.path.join(
        _get_root_dir(), "app/src/admin-frontend/node_modules"
    )
    admin_frontend_node_modules_dir_exists = os.path.exists(
        admin_frontend_node_modules_dir
    )
    if admin_frontend_node_modules_dir_exists:
        shutil.move(admin_frontend_node_modules_dir, admin_tmp_dir.name)

    # Compress the app folder
    app_tgz = os.path.join(tmp_dir.name, "app.tgz")
    with tarfile.TarFile(app_tgz, mode="w") as tar:
        tar.add(os.path.join(_get_root_dir(), "app"), arcname="app")

    # Move node_modules back
    if frontend_node_modules_dir_exists:
        shutil.move(
            os.path.join(tmp_dir.name, "node_modules"), frontend_node_modules_dir
        )
    if admin_frontend_node_modules_dir_exists:
        shutil.move(
            os.path.join(admin_tmp_dir.name, "node_modules"),
            admin_frontend_node_modules_dir,
        )

    _ansible_apply(deploy_environment, "update-app.yaml", ["-e", f"app_tgz={app_tgz}"])


@main.command()
def staging_create():
    """Create staging infrastructure"""
    snapshot_name = "backup-for-staging"

    # Save a snapshot of db-production
    print("creating db-production snapshot")
    volumes = json.loads(
        subprocess.check_output(
            ["doctl", "compute", "volume", "list", "--output", "json"]
        )
    )
    volume_id = None
    for volume in volumes:
        if volume["name"] == "db-production":
            volume_id = volume["id"]
            break

    if not volume_id:
        print("volume with name 'db-production' not found")
        return
    subprocess.run(
        [
            "doctl",
            "compute",
            "volume",
            "snapshot",
            volume_id,
            "--snapshot-name",
            snapshot_name,
        ]
    )

    # Get the snapshot_id
    snapshots = json.loads(
        subprocess.check_output(
            ["doctl", "compute", "snapshot", "list", "--output", "json"]
        )
    )
    snapshot_id = None
    for snapshot in snapshots:
        if snapshot["name"] == snapshot_name:
            snapshot_id = snapshot["id"]
            break

    if not snapshot_id:
        print("snapshot not found, weird ...")
        return

    # Get the bastion IP
    terraform_output = _get_terraform_output("prod")
    bastion_ip = terraform_output["bastion_ip"]

    # Terraform apply staging
    _terraform_apply(
        "staging", {"db_volume_snapshot_id": snapshot_id, "bastion_ip": bastion_ip}
    )

    # Delete snapshot
    print("deleting db-production snapshot")
    subprocess.run(["doctl", "compute", "snapshot", "delete", "--force", snapshot_id])


@main.command()
def staging_destroy():
    """Destroy staging infrastructure"""
    cwd = os.path.join(_get_root_dir(), "terraform/staging")

    # format extra_vars
    terraform_output = _get_terraform_output("prod")
    bastion_ip = terraform_output["bastion_ip"]
    terraform_vars = [
        "-var",
        f"bastion_ip={terraform_output['bastion_ip']}",
        "-var",
        f"db_volume_snapshot_id=null",
    ]

    # terraform destroy
    cmd = (
        [
            "terraform",
            "destroy",
        ]
        + _terraform_variables("staging")
        + terraform_vars
    )
    print(cmd)
    p = subprocess.run(
        cmd,
        cwd=cwd,
    )
    if p.returncode != 0:
        click.echo("Error running terraform destroy")


@main.command()
def ssh_bastion():
    """SSH to bastion server"""
    terraform_output = _get_terraform_output("prod")
    ip = terraform_output["bastion_ip"]

    args = ["ssh", f"root@{ip}"]
    args_str = " ".join(pipes.quote(s) for s in args)
    print(f"Executing: {args_str}")
    subprocess.run(args)


@main.command()
@click.argument("deploy_environment", nargs=1)
def ssh_app(deploy_environment):
    """SSH to app server"""
    if not _validate_env(deploy_environment):
        return
    _ssh(deploy_environment, "app")


@main.command()
@click.argument("deploy_environment", nargs=1)
def ssh_db(deploy_environment):
    """SSH to db server"""
    if not _validate_env(deploy_environment):
        return
    _ssh(deploy_environment, "db")


@main.command()
@click.argument("deploy_environment", nargs=1)
def forward_postgres(deploy_environment):
    """Forward the postgres port to localhost, using SSH"""
    if not _validate_env(deploy_environment):
        return

    # load ansible variables
    variables = _get_variables(os.path.join(_get_root_dir(), "vars-ansible.json"))[
        deploy_environment
    ]

    terraform_output = _get_terraform_output(deploy_environment)
    click.echo(
        f"postbird connection URL: postgresql://{variables['postgres_user']}:{variables['postgres_password']}@127.0.0.1:5432/{variables['postgres_db']}"
    )
    _ssh(
        deploy_environment,
        "db",
        [
            "-N",
            "-L",
            f"5432:{terraform_output['db_private_ip']}:5432",
        ],
    )


@main.command()
@click.argument("deploy_environment", nargs=1)
def forward_rq_dashboard(deploy_environment):
    """Forward the rq-dashboard port to localhost, using SSH"""
    if not _validate_env(deploy_environment):
        return

    click.echo("rq-dashboard: http://127.0.0.1:9181")
    _ssh(
        deploy_environment,
        "app",
        [
            "-N",
            "-L",
            f"9181:127.0.0.1:9181",
        ],
    )


@main.command()
@click.argument("deploy_environment", nargs=1)
def update_app_code(deploy_environment):
    """Just rsync the app code"""
    if not _validate_env(deploy_environment):
        return

    terraform_output = _get_terraform_output("prod")
    bastion_ip = terraform_output["bastion_ip"]

    app_ip, app_private_ip, db_ip, db_private_ip = _get_ips(deploy_environment)

    if deploy_environment == "prod":
        ip = app_private_ip
    elif deploy_environment == "staging":
        ip = app_ip

    args = [
        "rsync",
        "-av",
        "--delete",
        "--exclude",
        "app/docker-compose.yaml",
        "--exclude",
        "alembic.ini",
        "--exclude",
        "frontend/node_modules",
        "--exclude",
        "admin-frontend/node_modules",
        "-e",
        f"ssh -J root@{bastion_ip}",
        "app/src/",
        f"root@{ip}:/opt/semiphemeral/app/src",
    ]
    args_str = " ".join(pipes.quote(s) for s in args)
    print(f"Executing: {args_str}")
    subprocess.run(args)


if __name__ == "__main__":
    main()
