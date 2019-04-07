#!/usr/bin/env zsh
#compdef apttool

_message_next_arg()
{
    argcount=0
    for word in "${words[@][2,-1]}"
    do
        if [[ $word != -* ]] ; then
            ((argcount++))
        fi
    done
    if [[ $argcount -le ${#myargs[@]} ]] ; then
        _message -r $myargs[$argcount]
        if [[ $myargs[$argcount] =~ ".*file.*" || $myargs[$argcount] =~ ".*path.*" ]] ; then
            _files
        fi
    fi
}

_apttool ()
{
    local context state state_descr line
    typeset -A opt_args

    if [[ $words[$CURRENT] == -* ]] ; then
        _arguments -C \
        ':command:->command' \
		'(-?)-?' \
		'(--examples)--examples' \
		'(-h)-h' \
		'(--help)--help' \
		'(-v)-v' \
		'(--version)--version' \
		'(-c=-)-c=-' \
		'(--containsfile=-)--containsfile=-' \
		'(-C)-C' \
		'(--nocolor)--nocolor' \
		'(-n)-n' \
		'(--names)--names' \
		'(-q)-q' \
		'(--quiet)--quiet' \
		'(-i)-i' \
		'(--install)--install' \
		'(-d)-d' \
		'(--delete)--delete' \
		'(-p)-p' \
		'(--purge)--purge' \
		'(-C)-C' \
		'(--nocolor)--nocolor' \
		'(-q)-q' \
		'(--quiet)--quiet' \
		'(-e)-e' \
		'(--executables)--executables' \
		'(-f)-f' \
		'(--files)--files' \
		'(-S)-S' \
		'(--suggests)--suggests' \
		'(-C)-C' \
		'(--nocolor)--nocolor' \
		'(-q)-q' \
		'(--quiet)--quiet' \
		'(-s)-s' \
		'(--short)--short' \
		'(-P)-P' \
		'(--dependencies)--dependencies' \
		'(-R)-R' \
		'(--reversedeps)--reversedeps' \
		'(-C)-C' \
		'(--nocolor)--nocolor' \
		'(-I)-I' \
		'(--INSTALLED)--INSTALLED' \
		'(-N)-N' \
		'(--NOTINSTALLED)--NOTINSTALLED' \
		'(-q)-q' \
		'(--quiet)--quiet' \
		'(-s)-s' \
		'(--short)--short' \
		'(-H)-H' \
		'(--history)--history' \
		'(-C)-C' \
		'(--nocolor)--nocolor' \
		'(-q)-q' \
		'(--quiet)--quiet' \
		'(-l)-l' \
		'(--locate)--locate' \
		'(-L)-L' \
		'(--LOCATE)--LOCATE' \
		'(-C)-C' \
		'(--nocolor)--nocolor' \
		'(-q)-q' \
		'(--quiet)--quiet' \
		'(-s)-s' \
		'(--short)--short' \
		'(-u)-u' \
		'(--update)--update' \
		'(-C)-C' \
		'(--nocolor)--nocolor' \
		'(-q)-q' \
		'(--quiet)--quiet' \
		'(-V)-V' \
		'(--VERSION)--VERSION' \
		'(-C)-C' \
		'(--nocolor)--nocolor' \
		'(-a)-a' \
		'(--all)--all' \
		'(-q)-q' \
		'(--quiet)--quiet' \
		'(-s)-s' \
		'(--short)--short' \
		'(-a)-a' \
		'(--all)--all' \
		'(-C)-C' \
		'(--nocolor)--nocolor' \
		'(-I)-I' \
		'(--INSTALLED)--INSTALLED' \
		'(-N)-N' \
		'(--NOTINSTALLED)--NOTINSTALLED' \
		'(-D)-D' \
		'(--dev)--dev' \
		'(-n)-n' \
		'(--names)--names' \
		'(-q)-q' \
		'(--quiet)--quiet' \
		'(-r)-r' \
		'(--reverse)--reverse' \
		'(-s)-s' \
		'(--short)--short' \
		'(-x)-x' \
		'(--ignorecase)--ignorecase' \

    else
        myargs=('PACKAGES' 'PACKAGES' 'PACKAGES' 'QUERY' 'COUNT' 'PACKAGES' 'PACKAGES' 'PATTERNS')
        _message_next_arg
    fi
}


_apttool "$@"
