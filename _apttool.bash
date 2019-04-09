#!/bin/bash
# This completion script is very basic. There is nothing "smart" about it.
# In the future, I may make it a little smarter. -Cj
# To install this completion file:
#   ln -s "$PWD/_apttool.bash" /etc/bash_completion.d/apttool
# Then source it to start using it immediately:
#   source _apttool.bash

_apttool()
{
    local cur
    # Get current word for completion.
    cur="${COMP_WORDS[COMP_CWORD]}"

    if ((COMP_CWORD)); then
        if [[ "$cur" == -* ]]; then
            COMPREPLY=( $( compgen -fW '-? --examples -h --help -v --version -c= --containsfile= -C --nocolor -n --names -q --quiet -i --install -d --delete -p --purge -C --nocolor -q --quiet -e --executables -f --files -S --suggests -C --nocolor -q --quiet -s --short -P --dependencies -R --reversedeps -C --nocolor -I --INSTALLED -N --NOTINSTALLED -q --quiet -s --short -H --history -C --nocolor -q --quiet -l --locate -L --LOCATE -C --nocolor -q --quiet -s --short -u --update -C --nocolor -q --quiet -V --VERSION -C --nocolor -a --all -q --quiet -s --short -a --all -C --nocolor -I --INSTALLED -N --NOTINSTALLED -D --dev -n --names -q --quiet -r --reverse -s --short -x --ignorecase ' -- "$cur") )
        else
            COMPREPLY=( $( apt-cache --no-generate pkgnames "$cur" 2> /dev/null ) )
        fi
    fi
}

_apttool_show()
{
    local cur
    # Get current word for completion.
    cur="${COMP_WORDS[COMP_CWORD]}"

    if ((COMP_CWORD)); then
        if [[ "$cur" == -* ]]; then
            COMPREPLY=( $( compgen -fW '-h --help -l --list -v --version ' -- "$cur") )
        else
            COMPREPLY=( $( apt-cache --no-generate pkgnames "$cur" 2> /dev/null ) )
        fi
    fi
}

complete -o bashdefault -o default -o filenames -F _apttool apttool
complete -o bashdefault -o default -o filenames -F _apttool_show apttool-show
