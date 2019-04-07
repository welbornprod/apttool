#!/bin/bash

# ...
# -Christopher Welborn 04-07-2019
appname="install-apttool-completion"
appversion="0.0.1"
apppath="$(readlink -f "${BASH_SOURCE[0]}")"
appscript="${apppath##*/}"
appdir="${apppath%/*}"

file_src="$appdir/apttool_completion.sh"
file_dest="/etc/bash_completion.d/apttool"
[[ -f "$file_src" ]] || {
    echo "Missing apttool completion file: $file_src" 1>&2
    exit 1
}

function completions_install {
    [[ -e "$file_dest" ]] && {
        fail "Completion file already installed: $file_dest"
    }
    sudo ln -s "$file_src" "$file_dest" || {
        fail "Unable to install completion file: $file_dest"
    }
}

function completions_uninstall {
    [[ -e "$file_dest" ]] || {
        fail "Completion file not installed: $file_dest"
    }
    sudo rm "$file_dest" || {
        fail "Unable to remove completion file: $file_dest"
    }
}

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

function is_installed {
    [[ -e "$file_dest" ]] && return 0
    return 1
}

function print_usage {
    # Show usage reason if first arg is available.
    [[ -n "$1" ]] && echo_err "\n$1\n"

    echo "$appname v. $appversion

    Installs and uninstalls apttool_completion.sh for BASH.

    Usage:
        $appscript -h | -v
        $appscript -i | -u

    Options:
        -h,--help       : Show this message.
        -i,--install    : Install apttool completion file.
        -u,--uninstall  : Uninstall apttool completion file.
        -v,--version    : Show $appname version and exit.
    "
}

declare -a nonflags
do_install=0
do_uninstall=0

for arg; do
    case "$arg" in
        "-h" | "--help")
            print_usage ""
            exit 0
            ;;
        "-i" | "--install")
            do_install=1
            ;;
        "-u" | "--uninstall")
            do_uninstall=1
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

if ((do_install)); then
    completions_install || exit 1
    echo "Completion file was installed: $file_dest"
elif ((do_uninstall)); then
    completions_uninstall || exit 1
    echo "Completion file was uninstalled: $file_dest"
else
    if is_installed; then
        echo "Bash completion file is installed: $file_dest"
        exit 0
    else
        echo "Bash completion file is not installed: $file_dest"
        exit 1
    fi
fi

exit 0
