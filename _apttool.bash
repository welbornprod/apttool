#!/bin/bash
# This completion script is very basic. There is nothing "smart" about it.
# It was generated for me by `infi.docopt_completion` (a pip package).
# In the future, I may make it a little smarter. -Cj
_apttool()
{
    local cur
    # Get current word for completion.
    cur="${COMP_WORDS[COMP_CWORD]}"

    if ((COMP_CWORD)); then
        if [[ "$cur" == -* ]]; then
            COMPREPLY=( $( compgen -fW '-? --examples -h --help -v --version -c= --containsfile= -C --nocolor -n --names -q --quiet -i --install -d --delete -p --purge -C --nocolor -q --quiet -e --executables -f --files -S --suggests -C --nocolor -q --quiet -s --short -P --dependencies -R --reversedeps -C --nocolor -I --INSTALLED -N --NOTINSTALLED -q --quiet -s --short -H --history -C --nocolor -q --quiet -l --locate -L --LOCATE -C --nocolor -q --quiet -s --short -u --update -C --nocolor -q --quiet -V --VERSION -C --nocolor -a --all -q --quiet -s --short -a --all -C --nocolor -I --INSTALLED -N --NOTINSTALLED -D --dev -n --names -q --quiet -r --reverse -s --short -x --ignorecase ' -- "$cur") )
        else
            COMPREPLY=(
                $(apt-cache --no-generate pkgnames "$cur")
                $(apt-cache dumpavail | command grep "^Source: $cur" | sort -u | cut -f2 -d" ")
            )
        fi
    fi
}

complete -o bashdefault -o default -o filenames -F _apttool apttool
