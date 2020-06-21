# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os
import shutil
import lxc
import sys
from itertools import cycle
import click
from subprocess import call

import getpass
CURRENT_USER = getpass.getuser()

# [d]istribution, [r]elease, [a]rch
DEFAULT_CONTAINER = 'ubuntu,xenial,amd64'
DEFAULT_CONTAINER_NAME = 'test'
# credentials to checkout code
GIT_URL = os.environ.get('GIT_URL')
SRC_DIR = 'quokky_backend'
# Tests need some auth to access external services
SECRETS_FILE = 'config_local.json'
SECRETS_DIR = '/tmp/.secrets'
# export the container to share it with your friends
CONTAINER_ARCHIVE = '/tmp/container_rootfs.tar.gz'


def start_container(c):
    loader = ['\\', '|', '/', '-']
    loader_cycle = cycle(loader)

    if c.state != 'STARTED':
        c.start()
    while(c.state != 'RUNNING'):
        sys.stdout.write("[{}] Waiting for container '{}' to start ...\r".format(
            next(loader_cycle), c.name))
        sys.stdout.flush()
    # Wait for network connectivity
    if not c.get_ips(timeout=30):
        click.echo("Failed to get connectivity for container {}.\n".format(c.name), err=True)
        return
    click.echo("Container '{}' started".format(c.name))


def stop_container(c):
    if c.running:
        if not c.stop():
            click.echo("Failed to stop the container {}".format(c.name), err=True)
        if not c.shutdown(30):
            click.echo("Failed to cleanly shutdown container {}, forcing.".format(c.name), err=True)
            return False
    click.echo("Container '{}' stopped".format(c.name))
    return True


@click.group()
def tool():
    """Script to manage CI using an LXC container"""
    pass


@tool.command()
@click.option('--container-name', help='Container name (default: {})'.format(DEFAULT_CONTAINER_NAME),
              required=False, default=DEFAULT_CONTAINER_NAME)
@click.option('--container-data',
              help='CSV data to fetch+create the container (default: {})"'.format(DEFAULT_CONTAINER),
              type=str, required=False, default=DEFAULT_CONTAINER)
def create(container_name, container_data):
    """Create an LXC container"""

    if not os.path.exists(SECRETS_DIR):
        os.makedirs(SECRETS_DIR)
    shutil.copy(SECRETS_FILE, SECRETS_DIR)

    d, r, a = container_data.split(',')
    c = lxc.Container(container_name)
    if c.defined:
        click.echo("Container {} already exist".format(container_name))
        return

    # Create container rootfs
    click.echo("Creating container {} ...".format(container_name))
    if not c.create("download", lxc.LXC_CREATE_QUIET, {"dist": d, "release": r, "arch": a}):
        click.echo("Failed to create the container rootfs", err=True)
        return
    click.echo("Created container {}".format(container_name))


@tool.command()
@click.option('--container-name', help='Container name (default: {})'.format(DEFAULT_CONTAINER_NAME),
              required=False, default=DEFAULT_CONTAINER_NAME)
def destroy(container_name):
    """Stop and destroy a container"""
    c = lxc.Container(container_name)
    stop_container(c)
    if not c.destroy():
        click.echo("Failed to destroy container {}.\n".format(container_name), err=True)
    click.echo("Destroyed container {}".format(container_name))


@tool.command()
@click.option('--container-name', help='Container name (default: {})'.format(DEFAULT_CONTAINER_NAME),
              required=False, default=DEFAULT_CONTAINER_NAME)
