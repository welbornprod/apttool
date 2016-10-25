
_apttool()
{
    local cur
    cur="${COMP_WORDS[COMP_CWORD]}"

    if [ $COMP_CWORD -ge 1 ]; then
        COMPREPLY=( $( compgen -fW '-? --examples -h --help -v --version -c= --containsfile= -C --nocolor -n --names -q --quiet -i --install -d --delete -p --purge -C --nocolor -q --quiet -e --executables -f --files -S --suggests -C --nocolor -q --quiet -s --short -P --dependencies -R --reversedeps -C --nocolor -I --INSTALLED -N --NOTINSTALLED -q --quiet -s --short -H --history -C --nocolor -q --quiet -l --locate -L --LOCATE -C --nocolor -q --quiet -s --short -u --update -C --nocolor -q --quiet -V --VERSION -C --nocolor -a --all -q --quiet -s --short -a --all -C --nocolor -I --INSTALLED -N --NOTINSTALLED -D --dev -n --names -q --quiet -r --reverse -s --short -x --ignorecase ' -- $cur) )
    fi
}

complete -o bashdefault -o default -o filenames -F _apttool apttool