# aurutilsutils

Utilities extending [aurutils].

Tools included:

* `aur-smartsync` is the main tool and offers a declarative (config file based)
  approach to AUR package management on top of [aurutils]. See [below](#config-file)
  for file format.
* `aur-unmanaged` provides some sanity checking of the configuration file and
  system state, in particular it will list packages in `file://` repositories
  that are not in the config file nor a dependency of a package in the config
  file.
* `aur-move-helper` is a utility to help transition from a local AUR mono-repo
  to split repositories based on a newly written config file.


## Config file

The config file is read from `~/.config/aurutilsutils/sync.yml`. The expected
file format can be seen in this example:

```yaml
build_flags:
    - "--extra-flags"
    - "to aur build"
repositories:
    custom-basics:
        - aurutils
        - aurutilsutils-git
    some-other-repo:
        - some-package
        - ...
package_overrides:
    some-package:
        chroot: False
```

### Build flags

Extra flags to always pass to `aur build` can be listed in the `build_flags`
section. This can be used to pass `--remove` to remove old versions, or specify
a specific `makepkg.conf`.

### Repositories

`repositories` is the most important part of the configuration. It specifies
what packages should exist in the local AUR repositories and which packages go
into which repositories.

This is a package name, *not* a pkgbase name. However if this refers to a split
package, other parts of the same package will be put in the same repository
automatically.

In addition, any AUR dependencies that a listed package pulls in will be put in
the same repository as long as there are no conflicts. A conflict arises when
packages in different repositories pull in the same dependency. In this case
the dependency must be manually assigned to one of the repositories.

### Package overrides

By default packages are built in chroot (`aur build --chroot`) but this can be
overriden per package in the `package_overrides` section. Currently no other
package specific overrides exist.

[aurutils]: https://github.com/AladW/aurutils
