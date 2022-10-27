#!/usr/bin/env python3
import click
import subprocess
import os
import shutil
import tempfile
import tarfile
import json
import pipes
import socket
import random
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import requests


def _validate_env(deploy_environment):
    if deploy_environment != "staging" and deploy_environment != "prod":
        click.echo("The environment must be either 'staging' or 'prod'")
        return False
    return True


def _find_available_port():
    with socket.socket() as tmpsock:
        while True:
            try:
                tmpsock.bind(("127.0.0.1", random.randint(10000, 20000)))
                break
            except OSError:
                pass
        _, port = tmpsock.getsockname()
    return port


def _get_variables(filename):
    with open(filename) as f:
        variables = json.loads(f.read())
    return variables


def _terraform_variables(deploy_environment):
    variables = _get_variables(os.path.join(_get_root_dir(), "vars-terraform.json"))
    variables["deploy_environment"] = deploy_environment

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


def _get_devops_ip():
    # get the current IP address
    r = requests.get("https://ifconfig.co/ip")
    if r.status_code != 200:
        click.echo("Error loading https://ifconfig.co/ip")
        return
    devops_ip = r.text.strip()
    return devops_ip


def _terraform_apply(deploy_environment, ssh_ips):
    cwd = os.path.join(_get_root_dir(), f"terraform/{deploy_environment}")

    # terraform init
    p = subprocess.run(["terraform", "init"], cwd=cwd)
    if p.returncode != 0:
        click.echo("Error running terraform init")
        return

    # terraform apply
    cmd = [
        "terraform",
        "apply",
        "-var",
        f"ssh_ips={json.dumps(ssh_ips)}"
    ] + _terraform_variables(deploy_environment)
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
    if playbook not in ["deploy-app.yaml", "deploy-db.yaml", "update-app.yaml"]:
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
    app_ip, db_ip, _ = _get_ips(deploy_environment)
    if not app_ip or not db_ip:
        return

    if server == "app":
        ip = app_ip
    elif server == "db":
        ip = db_ip

    if not args:
        args = []
    args = ["ssh"] + args + [f"root@{ip}"]

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
        or ("db_ip" not in terraform_output)
        or ("db_private_ip" not in terraform_output)
    ):
        print("Missing terraform output. Did you run `terraform apply` successfully?")
        return False

    return (
        terraform_output["app_ip"],
        terraform_output["db_ip"],
        terraform_output["db_private_ip"],
    )


def _write_ansible_inventory(deploy_environment):
    app_ip, db_ip, _ = _get_ips(deploy_environment)
    if not app_ip or not db_ip:
        return

    # Create the ansible inventory file
    inventory_filename = os.path.join(
        _get_root_dir(), f"ansible/inventory-{deploy_environment}"
    )
    with open(inventory_filename, "w") as f:
        f.write("[app]\n")
        f.write(f"{app_ip}\n")
        f.write("\n")
        f.write("[db]\n")
        f.write(f"{db_ip}\n")

    return inventory_filename


@click.group()
def main():
    """Deploy semiphemeral.com"""


@main.command()
@click.argument("deploy_environment", nargs=1)
def ansible_app(deploy_environment):
    """Deploy and configure infrastructure app server"""
    if not _validate_env(deploy_environment):
        return

    if not _ansible_apply(deploy_environment, "deploy-app.yaml"):
        return


@main.command()
@click.argument("deploy_environment", nargs=1)
def ansible_db(deploy_environment):
    """Deploy and configure infrastructure db server"""
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

    if open_firewall or deploy_environment == "prod":
        _terraform_apply(deploy_environment, [devops_ip])
    else:
        _terraform_apply(
            deploy_environment, ["0.0.0.0/0", "::/0"]
        )


