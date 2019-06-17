#!/bin/bash

# ...Lists all non-base packages (packages installed after OS install).
# This is much faster than `apttool -I`.
# -Christopher Welborn 04-07-2019
appname="apttool-installed"
appversion="0.0.1"
apppath="$(readlink -f "${BASH_SOURCE[0]}")"
appscript="${apppath##*/}"
# appdir="${apppath%/*}"


function echo_err {
    # Echo to stderr.
    echo -e "$@" 1>&2
}

function fail {
    # Print a message to stderr and exit with an error status code.
    echo_err "$@"
    exit 1
}

function fail_usage {
    # Print a usage failure message, and exit with an error status code.
    print_usage "$@"
    exit 1
}

function list_installed {
    comm -13 \
      <(gzip -dc /var/log/installer/initial-status.gz | sed -n 's/^Package: //p' | sort) \
      <(comm -23 \
        <(dpkg-query -W -f='${Package}\n' | sed 1d | sort) \
        <(apt-mark showauto | sort) \
      )
}

function print_usage {
    # Show usage reason if first arg is available.
    [[ -n "$1" ]] && echo_err "\n$1\n"

    echo "$appname v. $appversion

    Usage:
        $appscript -h | -v
        $appscript [PATTERN...]

    Options:
        PATTERN       : One or more text/regex patterns to filter patterns.
                        This is just a shorter way to build multiple grep
                        patterns.
        -h,--help     : Show this message.
        -v,--version  : Show $appname version and exit.
    "
}

declare -a nonflags

for arg; do
    case "$arg" in
        "-h" | "--help")
            print_usage ""
            exit 0
            ;;
        "-v" | "--version")
            echo -e "$appname v. $appversion\n"
            exit 0
            ;;
        -*)
            fail_usage "Unknown flag argument: $arg"
            ;;
        *)
            nonflags+=("$arg")
    esac
done

if ((${#nonflags[@]})); then
    filterpat=""
    for pkgname in "${nonflags[@]}"; do
        [[ -n "$filterpat" ]] && filterpat="${filterpat}|"
        filterpat="${filterpat}($pkgname)"
    done
    list_installed | grep -E "$filterpat"
else
    list_installed
fi
