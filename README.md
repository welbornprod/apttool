# AptTool

This tool is for searching package names and descriptions in the apt-cache,
listing dependencies/reverse-dependencies and suggested packages.
It also handles installs, upgrades, removals/purges, and some other stuff
(reverse file searches, history searching). By using regex or plain-text you
can quickly find a package by part of a name, or part of a description.
The real package name, install-state, and description will be listed for all
packages that match (or don't match when --reverse  is used).
There are options to search names only, or omit the descriptions when printing
results.
The cache is searched while it is being loaded. This helps to cut down on the
time, by iterating over the packages only once instead of loading first, and
searching second.
Results are shown as they are found, so even if searching the packages is
taking too long you will normally see some results right away.
You can always `Ctrl + C` if you already found what you were looking for.
Using the `--containsfile`  option you can reverse-search a file to find out
what package it came from (if any).
You can also list all installed-files for a package using the `--files`
option.
Obviously, a package must already be installed to list the installed-files.
The `-V` option will show the current version information for a package,
and when coupled with `-a` , can show all available versions.
It will always tell you if the latest version is installed or not.
The install, remove, and purge options work. They don't offer much of an
improvement over the usual apt-get install|remove|purge methods, except maybe
some colorization, unless you just really hate typing and prefer
`apttool -i|-d|-p`.

## Dependencies

These are installable with `pip`, except maybe `apt_pkg`, which comes
installed on debian-based systems.

* `python-apt`: Provides the apt cache and related methods.
* `apt_pkg`: `python-apt` depends on this, as it provides helpers for
individual apt packages.
* `colr`: Provides terminal colors.
* `docopt`: Provides command-line argument parsing.

## Command Help
```
Usage:
    apttool -? | -h | -v
    apttool -c file [-C] [-n] [-q]
    apttool (-i | -d | -p) PACKAGES... [-C] [-q]
    apttool (-e | -f | -S) PACKAGES... [-C] [-q] [-s]
    apttool (-P | -R) PACKAGES... [-C] [-I | -N] [-q] [-s]
    apttool -H [QUERY] [COUNT] [-C] [-q]
    apttool (-l | -L) PACKAGES... [-C] [-q] [-s]
    apttool -u [-C] [-q]
    apttool -V PACKAGES... [-C] [-a] [-q] [-s]
    apttool PATTERNS... [-a] [-C] [-I | -N] [-D | -n] [-q] [-r] [-s] [-x]

Options:
    COUNT                        : Number of history lines to return.
    PACKAGES                     : One or many package names to try.
                                   If a file name is given, the names
                                   are read from the file. If '-' is
                                   given, names are read from stdin.
    PATTERNS                     : One or more text/regex patterns to
                                   search for. Multiple patterns will be
                                   joined with (.+)? if -a is used,
                                   otherwise they are joined with |.
    QUERY                        : Query to filter history with. The
                                   default is 'installed'.
    -a,--all                     : When viewing package version, list all
                                   available versions.

                                   When searching, join all patterns so
                                   they must all be found in the exact
                                   argument order.
                                   Like doing (arg1)(.+)?(arg2).
    -c file,--containsfile file  : Search all installed packages for an
                                   installed file using regex or text.
    -C,--nocolor                 : Disable colors always.
    -d,--delete                  : Uninstall/delete/remove a package.
    -D,--dev                     : Search for development packages.
    -e,--executables             : Show installed executables for a
                                   package.
                                   It just shows files installed to
                                   /bin directories.
    -f,--files                   : Show installed files for package.
                                   Multiple package names may be
                                   comma-separated, or passed with
                                   multiple flags.
    -?,--examples                : Show specific usage examples and exit.
    -h,--help                    : Show this help message and exit.
    -H,--history                 : Show package history.
                                   (installs, uninstalls, etc.)
    -i,--install                 : Install a package.
    -I,--INSTALLED               : When searching for a package, only
                                   include installed packages.
    -l,--locate                  : Determine whether or not a package
                                   exists. You can pass a file name to
                                   read from, or use - for stdin.
                                   Otherwise a full package name is
                                   needed. Multiple names can be passed.
    -L,--LOCATE                  : Same as --locate, but only shows
                                   existing packages that are found.
    -n,--names                   : When searching for packages, only
                                   search names, not descriptions.
                                   When searching with -c, don't use the
                                   full file path, only the file name.
    -N,--NOTINSTALLED            : When searching for a package, only
                                   include non-installed packages.
    -p,--purge                   : Purge the package completely,
                                   remove all configuration.
    -P,--dependencies            : List all dependencies for a package.
    -q,--quiet                   : Don't print extra status messages.
    -r,--reverse                 : When searching, return packages that
                                   DON'T match.
    -R,--reversedeps             : Show reverse dependencies.
    -s,--short                   : Use shorter output.
                                   When searching, don't print the
                                   description.
                                   When locating, don't show the install
                                   state.
    -S,--suggests                : Show package suggestions.
    -u,--update                  : Update the cache.
                                   ..Just like `apt-get update`.
    -v,--version                 : Show version and exit.
    -V,--VERSION                 : Show a package's installed or available
                                   versions.
    -x,--ignorecase              : Make the search query case-insensitive.
```

## Example Usage

Shows installed packages with 'foo' in the name or desc.
```
apttool foo -I
```

Show non-installed packages with 'bar' in the name only.
```bash
apttool bar -n -N
```

Show installed files for the 'python' package.
```bash
apttool -f python
```

Show installed executables for the 'python' package.
```bash
apttool -e python
```

Show suggested packages for the 'python' package.
```bash
apttool -S python
```

Determine whether a full package name exists in the cache.

This is quicker than a full search.
```bash
apttool -l pythonfoo
```

Search dpkg history for latest installs/half-installs.
```bash
apttool -H install
```

Show packages containing files with 'foo' in the path.
```bash
apttool -c foo
```

### Marker Legend:

Results are prepended with a marker that shows it's install state.

Marker | Description
:---:|---
i | Package is installed.
u | Package is not installed.
? | Package name was not found in the cache.

### Notes:

If no options are given, the default behaviour is to search for
packages by name and description, then print results.

## AptTool-Show

There is a little helper script included (`apttool-show.sh`), that basically
wraps `dpkg (-l|-s) PACKAGE...`, except it colorizes the output.

## Completions

There are `bash` and `oh-my-zsh` completion files included for the `apttool`
command. To install them just copy them into `/etc/bash_completion.d/`:

## Installation

Clone the repo and symlink/copy the necessary files. `apttool.py` and
`apttool-show.sh` can be symlinked somewhere in `$PATH`.

```bash
git clone https://github.com/welbornprod/apttool
cd apttool

# Symlink the executables, assuming ~/.local/bin is in $PATH.
ln -s "$PWD/apttool.py" ~/.local/bin/apttool
ln -s "$PWD/aptool-show.sh" ~/.local/bin/apttool-show

# Copy the completion files.
# BASH
cp apttool_completions.sh /etc/bash_completion.d/apttool
# Oh-my-zsh
cp _apttool.sh ~/.oh-my-zsh/completions/_apttool
```

After that, you can run apttool with `apttool` and enjoy the basic
completions.