@main.command()
def destroy_staging():
    """Destroy staging infrastructure"""
    deploy_environment = "staging"

    cwd = os.path.join(_get_root_dir(), f"terraform/{deploy_environment}")
    devops_ip = _get_devops_ip()

    ip_vars = [
        "-var",
        f"ssh_ips={json.dumps([devops_ip])}"
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
        f"postbird connection URL: postgres://{variables['postgres_user']}:{variables['postgres_password']}@127.0.0.1:5432/{variables['postgres_db']}"
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
def backup_save_db(deploy_environment):
    """Save db backup"""
    if not _validate_env(deploy_environment):
        return

    _, db_ip, _ = _get_ips(deploy_environment)

    # Save the backup
    _ssh(deploy_environment, "db", cmds=["/db/backup.sh"])

    # Download the backup
    subprocess.run(["scp", f"root@{db_ip}:/db/mnt/semiphemeral-*.sql.gz", "./backups"])

    # Delete the backup
    _ssh(deploy_environment, "db", cmds=["rm", "/db/mnt/semiphemeral-*.sql.gz"])


@main.command()
@click.argument("deploy_environment", nargs=1)
@click.argument("backup_filename", nargs=1)
def backup_restore_db(deploy_environment, backup_filename):
    """Restore db backup"""
    if not _validate_env(deploy_environment):
        return

    _, db_ip, _ = _get_ips(deploy_environment)

    # Validate
    backup_type = None
    if backup_filename.endswith(".sql.gz"):
        backup_type = "db"
    else:
        click.echo("Backup must be a .sql.gz")
        return

    basename = os.path.basename(backup_filename)

    # Upload the backup
    subprocess.run(["scp", backup_filename, f"root@{db_ip}:/db/mnt/"])

    # Restore the backup
    _ssh(deploy_environment, "db", cmds=["/db/restore.sh", basename])


@main.command()
@click.argument("deploy_environment", nargs=1)
def backup_save_app(deploy_environment):
    """Save app backup"""
    if not _validate_env(deploy_environment):
        return

    app_ip, _, _ = _get_ips(deploy_environment)

    # Save the backup
    _ssh(deploy_environment, "app", cmds=["/opt/semiphemeral/backup.sh"])

    # Download the backup
    subprocess.run(
        ["scp", f"root@{app_ip}:/opt/semiphemeral/semiphemeral-*.tar.gz", "./backups"]
    )

    # Delete the backup
    _ssh(
        deploy_environment,
        "app",
        cmds=["rm", "/opt/semiphemeral/semiphemeral-*.tar.gz"],
    )


@main.command()
@click.argument("deploy_environment", nargs=1)
@click.argument("backup_filename", nargs=1)
def backup_restore_app(deploy_environment, backup_filename):
    """Restore app backup"""
    if not _validate_env(deploy_environment):
        return

    app_ip, _, _ = _get_ips(deploy_environment)

    # Validate
    backup_type = None
    if backup_filename.endswith(".tar.gz"):
        backup_type = "app"
    else:
        click.echo("Backup must be a .tar.gz file")
        return

    basename = os.path.basename(backup_filename)

    # Upload the backup
    subprocess.run(["scp", backup_filename, f"root@{app_ip}:/opt/semiphemeral/"])

    # Restore the backup
    _ssh(deploy_environment, "db", cmds=["/opt/semiphemeral/restore.sh", basename])


@main.command()
def backup_prod_to_staging():
    """Create backup on prod, restore it to"""
    _, prod_db_ip, _ = _get_ips("prod")
    _, staging_db_ip, _ = _get_ips("staging")

    # Generate an ssh key on prod
    _ssh(
        "prod",
        "db",
        cmds=["rm", "/root/.ssh/id_ed25519", "/root/.ssh/id_ed25519.pub"],
    )
    _ssh(
        "prod",
        "db",
        cmds=[
            "ssh-keygen",
            "-t",
            "ed25519",
            "-f",
            "/root/.ssh/id_ed25519",
            "-N",
            "''",
        ],
    )

    # Copy the public key to staging
    subprocess.run(
        [
            "scp",
            f"root@{prod_db_ip}:/root/.ssh/id_ed25519.pub",
            "./backups",
        ]
    )
    subprocess.run(
        [
            "ssh-copy-id",
            "-f",
            "-i",
            "./backups/id_ed25519.pub",
            f"root@{staging_db_ip}",
        ]
    )

    # Save the backup on prod
    _ssh("prod", "db", cmds=["/db/backup.sh"])

    # Find the filename
    backup_filename = (
        _ssh(
            "prod",
            "db",
            cmds=["ls", "/db/mnt/semiphemeral-*.sql.gz"],
            check_output=True,
        )
        .decode()
        .strip()
    )
    basename = os.path.basename(backup_filename)

    # Accept the db-staging host key
    _ssh(
        "prod",
        "db",
        cmds=[
            "ssh",
            "-oStrictHostKeyChecking=no",
            f"root@{staging_db_ip}:{backup_filename}",
            "id",
        ],
    )

    # Copy the backup from prod to staging
    _ssh(
        "prod",
        "db",
        cmds=[
            "rsync",
            "--progress",
            backup_filename,
            f"root@{staging_db_ip}:{backup_filename}",
        ],
    )

    # Restore the backup on staging
    _ssh("staging", "db", cmds=["/db/restore.sh", basename])

    # Delete the backup from prod
    if click.confirm("Are you ready to delete the backup on prod?"):
        _ssh(
            "prod",
            "db",
            cmds=["rm", backup_filename],
        )


if __name__ == "__main__":
    main()
