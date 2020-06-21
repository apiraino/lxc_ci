# Manage CI using an LXC container
This guide will get you through the basic setup of an LXC container in userspace.

### Setup and installation

#### 1. Install packages
```
$ sudo apt-get install lxc
```
Python3 bindings is also installed (pkg `python3-lxc`)

The usage of `virtualenv` is always advisable to keep your system tidied up and not cluttered with tons of Python packages, sometimes in conflict with each other.

```
$ virtualenv virtual
$ source virtual/bin/activate
$ pip install -r requirements.txt
```
Note that the Python3 LXC bindings rely on shared objects installed system-wide earlier. The virtualenv is not aware of these libaries, you need to let it know. A symlink is enough:
```
$ cd virtual/lib/<your_python3_version>/site-packages/
$ ln -s /usr/lib/python3/dist-packages/_lxc-0.1.egg-info
$ ln -s /usr/lib/python3/dist-packages/_lxc.cpython-35m-x86_64-linux-gnu.so
$ ln -s /usr/lib/python3/dist-packages/lxc
```
Test with `python -c "import lxc"`.

#### 2. Allow current `$USER` permissions
We don't need the container to run as root. Your user must be allowed sufficient namespace access (`man 7 user_namespaces`) and virtual networking creation (replace `your_user` with your username):
```
$ grep $USER /etc/subuid /etc/subgid
/etc/subuid:your_user:100000:65536
/etc/subgid:your_user:100000:65536

$ cat /etc/lxc/default.conf
lxc.network.type = veth
lxc.network.link = lxcbr0
lxc.network.flags = up
lxc.network.hwaddr = 00:16:3e:xx:xx:xx

$ cat /etc/lxc/lxc-usernet
# USERNAME TYPE BRIDGE COUNT
your_user veth lxcbr0 2 # allow creation of two virtual network nterfaces
```

The above namespace mask is default since Ubuntu 14.04; in case it's not, run (replace `your_user` with your username):
```
$ sudo usermod -v 100000-165536 -w 100000-165536 your_user
```

#### 3. Create ~/.config/lxc/default.conf:
Default LXC container config
```
lxc.include = /etc/lxc/default.conf
lxc.id_map = u 0 100000 1000
lxc.id_map = g 0 100000 1000
lxc.id_map = u 1000 1000 1
lxc.id_map = g 1000 1000 1
lxc.id_map = u 1001 101001 64535
lxc.id_map = g 1001 101001 64535
```

#### 4. Play
Now you should be able to use the script `cli.py` (inspired by [Stéphane Graber's tutorials series](https://www.stgraber.org)) to manage an LXC container for your CI.

You need to set an ENV variable to be able to download source from a repo:
```
export GIT_URL=https://<user>:<pass>@url/reponame.git
```
You need to use the `https` protocol since the container is ephemeral and you cannot store or cache anywhere GIT credentials.

The file `config_local.json` is just a set of credentials for the tests to access external services, YMMV.