def provision(container_name):
    """Install all needed packages in container"""
    def _mongodb_small_files():
        # translates to: echo 'smallfiles = true' >> /etc/mongodb.conf
        with open('/etc/mongodb.conf', 'a') as fp:
            fp.write("\nsmallfiles = true\n")

    container = lxc.Container(container_name)
    start_container(container)

    # install and configure stuff
    container.attach_wait(lxc.attach_run_command, ["apt-get", "update"])
    container.attach_wait(lxc.attach_run_command, ["apt-get", "dist-upgrade", "-y"])
    container.attach_wait(lxc.attach_run_command, ['apt-get', 'install', '-qy', 'python-pip', 'python-dev', 'libffi-dev'])
    container.attach_wait(lxc.attach_run_command, ['pip', 'install', '--upgrade', '-q', 'pip'])
    container.attach_wait(lxc.attach_run_command, ['pip', 'install', '--upgrade', '-q', 'virtualenv'])
    container.attach_wait(lxc.attach_run_command, ['apt-get', 'install', '-qy', 'rabbitmq-server'])
    container.attach_wait(lxc.attach_run_command, ['locale-gen', 'it_IT.UTF-8'])
    container.attach_wait(lxc.attach_run_command, ['apt-get', 'install', '-qy', 'postgresql', 'postgresql-server-dev-all'])
    container.attach_wait(lxc.attach_run_command, ['service', 'postgresql', 'start'])
    container.attach_wait(lxc.attach_run_command, ['service', 'postgresql@9.4-main', 'start'])
    container.attach_wait(lxc.attach_run_command, ['apt-get', 'install', '-qy', 'memcached', 'mongodb-server', 'git'])
    container.attach_wait(lxc.attach_run_command, ['apt-get', 'clean', '-y'])
    container.attach_wait(_mongodb_small_files)
    container.attach_wait(lxc.attach_run_command, ['service', 'mongodb', 'start'])


@tool.command()
@click.option('--container-name', help='Container name (default: {})'.format(DEFAULT_CONTAINER_NAME),
              required=False, default=DEFAULT_CONTAINER_NAME)
@click.option('--branch', help='ranch name (default=develop)', type=str, required=False, default='develop')
def clone_backend(container_name, branch):
    """Clone backend repository"""
    if not GIT_URL:
        click.echo("\nGIT url not set. Please export ENV variable:")
        click.echo("\n\texport GIT_URL=https://<user>:<pass>@url/reponame.git")
        return

    container = lxc.Container(container_name)
    start_container(container)
    if True != container.attach_wait(lxc.attach_run_command, ['git']):
        provision(['--container-name', container_name])
    container.attach_wait(lxc.attach_run_command, ['rm', '-rf', SRC_DIR])
    container.attach_wait(lxc.attach_run_command, ['git', 'clone', '-b', branch, GIT_URL, SRC_DIR])
    container.attach_wait(lxc.attach_run_command, ['cp', '-r', '.secrets', SRC_DIR])


@tool.command()
@click.option('--container-name', help='Container name (default: {})'.format(DEFAULT_CONTAINER_NAME),
              required=False, default=DEFAULT_CONTAINER_NAME)
def setup_backend(container_name):
    """Install Python packages, init DB"""

    def _pip_install():
        call(['pip', 'install', '-r', 'requirements/dev.txt'], cwd=SRC_DIR)

    container = lxc.Container(container_name)
    start_container(container)
    container.attach_wait(lxc.attach_run_command,
                          ['sudo', '-u', 'postgres', 'psql', '-c drop database quokky'])
    container.attach_wait(lxc.attach_run_command,
                          ['sudo', '-u', 'postgres', 'psql', '-c drop user django'])
    container.attach_wait(lxc.attach_run_command,
                          ['sudo', '-u', 'postgres', 'psql', '-c create user django with createdb password \'django\''])
    container.attach_wait(lxc.attach_run_command,
                          ['sudo', '-u', 'postgres', 'psql', '-c create database quokky with ENCODING "UTF-8" LC_COLLATE="it_IT.UTF-8" LC_CTYPE="it_IT.UTF-8" template=template0 owner=django;'])
    container.attach_wait(_pip_install)


@tool.command()
@click.option('--container-name', help='Container name (default: {})'.format(DEFAULT_CONTAINER_NAME),
              required=False, default=DEFAULT_CONTAINER_NAME)
def run_tests(container_name):
    """Run tests and report coverage"""
    def _fab_check():
        ret_code = call(['fab', 'check'], cwd=SRC_DIR)
        click.echo("Static code check returned {}: {}".format(ret_code, 'failed' if ret_code != 0 else 'success'))

    def _fab_test():
        ret_code = call(['fab', 'test:coverage=1'], cwd=SRC_DIR)
        click.echo("Tests returned {}: {}".format(ret_code, 'failed' if ret_code != 0 else 'success'))

    def _fab_coverage():
        ret_code = call(['fab', 'coverage_report'], cwd=SRC_DIR)
        click.echo("Coverage report returned {}: {}".format(ret_code, 'failed' if ret_code != 0 else 'success'))

    container = lxc.Container(container_name)
    start_container(container)
    container.attach_wait(_fab_check)
    container.attach_wait(_fab_test)
    container.attach_wait(_fab_coverage)

if __name__ == '__main__':
    tool()
