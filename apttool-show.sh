#!/bin/bash

# This is just an alias for `dpkg (-l|-s) PACKAGE...`, with colors.
# -Christopher Welborn 11-16-2016
appname="apttool-show"
appversion="0.0.2"
apppath="$(readlink -f "${BASH_SOURCE[0]}")"
appscript="${apppath##*/}"
# appdir="${apppath%/*}"

# Some color constants.
red='\e[0;31m'
yellow='\e[0;33m'
blue='\e[0;34m'
lightblue='\e[38;5;39m'
cyan='\e[0;36m'
green='\e[0;32m'
# No Color, normal/reset.
NC='\e[0m'

function echo_err {
    # Echo to stderr.
    [[ -t 2 ]] && printf "%b" "$red" 1>&2
    printf "\n%s" "$@" 1>&2
    [[ -t 2 ]] && printf "%b" "$NC" 1>&2
    printf "\n" 1>&2
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

function list_pkgs {
    # Use `dpkg -l` to list packages concisely.
    if ! output="$(dpkg -l "$@" 2>&1)"; then
        if apt-cache show "$@" &>/dev/null; then
            echo_err "\`dpkg\` will not work for at least one of these packages."
            echo_err "Use \`apttool-show PACKAGES...\` instead."
        else
            echo_err "$output"
        fi
        return 1
    fi
    printf "%-5s %b%-25s %b%-35s %b%-6s %b%s%b\n" \
        "State" \
        "$blue" "Name" \
        "$yellow" "Version" \
        "$NC" "Arch." \
        "$cyan" "Description" \
        "$NC"
    printf "%-5s %b%-25s %b%-35s %b%-6s %b%s%b\n" \
        "-----" \
        "$blue" "----" \
        "$yellow" "-------" \
        "$NC" "-----" \
        "$cyan" "-----------" \
        "$NC"
    while read state name ver arch desc; do
        printf "%-5s %b%-25s %b%-35s %b%-6s %b%s%b\n" \
            "$state" \
            "$blue" "$name" \
            "$yellow" "$ver" \
            "$NC" "$arch" \
            "$cyan" "$desc" \
            "$NC"
    done < <(tail -n +6 <<<"$output")
}

function print_pkg_info {
    # Use `dpkg -s` to show package info.
    local pkgname=$1
    if ! output="$(dpkg -s "$pkgname" 2>/dev/null)"; then
        if ! output="$(apt-cache show "$pkgname" 2>/dev/null)"; then
            echo_err "Package can't be found: $pkgname"
            return 1
        fi
    fi
    while read lbl val; do
        if [[ "$lbl" =~ :$ ]]; then
            # Label:value pair.
            # Set value color depending on the label.
            valcolor=$cyan
            case "$lbl" in
                Description* )
                valcolor=$NC
                ;;
                Homepage* )
                valcolor=$lightblue
                ;;
                Package* )
                valcolor=$green
                printf "\n"
                ;;
                Version* )
                valcolor=$yellow
                ;;
            esac
            # Trim the colon from the label, and indent.
            lbl="$(printf "%*s" "$justlevel" "${lbl:0:-1}")"
            printf "%b%s%b: %b%s%b\n" \
                "$blue" "$lbl" "$NC" \
                "$valcolor" "$val" "$NC"
        else
            # Content ran long.
            printf "%s%b%s %s%b\n" \
                "$indent" "$valcolor" "$lbl" \
                "$val" "$NC"
        fi
    done <<<"$output";
    return 0
}

function print_usage {
    # Show usage reason if first arg is available.
    [[ -n "$1" ]] && echo_err "\n$1\n"

    echo "$appname v. $appversion

    This is just an alias for \`dpkg (-l|-s) PACKAGE...\`, with colors.

    Usage:
        $appscript -h | -v
        $appscript [-l] PACKAGE...

    Options:
        PACKAGE       : Package name to look up.
                        If the package name contains a * character then -l
                        is implied.
        -h,--help     : Show this message.
        -l,--list     : List packages that match a pattern.
                        This is the same as \`dpkg -l\`.
        -v,--version  : Show $appname version and exit.
    "
}

(( $# > 0 )) || fail_usage "No arguments!"

declare -a packages
do_list=0
star_pat='\*'

for arg; do
    case "$arg" in
        "-h"|"--help" )
            print_usage ""
            exit 0
            ;;
        "-l"|"--list" )
            do_list=1
            ;;
        "-v"|"--version" )
            echo -e "$appname v. $appversion\n"
            exit 0
            ;;
        -*)
            fail_usage "Unknown flag argument: $arg"
            ;;
        *)
            packages+=("$arg")
            # Star was used, automatically use -l.

            [[ "$arg" =~ $star_pat ]] && do_list=1
    esac
done

((${#packages[@]})) || fail_usage "No package names given!"

let errs=0
justlevel=20
# Dynamically make some spaces for indenting, +2 for ': '.
indent="$(printf "%*s" "$((justlevel +2))" " ")"
if ((do_list)); then
    list_pkgs "${packages[@]}" || let errs+=1
else
    # Running for each package, for better error messaging/tracking.
    for pkgname in "${packages[@]}"; do
        print_pkg_info "$pkgname" || let errs+=1
    done
fi
exit $errs
