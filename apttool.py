#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" apttool.py
    Provides a few apt-related functions based on the 'apt' module.
    -Christopher Welborn
    06-2013
"""

from collections import UserDict, UserList   # PackageVersions/UsageExampleKey
from contextlib import suppress              # easily suppress expected errs.
from datetime import datetime                # log date parsing.
from enum import Enum                        # install states.
import os.path                               # for file/dir
import re                                    # search pattern matching
import stat                                  # checking for executables
import struct                                # for get_terminal_size()
import sys                                   # for args (Scriptname)
from time import time                        # run time calc.
import weakref                               # for IterCache()

try:
    import apt                        # apt tools
    import apt_pkg                    # for IterCache()
    from apt_pkg import gettext as _  # for IterCache()
    import apt.progress.text          # apt tools
except ImportError as eximp:
    print(
        '\n'.join((
            '\nMissing important module or modules!\n{}',
            '\nThese must be installed:',
            '      apt: ..uses apt.progress.text and others',
            '  apt_pkg: ..uses apt_pkg.gettext and others.',
            '\nTry doing: pip install <modulename>\n'
        )).format(eximp),
        file=sys.stderr
    )
    sys.exit(1)


try:
    from docopt import docopt        # cmdline arg parser
except ImportError as exdoc:
    print(
        '\nDocopt must be installed, try: pip install docopt.\n\n{}'.format(
            exdoc
        ),
        file=sys.stderr
    )
    sys.exit(1)

try:
    from colr import (
        auto_disable as colr_auto_disable,
        Colr,
        disable as colr_disable,
        strip_codes
    )
    # Aliased for easier typing and shorter lines.
    C = Colr
except ImportError as excolr:
    print(
        '\nColr must be installed, try: pip install colr\n\n{}'.format(
            excolr
        ),
        file=sys.stderr
    )
    sys.exit(1)

__version__ = '0.7.0'
NAME = 'AptTool'

# Get short script name.
SCRIPT = os.path.split(sys.argv[0])[-1]

USAGESTR = """{name} v. {version}

    Usage:
        {script} -? | -h | -v
        {script} -c file [-C] [-n] [-q]
        {script} (-i | -d | -p) PACKAGES... [-C] [-q]
        {script} (-e | -f | -S) PACKAGES... [-C] [-q] [-s]
        {script} (-P | -R) PACKAGES... [-C] [-I | -N] [-q] [-s]
        {script} -H [QUERY] [COUNT] [-C] [-q]
        {script} (-l | -L) PACKAGES... [-C] [-q] [-s]
        {script} -u [-C] [-q]
        {script} -V PACKAGES... [-C] [-a] [-q] [-s]
        {script} PATTERNS... [-a] [-C] [-I | -N] [-D | -n] [-q] [-r] [-s] [-x]

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
""".format(name=NAME, script=SCRIPT, version=__version__)


# GLOBALS ------------------------------------------------
# placeholder for global cache
cache_main = None
# Something besides None to represent no value (where None has meaning)
NoValue = object()

# Set default terminal width/height (set with get_terminal_size() later).
TERM_WIDTH, TERM_HEIGHT = 80, 120


# MAIN ---------------------------------------------------
def main(argd):
    """ Main entry point for apttool """
    global cache_main, oprogress, fprogress, print_status, print_status_err
    if argd['--nocolor']:
        colr_disable()
    if argd['--quiet']:
        print_status = print_status_err = noop
    # Non-cache related args.
    if argd['--examples']:
        print_example_usage()
        return 0

    # Search (iter_open the cache, not pre-load. for performance)
    if argd['PATTERNS']:
        query = query_build(argd['PATTERNS'], all_patterns=argd['--all'])
        return cmd_search(
            query,
            desc_search=not argd['--names'],
            print_no_desc=argd['--short'],
            installstate=InstallStateFilter.from_argd(argd),
            case_insensitive=argd['--ignorecase'],
            dev_only=argd['--dev'],
            reverse=argd['--reverse'])

    if argd['--history']:
        # Just show apt history and exit.
        cnt = argd['COUNT']
        if cnt:
            try:
                cnt = int(cnt)
                if cnt < 1:
                    raise ValueError('Must be greater than 0!')
            except (TypeError, ValueError) as exint:
                print_err(
                    '\nInvalid number for count: {}\n{}'.format(cnt, exint)
                )
                return 1

        return cmd_history(argd['QUERY'], count=cnt)

    # -----v-- Actions that may benefit from cache pre-loading --v------
    return run_preload_cmd(argd)


# FUNCTIONS -----------------------------------------------
def noop(*args, **kwargs):
    """ Any function can be disabled by replacing it with this no-op function.
        Used for silencing print_status.
    """
    return None


def anyinstance(iterable, klass):
    """ Like isinstance(), but checks an iterable for any occurrences of
        isinstance(item, klass) == True.
    """
    for obj in iterable:
        if isinstance(obj, klass):
            return True
    return False


def cache_get(self, item, default=NoValue):
    """ Supplies Cache.get()
        To monkeypatch apt.Cache to act like a dict with .get()
    """
    try:
        val = self[item]
    except KeyError:
        if default is NoValue:
            raise
        return default
    return val


def cmd_contains_file(name, shortnamesonly=False):
    """ Search all installed files for a filename.
        Print packages containing matches.
        Arguments:
            name            : Name or part of a name to search for

        Keyword Arguments:
            shortnamesonly  : don't include the full path in search,
                              just the short file name.
    """

    try:
        repat = re.compile(name)
    except Exception as ex:
        print_err('\nInvalid search term!: {}\n{}'.format(name, ex))
        return 1

    print_status(
        'Looking for packages by file pattern',
        value=repat.pattern,
    )

    # Setup filename methods (long or short, removes an 'if' from the loop.)
    def getfilenameshort(s):
        return os.path.split(s)[1]
    # Pick filename retrieval function..
    filenamefunc = getfilenameshort if shortnamesonly else str

    # Iterate all packages...
    totalpkgs = 0
    totalfiles = 0

    for pkgname in cache_main.keys():
        pkg = cache_main[pkgname]
        matchingfiles = []
        if not pkg_install_state(pkg):
            continue
        if not hasattr(pkg, 'installed_files'):
            print_err(
                '\n'.join((
                    '\nUnable to retrieve installed files for {},',
                    'apt/apt_pkg may be out of date!'
                )).format(pkgname)
            )
            return 1

        for installedfile in (pkg.installed_files or []):
            shortname = filenamefunc(installedfile)
            rematch = repat.search(shortname)
            if rematch:
                # Save match for report,
                # (report when we're finished with this package.)
                matchingfiles.append(installedfile)

        # Report any matches.
        if matchingfiles:
            totalpkgs += 1
            totalfiles += len(matchingfiles)
            print(pkg_format(pkg, no_desc=True, no_marker=True))
            print('    {}'.format('\n    '.join(matchingfiles)))

    pluralfiles = 'file' if totalfiles == 1 else 'files'
    pluralpkgs = 'package' if totalpkgs == 1 else 'packages'
    print_status(
        '\nFound',
        C(totalfiles, fore='blue', style='bright'),
        pluralfiles,
        'in',
        C(totalpkgs, fore='blue', style='bright'),
        pluralpkgs,
        '.'
    )
    return 0


def cmd_dependencies(pkgname, installstate=None, short=False):
    """ Print all dependencies for a package.
        Optionally, filter by installed or uninstalled.
        Arguments:
            pkgname       : (str) Package name to check dependencies for.
            installstate  : InstallStateFilter, to filter dependency list.
                            Default: InstallStateFilter.every
            short         : Use shorter output.
    """
    status = noop if short else print_status
    installstate = installstate or InstallStateFilter.every

    package = cache_main.get(pkgname, None)
    if package is None:
        print_err('\nCan\'t find a package by that name: {}'.format(pkgname))
        return 1

    is_match = (
        lambda dep:
            pkg_install_state(dep.name, expected=installstate))
    total = 0
    for pkgver in package.versions:
        status(
            '\n{} dependencies for {} v. {}'.format(
                str(installstate).title(),
                package.name,
                pkgver.version))
        for deplst in pkgver.dependencies:
            for dep in filter(is_match, deplst):
                deppkg, ver, rel = dependency_info(dep, default=dep.name)
                print(
                    pkg_format(
                        deppkg,
                        no_ver=short,
                        no_desc=short,
                        use_version=ver,
                        use_relation=rel
                    )
                )
                total += 1

    status('\nTotal ({}): {}'.format(installstate, total))
    return 0 if total > 0 else 1


def cmd_history(filtertext=None, count=None):
    """ Search dpkg log for lines containing text, print the formatted lines.
        If filtertext is None, all lines are formatted and printed.
    """
    repat = None
    if filtertext is not None:
        try:
            repat = re.compile(filtertext)
        except re.error as exre:
            print_err('Invalid filter text: {}\n{}'.format(filtertext, exre))
            return False

    if count:
        def cnt_exceeded(i):
            return i >= count
    else:
        def cnt_exceeded(i):
            # Count is never exceeded
            return False

    total = 0
    try:
        for historyline in iter_history():
            if historyline.matches(repat):
                total += 1
                print(str(historyline))
            if cnt_exceeded(total):
                break
        entryplural = 'entry' if total == 1 else 'entries'
        print_status('\nFound {} {}.'.format(total, entryplural))

    except (EnvironmentError, FileNotFoundError, re.error) as excancel:
        print_err('\nUnable to retrieve history:\n    {}'.format(excancel))
        return False
    except Exception as exgeneral:
        print_err('\nUnexpected error: {}'.format(exgeneral))
        return False

    return True


def cmd_install(pkgname, doupdate=False):
    """ Install a package. """
    print_status('\nLooking for \'{}\'...'.format(pkgname))
    if doupdate:
        updateret = update()
        if updateret:
            print_err('\nCan\'t update cache!')

    if pkgname in cache_main.keys():
        package = cache_main[pkgname]
        if pkg_install_state(package):
            print_err(
                '\nThis package is already installed: {}'.format(package.name)
            )
            return 1

        print_status('Installing package: {}'.format(package.name))
        # Mark for install.
        if not hasattr(package, 'mark_install'):
            print_err(
                '\napt_pkg doesn\'t have \'mark_install\' attribute, '
                'apt/apt_pkg module may be out of date.\n'
                'Stopping.')
            return 1
        cache_main[pkgname].mark_install()
        # Install the package
        try:
            cache_main.commit(
                fetch_progress=SimpleFetchProgress(),
                install_progress=SimpleInstallProgress(
                    pkgname=pkgname))
        except apt.cache.LockFailedException as exlock:
            print_err(
                '\n'.join((
                    '\nCan\'t install package!',
                    'Make sure you have proper permissions. (are you root?)',
                    '\nError Message:\n{}'
                )).format(exlock))
            return 1
        except SystemError as exsys:
            # dpkg is already being used by something else.
            print_err(
                '\n'.join((
                    '\nCan\'t install package!',
                    'Make sure all other package managers are closed.',
                    '\nError Message:\n{}'
                )).format(exsys))
            return 1

    else:
        print_err('\nCan\'t find a package by that name: {}'.format(pkgname))
        return 1
    return 0


def cmd_installed_files(pkgname, execs_only=False, short=False):
    """ Print a list of installed files for a package. """
    status = noop if short else print_status

    status('\nGetting installed {} for \'{}\'\n'.format(
        'executables' if execs_only else 'files',
        pkgname))
    try:
        package = cache_main[pkgname]
    except KeyError:
        print_missing_pkg(pkgname)
        return 1

    if not pkg_install_state(package):
        print_err(''.join((
            '\nThis package is not installed: {}',
            '\nCan\'t get installed files for ',
            'uninstalled packages.')).format(package.name))
        return 1

    if not hasattr(package, 'installed_files'):
        print_err(''.join((
            '\nUnable to get installed files for {}',
            ', apt/apt_pkg module may be out of date.'
        )).format(package.name))
        return 1

    files = sorted(fname for fname in package.installed_files if fname)
    if execs_only:
        # Show executables only (/bin directory files.)
        # Returns true for a path if it looks like an executable.
        # is_exec = lambda s: ('/bin' in s) and (not s.endswith('/bin'))
        files = [fname for fname in files if is_executable(fname)]
        label = 'executable' if len(files) == 1 else 'executables'
    else:
        # Show installed files.
        label = 'installed file' if len(files) == 1 else 'installed files'

    if files:
        status('Found {} {} for {}:'.format(len(files), label, package.name))
        if short:
            print('\n'.join(sorted(files)))
        else:
            print('    {}\n'.format('\n    '.join(sorted(files))))
        return 0

    # No files found (possibly after trimming to only executables)
    print_status_err('Found 0 {} for: {}'.format(label, package.name))
    return 1


def cmd_locate(pkgnames, only_existing=False, short=False):
    """ Locate one or more packages.
        Arguments:
            pkgnames       : A list of package names, or file names to read
                             from. If '-' is encountered in the list then
                             stdin is used. stdin can only be used once.
            only_existing  : Only show existing packages.
            short          : When truthy, do not print the install state.
    """
    existing = 0
    checked = 0
    for pname in pkgnames:
        pname = pname.lower().strip()
        # Use Package for existing, packagename for missing.
        pkg = cache_main.get(pname, pname)
        if pkg != pname:
            existing += 1
        print(pkg_format(
            pkg,
            color_missing=True,
            no_marker=short,
            no_desc=short
        ))

        checked += 1

    plural = 'package' if existing == 1 else 'packages'
    print_status('\nFound {} of {} {}.'.format(existing, checked, plural))
    return 0 if (checked > 0) and (existing == checked) else 1


def cmd_remove(pkgname, purge=False):
    """ Remove or Purge a package by name """

    print_status('\nLooking for \'{}\'...'.format(pkgname))
    if purge:
        opaction = 'purge'
        opstatus = 'Purging'
    else:
        opaction = 'remove'
        opstatus = 'Removing'

    try:
        package = cache_main[pkgname]
    except KeyError:
        print_missing_pkg(pkgname)
        return 1

    if not pkg_install_state(package):
        print_err('\nThis package is not installed: {}'.format(package.name))
        return 1

    print_status('Removing package: {}'.format(package.name))
    # Mark for delete.
    if not hasattr(package, 'mark_delete'):
        print_err(
            '\n'.join((
                '\napt_pkg doesn\'t have \'mark_delete\' attribute,',
                'apt/apt_pkg module may be out of date.',
                '\nStopping.'
            ))
        )
        return 1

    package.mark_delete(purge=purge)
    # Remove the package
    try:
        cache_main.commit(
            fetch_progress=SimpleFetchProgress(),
            install_progress=SimpleInstallProgress(
                pkgname=pkgname,
                msg=opstatus))
        return 0
    except apt.cache.LockFailedException as exlock:
        print_err(
            '\n'.join((
                '\nCan\'t {} package, ',
                'Make sure you have proper permissions. (are you root?)',
                '\nError Message:\n{}',
            )).format(opaction, exlock)
        )
        return 1
    except SystemError as exsys:
        # dpkg is already being used by something else.
        print_err(
            '\n'.join((
                'Can\'t {} package, ',
                'Make sure all other package managers are closed.',
                '\nError Message:\n{}',
            )).format(opaction, exsys)
        )
        return 1


def cmd_reverse_dependencies(pkgname, installstate=None, short=False):
    """ Print all reverse dependencies for a package.
        Optionally, filter by installed or uninstalled.
        Arguments:
            pkgname       : (str) Package name to check dependencies for.
            installstate  : InstallStateFilter, to filter dependency list.
                            Default: InstallStateFilter.every
            short         : Use shorter output.
    """
    status = noop if short else print_status
    installstate = installstate or InstallStateFilter.every
    try:
        package = cache_main[pkgname]
    except KeyError:
        print_missing_pkg(pkgname)
        return 1

    status('\nSearching for {} dependents on {}...'.format(
        installstate,
        package.name))
    total = 0
    for pkg in cache_main:
        if not pkg_install_state(pkg, expected=installstate):
            continue
        for pkgver in pkg.versions:
            for deplst in pkgver.dependencies:
                for dep in filter(lambda d: d.name == package.name, deplst):
                    print(pkg_format(pkg, no_ver=short, no_desc=short))
                    total += 1

    status('\nTotal ({}): {}'.format(installstate, total))
    return 0 if total > 0 else 1


def cmd_search(query, **kwargs):
    """ print results while searching the cache...
        Arguments:
            query             : Seach term for package name/desc.

        Keyword Arguments:
            print_no_desc     : If True, don't print descriptions of packages.
                                Default: False
            print_no_ver      : If True, don't print the latest versions.
                                Default: False
            installstate      : InstallStateFilter to filter packages.
                                Default: InstallStateFilter.every

            Other keyword arguments are forwarded to search_itercache().
    """

    print_no_desc = kwargs.get('print_no_desc', False)
    print_no_ver = kwargs.get('pront_no_ver', False)
    dev_only = kwargs.get('dev_only', False)
    if hasattr(query, 'pattern'):
        # Extract pattern from compiled regex for modification.
        query = query.pattern

    if dev_only:
        # This little feature would be wrecked by adding '$' to the pattern.
        if query.endswith('$'):
            query = query[:-1]
            queryend = '$'
        else:
            queryend = ''
        # Adding 'dev' to the query to search for development packages.
        query = '{}(.+)dev{}'.format(query, queryend)

    # Initialize cache without doing an .open() (do iter_open() instead)
    print_status('Initializing Cache...')
    cache = IterCache(do_open=False)
    cache._pre_iter_open()
    print_status(
        'Searching ~{} packages for {}'.format(cache.rough_size, query)
    )

    # Update arguments for use with search_itercache().
    kwargs.update({
        'cache': cache,
        'progress': None,
    })

    result_cnt = 0

    for result in search_itercache(query, **kwargs):
        print('\n{}'.format(
            pkg_format(
                result,
                no_desc=print_no_desc,
                no_ver=print_no_ver
            )
        ))
        result_cnt += 1

    print_status('\nFinished searching, found {} {}.'.format(
        str(result_cnt),
        'result' if result_cnt == 1 else 'results'
    ))
    return 0


def cmd_suggests(pkgname, short=False, indent=0):
    """ Print suggested packages for a single Package.
        Return an exit status code.

        Arguments:
            pkgname  : Package name to get suggests for.
            short    : If True, do not print versions/descriptions.
                       Default: False
            indent   : Amount of indent for formatted package lines.
                       Default: 0
    """
    try:
        pkg = cache_main[pkgname]
    except KeyError:
        print_missing_pkg(pkgname)
        return 1

    format_args = {
        'no_desc': short,
        'no_ver': short,
        'indent': indent,
    }

    suggests = get_suggests(pkg)
    suggestlen = sum(len(basedeps) for basedeps in suggests)
    print_status(
        '\nSuggested packages for {} ({}):'.format(pkgname, suggestlen)
    )
    results = 0
    missing = 0

    try:
        for dep in suggests:
            for basedep in dep:
                deppkg = cache_main.get(basedep.name, None)
                if deppkg is None:
                    # pkg_format accepts a str (name) to print missing pkgs.
                    deppkg = basedep.name
                    missing += 1
                results += 1
                print('\n{}'.format(pkg_format(deppkg, **format_args)))
    except KeyboardInterrupt:
        # User cancelled, print the result count anyway.
        print_err('\nUser cancelled.\n')

    if missing > 0:
        # Show a warning for missing packages.
        print_status_err(
            '\n{} suggested {} for {} are not in the cache.'.format(
                missing,
                'package' if missing == 1 else 'packages',
                pkgname
            )
        )

    print_status('\nFound {} suggested {}.'.format(
        results,
        'package' if results == 1 else 'packages'
    ))

    return 0 if (results > 0) else 1


def cmd_update(load_cache=False):
    """ update the cache,
        init or re-initialize the cache if load_cache is True
    """
    global cache_main
    if load_cache:
        cache_main = apt.Cache()

    try:
        cache_main.update(SimpleFetchProgress(msg='Updating...'))
        cache_main.open(progress=SimpleOpProgress(msg='Opening cache...'))
        print_status('Loaded ' + str(len(cache_main.keys())) + ' packages.')
    except KeyboardInterrupt:
        print_err('\nUser cancelled.\n')
    except apt.cache.FetchFailedException as exfail:
        print_err('\nFailed to complete download.\n{}'.format(exfail))
    except Exception as ex:
        print_err('\nError during update!:\n{0}\n'.format(ex))
    return True


def cmd_version(pkgname, allversions=False, div=False, short=False):
    """ Retrieve and print the current version info for a package.
        Returns 0 for success, 1 for error.
    """
    if (not short) and div:
        print_status(C('{}'.format('-' * TERM_WIDTH)))
    status = noop if short else print_status
    status('\nLooking for \'{}\'...'.format(pkgname))
    try:
        package = cache_main[pkgname]
    except KeyError:
        print_missing_pkg(pkgname)
        return 1

    try:
        versions = PackageVersions(package)
    except (TypeError, ValueError):
        print_err(''.join((
            '\nUnable to retrieve versions for {}, ',
            'apt/apt_pkg may be out of date.')).format(pkgname))
        return 1

    if allversions:
        print(versions.formatted_all(header=not short))
    else:
        print(versions.formatted(header=not short))
    if not short:
        print(versions.format_desc())

    return 0


def cmdmap_build(argd):
    """ Return a map of {cmdline_option: function_info}. """
    funcmap = {
        '--containsfile': {
            'func': cmd_contains_file,
            'args': (argd['--containsfile'],),
            'kwargs': {'shortnamesonly': argd['--names']}
        },
        '--dependencies': {
            'func': multi_pkg_func,
            'args': (
                cmd_dependencies,
                argd['PACKAGES']
            ),
            'kwargs': {
                'installstate': InstallStateFilter.from_argd(argd),
                'short': argd['--short']
            }
        },
        '--delete': {  # --purge
            'func': multi_pkg_func,
            'args': (
                cmd_remove,
                argd['PACKAGES']
            ),
            'kwargs': {'purge': bool(argd['--purge'])}
        },
        '--executables': {
            'func': multi_pkg_func,
            'args': (
                cmd_installed_files,
                argd['PACKAGES'],
            ),
            'kwargs': {
                'execs_only': True,
                'short': argd['--short'] or argd['--quiet']
            }
        },
        '--files': {
            'func': multi_pkg_func,
            'args': (
                cmd_installed_files,
                argd['PACKAGES'],
            ),
            'kwargs': {
                'short': argd['--short'] or argd['--quiet']
            }
        },
        '--install': {
            'func': multi_pkg_func,
            'args': (
                cmd_install,
                argd['PACKAGES'],
            )
        },
        '--locate': {  # --LOCATE
            'func': cmd_locate,
            'args': (
                parse_packages_arg(argd['PACKAGES']),
            ),
            'kwargs': {
                'only_existing': argd['--LOCATE'],
                'short': argd['--short']
            }
        },
        '--reversedeps': {
            'func': multi_pkg_func,
            'args': (
                cmd_reverse_dependencies,
                argd['PACKAGES']
            ),
            'kwargs': {
                'installstate': InstallStateFilter.from_argd(argd),
                'short': argd['--short']
            }
        },
        '--suggests': {
            'func': multi_pkg_func,
            'args': (
                cmd_suggests,
                argd['PACKAGES'],
            ),
            'kwargs': {'short': argd['--short']}
        },
        '--update': {'func': cmd_update},
        '--VERSION': {
            'func': multi_pkg_func,
            'args': (
                cmd_version,
                argd['PACKAGES'],
            ),
            'kwargs': {
                'allversions': argd['--all'],
                'div': True,
                'short': argd['--short']}
        },
    }
    # Shared functions with different arguments:
    funcmap['--purge'] = funcmap['--delete']
    funcmap['--LOCATE'] = funcmap['--locate']
    return funcmap


def dependency_info(dep, default=None):
    """ Get the actual Package, version, and relation for a Dependency.
        Returns a tuple of (Package/`default`, dep.version, dep.relation).
        Arguments:
            dep      : Dependency object to get info for.
            default  : Returned as `deppkg` when an actual Package can't be
                       found.
    """
    deppkg = cache_main.get(strip_arch(dep.name), default)
    deprel = getattr(dep, 'relation', None) or ''
    depver = getattr(dep, 'version', None) or ''
    return deppkg, depver, deprel


def flatten_args(args, allow_dupes=False):
    """ Flatten any comma separated args, mixed with regular args, into a
        single tuple.
        Example:
            flatten_arg_list(['test', 'this,thing', 'out, right, here'])
            # ['test', 'this', 'thing', 'out', 'right', 'here']
    """
    if allow_dupes:
        flat = list()
        for arg in args:
            flat.extend(s.strip() for s in arg.split(','))
    else:
        flat = set()
        for arg in args:
            flat.update(s.strip() for s in arg.split(','))
    return tuple(flat)


def format_block(
        text,
        maxwidth=60, chars=False, newlines=False,
        prepend=None, strip_first=False, lstrip=False):
    """ Format a long string into a block of newline seperated text.
        Arguments:
            See iter_format_block().
    """
    # Basic usage of iter_format_block(), for convenience.
    return '\n'.join(
        iter_format_block(
            text,
            prepend=prepend,
            strip_first=strip_first,
            maxwidth=maxwidth,
            chars=chars,
            newlines=newlines,
            lstrip=lstrip
        )
    )


def get_latest_ver(pkg):
    """ Return the latest version for a package. """
    ver = get_latest_verobj(pkg)
    return getattr(ver, 'version', 'unknown').strip()


def get_latest_verobj(pkg):
    """ Return the latest Version object for a package. """
    try:
        ver = pkg.versions[0]
    except AttributeError:
        return None

    return ver


def get_pkg_description(pkg):
    """ Retrieves package description using old and new apt API,
        Returns empty string on failure, or no description.
    """

    if hasattr(pkg, 'description'):
        return pkg.description or ''
    if hasattr(pkg, 'installed'):
        installedpkg = pkg.installed
        if installedpkg:
            # Use installed version description
            return installedpkg.description or ''

        # Get first description found in all versions.
        desc = ''
        for ver in pkg.versions:
            if ver.description:
                desc = ver.description
                break
        return desc

    return ''


def get_suggests(pkg):
    """ Return a list of Dependency objects (a package's suggested packages).
    """
    ver = get_latest_verobj(pkg)
    if ver is None:
        return []
    return ver.suggests


def get_terminal_size():
    """ Return terminal (width, height) """
    def ioctl_GWINSZ(fd):
        try:
            import fcntl
            import termios
            cr = struct.unpack('hh',
                               fcntl.ioctl(fd, termios.TIOCGWINSZ, '1234'))
            return cr
        except:
            pass
    cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
    if not cr:
        try:
            fd = os.open(os.ctermid(), os.O_RDONLY)
            cr = ioctl_GWINSZ(fd)
            os.close(fd)
        except:
            pass
    if not cr:
        try:
            cr = (os.environ['LINES'], os.environ['COLUMNS'])
        except:
            return None
    return int(cr[1]), int(cr[0])


def is_executable(filename):
    """ Return True if the file is executable.
        Returns False on errors.
    """

    try:
        st = os.stat(filename)
    except EnvironmentError as ex:
        print_err(
            'Error checking executable stat: {}\n{}'.format(filename, ex))
        return False
    return (
        stat.S_ISREG(st.st_mode) and
        st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


def is_pkg_match(re_pat, pkg, **kwargs):
    """ returns True/False if pkg matches the regex.
        Arguments:
            re_pat           : compiled regex pattern to match with.
            pkg              : Package() to match.

        Keyword Arguments:
            desc_search      : if True, try matching descriptions.
                               Default: True
            reverse          : if True, opposite of matching. return packages
                               that don't match.
                               Default: False
            installstate     : InstallStateFilter to match against.
                               Default: InstallStateFilter.every
    """

    desc_search = kwargs.get('desc_search', True)
    reverse = kwargs.get('reverse', False)
    installstate = (
        kwargs.get('installstate', InstallStateFilter.every) or
        InstallStateFilter.every)

    # Trim filtered packages.
    if not pkg_install_state(pkg, expected=installstate):
        return False

    def matchfunc(targetstr, reverse=False):
        rematch = re_pat.search(targetstr)
        return (rematch is None) if reverse else (rematch is not None)

    # Try matching the name. (reverse handled also.)
    if matchfunc(pkg.name, reverse):
        return True
    if not desc_search:
        return False

    pkgdesc = get_pkg_description(pkg)

    # Try matching description.
    if pkgdesc and matchfunc(pkgdesc, reverse):
        return True
    # No match/no desc to search
    return False


def iter_block(text, maxwidth=60, chars=False, newlines=False, lstrip=False):
    """ Iterator that turns a long string into lines no greater than
        'maxwidth' in length.
        It can wrap on spaces or characters. It only does basic blocks.
        For prepending see `iter_format_block()`.

        Arguments:
            text       : String to format.
            maxwidth  : Maximum width for each line.
                         Default: 60
            chars      : Wrap on characters if true, otherwise on spaces.
                         Default: False
            newlines   : Preserve newlines when True.
                         Default: False
            lstrip     : Whether to remove leading spaces from each line.
                         Default: False
    """
    if lstrip:
        # Remove leading spaces from each line.
        fmtline = str.lstrip
    else:
        # Yield the line as-is.
        fmtline = str
    if chars and (not newlines):
        # Simple block by chars, newlines are treated as a space.
        text = ' '.join(text.splitlines())
        for l in (
                fmtline(text[i:i + maxwidth])
                for i in range(0, len(text), maxwidth)):
            yield l
    elif newlines:
        # Preserve newlines
        for line in text.splitlines():
            for l in iter_block(
                    line,
                    maxwidth=maxwidth,
                    chars=chars,
                    lstrip=lstrip):
                yield l
    else:
        # Wrap on spaces (ignores newlines)..
        curline = ''
        for word in text.split():
            possibleline = ' '.join((curline, word)) if curline else word

            if len(possibleline) > maxwidth:
                # This word would exceed the limit, start a new line with it.
                yield fmtline(curline)
                curline = word
            else:
                curline = possibleline
        if curline:
            yield fmtline(curline)


def iter_file(filename, skip_comments=True, split_spaces=False):
    """ Iterate over lines in a file, skipping blank lines.
        If 'skip_comments' is truthy then lines starting with #
        are also skipped.
        If filename is None, then stdin is used.
        If split_spaces is True, words will be yielded instead of lines.
    """
    if skip_comments:
        def is_skipped(l):
            (not l) or l.startswith('#')
    else:
        def is_skipped(l):
            return (not l)

    if filename is None:
        for line in sys.stdin.readlines():
            if is_skipped(line.strip()):
                continue
            if split_spaces:
                for l in line.rstrip().split():
                    yield l
            else:
                yield line.rstrip()
    else:
        with open(filename, 'r') as f:
            for line in f:
                if is_skipped(line.strip()):
                    continue
                if split_spaces:
                    for l in line.rstrip().split():
                        yield l
                else:
                    yield line.rstrip()


def iter_format_block(
        text,
        maxwidth=60, chars=False, newlines=False,
        prepend=None, strip_first=False, lstrip=False):
    """ Iterate over lines in a formatted block of text.
        This iterator allows you to prepend to each line.
        For basic blocks see iter_block().


        Arguments:
            text         : String to format.

            maxwidth    : Maximum width for each line. The prepend string is
                           not included in this calculation.
                           Default: 60

            chars        : Whether to wrap on characters instead of spaces.
                           Default: False

            newlines     : Whether to preserve newlines in the original str.
                           Default: False

            prepend      : String to prepend before each line.

            strip_first  : Whether to omit the prepend string for the first
                           line.
                           Default: False

                           Example (when using prepend='$'):
                            Without strip_first -> '$this', '$that', '$other'
                               With strip_first -> 'this', '$that', '$other'

            lstrip       : Whether to remove leading spaces from each line.
                           This doesn't include any spaces in `prepend`.
                           Default: False
    """
    iterlines = iter_block(
        text,
        maxwidth=maxwidth,
        chars=chars,
        newlines=newlines,
        lstrip=lstrip)
    if prepend is None:
        for l in iterlines:
            yield l
    else:
        # Prepend text to each line.
        for i, l in enumerate(iterlines):
            if i == 0 and strip_first:
                # Don't prepend the first line if strip_first is used.
                yield l
            else:
                yield '{}{}'.format(prepend, l)


def iter_history():
    """ Read dpkg.log and parse it's contents to yield HistoryLine()s
        with package names, install states, etc.
    """
    logname = '/var/log/dpkg.log'
    if not os.path.exists(logname):
        raise FileNotFoundError('File does not exist: {}'.format(logname))
    try:
        with open(logname, 'r') as f:
            # Going to read these backwards, latest first.
            for line in reversed(f.readlines()):
                historyline = HistoryLine.from_dpkg_line(line)
                if historyline is not None:
                    yield historyline
    except EnvironmentError as exenv:
        errfmt = 'Failed to read history: {}\n{}'
        raise EnvironmentError(errfmt.format(logname, exenv))


def multi_pkg_func(func, pkgnames, *args, **kwargs):
    """ Run an exit-status returning function for multiple package names.
        Return the number of errors as an exit status.
        Arguments:
            func      : Function to run on package names.
            pkgnames  : Iterable of package names to get suggests for.

            *args     : Arguments for the function.
            **kwargs  : Keyword arguments for the function.
    """
    return sum(
        func(pkgname, *args, **kwargs)
        for pkgname in parse_packages_arg(pkgnames)
    )


def parse_packages_arg(names):
    """ Parse the --PACKAGES arg, which accepts package names,
        file names, or '-' for stdin.
        Yields package names as they are read (from arg, from file, or stdin).
    """
    did_stdin = False
    for pname in names:
        if pname.strip() == '-':
            if did_stdin:
                print_err('Already read from stdin.')
                continue
            if sys.stdin.isatty() and sys.stdout.isatty():
                print_status('\nReading package names from stdin...\n')
            did_stdin = True
            for word in sys.stdin.read().split():
                yield word.strip()
        elif os.path.isfile(pname):
            try:
                with open(pname, 'r') as f:
                    for line in f:
                        for word in line.split():
                            yield word.strip()
            except EnvironmentError as ex:
                print_err(
                    '\nError reading from file: {}\n{}'.format(pname, ex)
                )
                continue
        else:
            yield pname


def pkg_format(
        pkg, color_missing=False, indent=0,
        no_desc=False, no_marker=False, no_ver=False,
        use_relation=None, use_version=None):
    """ Formats a single search result, using colors.

        Arguments:
            pkg           : Package object to format.
            color_missing : If True, colorize missing package names
                            (when pkg is a str instead of a Package).
            indent        : Number of spaces to indent the final line.
                            Default: 0
            no_desc       : If True, only prints state and name.
                            Default: False
            no_marker     : If True, do not print the install state marker.
            no_ver        : If True, print package version also
                            (even with no_desc).
                            Default: False
            use_relation  : Print this version relation (for dependencies).
                            (=, >=, ~, etc.).
            use_version   : Print this version number instead of grabbing the
                            latest/installed version.
    """
    missing = False
    name_len = 35
    separator = ' : '

    # name formatting
    if isinstance(pkg, str):
        # Just a name was passed in, because the cache didn't contain this
        # known package. ..Happens when printing dependencies (python3-flup?).
        marker = '' if no_marker else C('[?]', fore='red', style='bright')
        pkgname = pkg
        missing = True
    elif pkg_install_state(pkg):
        marker = '' if no_marker else C('[i]', fore='green', style='bright')
        pkgname = pkg.name
    else:
        marker = '' if no_marker else C('[u]')
        pkgname = pkg.name
    pkgname = pkg_format_name(
        pkgname.ljust(name_len),
        missing=missing and color_missing
    )
    if not no_marker:
        pkgname = C(' ').join(
            marker,
            pkgname
        )

    # Get Package Version/Description....
    if missing:
        pkgdesc_full = 'This package cannot be found in the cache.'
        verstr = '(missing)'
        verlen = len(verstr)
        relation = ''
        verfmt = C(verstr, fore='red')
    else:
        pkgdesc_full = get_pkg_description(pkg)
        verstr = use_version if use_version else get_latest_ver(pkg)
        relation = use_relation or ''
        if relation:
            verfmt = '{} {}'.format(
                C(relation, fore='green'),
                C(verstr, fore='blue')
            )
        else:
            verfmt = C(verstr, fore='blue')

        verlen = len(strip_codes(verfmt))

    # No description needed/available RETURN only the name.
    if no_desc:
        if no_ver:
            return pkgname
        # Give an extra 50 chars for the pkgname since no desc is needed.
        return '{:<50} {}'.format(pkgname, verfmt)

    # No description available?
    if not pkgdesc_full:
        return pkgname

    # Padlen is how far extended descriptions should be padded.
    padlen = indent + name_len + len(strip_codes(marker)) + len(separator)
    # The +1 is for a space between the marker and the name.
    if not no_marker:
        padlen += 1

    descmax = TERM_WIDTH - padlen
    padding = ' ' * padlen
    if len(pkgdesc_full) <= descmax:
        # already short description
        pkgdesc = pkgdesc_full
        if not no_ver:
            # Add a second line for the version.
            pkgdesc = '\n'.join((
                pkgdesc_full,
                '    {}'.format(verfmt)
            ))
    else:
        pkgdesc = format_block(
            pkgdesc_full,
            maxwidth=descmax,
            strip_first=True,
            prepend=padding
        )
        if not no_ver:
            pkglines = pkgdesc.splitlines()
            pkgver = '    {}'.format(verfmt)
            if len(pkglines) > 1:
                # Replace part of the second line with the version.
                pkglines[1] = ''.join((
                    pkgver,
                    pkglines[1][verlen + 4:]
                ))
            else:
                # Add a second line for the version.
                pkglines.append(pkgver)

            pkgdesc = '\n'.join(pkglines)

    if len(pkgdesc) > 188:
        pkgdesc = '{}...'.format(pkgdesc[:185].rstrip())

    # Return the final line, indent if needed.
    return ''.join((
        ' ' * indent,
        str(C(separator).join(pkgname, pkgdesc))
    ))


def pkg_format_name(s, missing=False):
    """ Colorize a package name.
        Arguments:
            s        : A package name to format.
            missing  : Whether this is a missing package
                       (not found in the cache).
                       It will be colored different.
    """
    return str(C(s, fore=('red' if missing else 'magenta'), style='bright'))


def pkg_install_state(pkg, expected=None):
    """ Returns True/False whether this package is installed.
        Uses old and new apt API methods.

        If expected is passed (a InstallStateFilter enum),
        returns True if the InstallStateFilter matches the packages install
        state, or if InstallState.every is used.
    """
    expected = expected or InstallStateFilter.installed
    # This function is useless with InstallStateFilter.every.
    if expected == InstallStateFilter.every:
        return True

    if hasattr(pkg, 'isInstalled'):
        actualstate = pkg.isInstalled()
    elif hasattr(pkg, 'installed'):
        actualstate = (pkg.installed is not None)
    else:
        if isinstance(pkg, str):
            # Convenience, package name was passed instead of a package.
            pkg = cache_main.get(pkg, None)
            if pkg is not None:
                return pkg_install_state(pkg, expected=expected)

        # API fell through?
        # (it has happened before, hince the need for the 2 ifs above)
        actualstate = False

    if expected == InstallStateFilter.installed:
        return actualstate
    if expected == InstallStateFilter.uninstalled:
        return not actualstate
    # Should not reach this.
    print_err(
        '\nUnreachable code in pkg_install_state({!r}, expected={})!'
        .format(pkg, expected))
    return True


def print_err(*args, **kwargs):
    """ Like print(), except `file` is set to sys.stderr by default. """
    kwargs['file'] = kwargs.get('file', sys.stderr)
    return print(
        C(kwargs.get('sep', ' ').join(args), fore='red'),
        **kwargs
    )


def print_example_usage():
    """ Print specific usage examples when -? is used. """
    print("""{name} v. {ver}

Example Usage:

    Shows installed packages with 'foo' in the name or desc.
        {script} foo -I

    Show non-installed packages with 'bar' in the name only.
        {script} bar -n -N

    Show installed files for the 'python' package.
        {script} -f python

    Show installed executables for the 'python' package.
        {script} -e python

    Show suggested packages for the 'python' package.
        {script} -S python

    Determine whether a full package name exists in the cache.
    This is quicker than a full search.
        {script} -l pythonfoo

    Search dpkg history for latest installs/half-installs.
        {script} -H install

    Show packages containing files with 'foo' in the path.
        {script} -c foo

    Show full help/options.
        {script} -h

Marker Legend:
    [i] = package is installed
    [u] = package is not installed
    [?] = package name was not found in the cache

Notes:
    If no options are given, the default behaviour is to search for
    packages by name and description, then print results.
    """.format(name=NAME, ver=__version__, script=SCRIPT))


def print_missing_pkg(pkgname):
    """ Print an error msg (for when a bad package name is given). """
    print_err('\nCan\'t find a package by that name: {}'.format(pkgname))


def print_runtime(seconds):
    """ Print a duration (timedelta.total_seconds()) to the console
        (for end-of-run time).
    """
    print_status(C('{:.3f}s'.format(seconds), fore='cyan'), file=sys.stderr)


def print_status(*args, **kwargs):
    """ Print a non-critical status message that can be silenced with --quiet.
    """
    # Use stdout by default, explicitly setting the 'file' kwarg for print.
    kwargs['file'] = kwargs.get('file', sys.stdout)

    # Add color to non-colorized messages, use RED for errors.
    pargs = list(args)
    msgcolor = 'red' if kwargs['file'] is sys.stderr else 'lightblue'
    for i, arg in enumerate(pargs[:]):
        # Keep any previously colorized args (Colr instances).
        if not isinstance(arg, C):
            pargs[i] = C(arg, fore=msgcolor)

    # Optional value, for printing label: value style messages.
    with suppress(KeyError):
        value = kwargs.pop('value')
        pargs[-1] = C().join(
            pargs[-1],
            ': ',
            C(value, fore='cyan'),
        )

    print(*pargs, **kwargs)


def print_status_err(*args, **kwargs):
    """ Print a non-critical error message that can be silenced with --quiet.
    """
    if kwargs.get('file', None) is None:
        kwargs['file'] = sys.stderr
    print_status(*args, **kwargs)


def query_build(patterns, all_patterns=False):
    """ Join query pattern arguments into a single regex pattern.
        Arguments:
            patterns     : List of regex/text patterns from the user.
            all_patterns : Join with (.+)? instead of |.
    """
    parsed = []
    for pat in patterns:
        parenscnt = pat.count('(')
        if parenscnt and (parenscnt == pat.count(')')):
            # Has parentheses.
            parsed.append(pat)
        elif not parenscnt:
            # Add parentheses.
            parsed.append('({})'.format(pat))
        else:
            # Mismatched parens!
            raise BadSearchQuery(pat, 'Unbalanced parentheses.')

    return ('(.+)?' if all_patterns else '|').join(parsed)


def run_preload_cmd(argd):
    """ Handle command-line options that may benefit from preloading the
        cache.
    """
    global cache_main

    status = noop if argd['--short'] else print_status
    # Initialize
    status('Loading APT Cache...')
    cache_main = apt.Cache()
    if not cache_main:
        print_err('Failed to load apt cache!')
        return 1

    # Cache was loaded properly.
    status('Loaded {} packages.'.format(len(cache_main)))
    funcmap = cmdmap_build(argd)
    for opt in funcmap:
        if argd[opt]:
            # Run the command's function with previously defined args.
            return funcmap[opt]['func'](
                *funcmap[opt].get('args', []),
                **funcmap[opt].get('kwargs', {})
            )


def search_itercache(regex, **kwargs):
    """ search while building the cache,
        Arguments:
            regex             :  regex pattern to search for

        Keyword Arguments:
            case_insensitive  : if True, serach pattern is compiled with
                                re.IGNORECASE.
            desc_search       : if True, search through descriptions also,
                                not just names.
                                Default: True
            installstate      : InstallStateFilter to filter packages.
                                Default: InstallStateFilter.every
            reverse           : if True, yield packages that DON'T match.
                                Default: False
            progress          : apt.OpProgress() to report to on iter_open()
                                Default: None
            cache             : initialized (not .open()ed IterCache())
                                if you need to do it yourself.
    """

    # parse args
    desc_search = kwargs.get('desc_search', True)
    progress = kwargs.get('progress', None)
    reverse = kwargs.get('reverse', False)
    case_insensitive = kwargs.get('case_insensitive', False)
    installstate = (
        kwargs.get('installstate', InstallStateFilter.every) or
        InstallStateFilter.every)

    # initialize Cache object without opening,
    # or use existing cache passed in with cache keyword.
    cache = kwargs.get('cache', IterCache(do_open=False))

    if cache is None:
        raise CacheNotLoaded(
            'No apt cache to search, it could not be loaded.'
        )

    try:
        re_pat = re.compile(
            regex,
            re.IGNORECASE if case_insensitive else 0)
    except re.error as ex:
        raise BadSearchQuery(regex, ex)

    is_match = (
        lambda pkg: is_pkg_match(
            re_pat,
            pkg,
            desc_search=desc_search,
            reverse=reverse,
            installstate=installstate)
    )
    # iterate the pkgs as they are loaded.
    for pkg in filter(is_match, cache.iter_open(progress=progress)):
        yield pkg


def strip_arch(pkgname, force=False):
    """ Strip the architecture from a package name (python:i386).
        If `force` is used, the arch is stripped unconditionally.
        Otherwise, it is only stripped when the full pkgname can not be found
        in the cache (python:any).
    """
    if (
            (not force) and
            (cache_main is not None) and
            cache_main.get(pkgname, None) is not None):
        return pkgname
    name, colon, arch = pkgname.rpartition(':')
    if name:
        return name
    # No ':' in the name (arch is the name now).
    return arch


# CLASSES -----------------------------------------------
class InstallStateFilter(Enum):

    """ For querying packages with a certain install state. """
    uninstalled = -1
    every = 0
    installed = 1

    def __str__(self):
        """ Enhanced representation for console. """
        return {
            InstallStateFilter.uninstalled.value: 'uninstalled',
            InstallStateFilter.every.value: 'all',
            InstallStateFilter.installed.value: 'installed'
        }.get(self.value, 'unknown')

    @classmethod
    def from_argd(cls, argd):
        """ Maps a filter arg to an actual InstallStateFilter. """
        if argd['--INSTALLED']:
            return cls.installed
        if argd['--NOTINSTALLED']:
            return cls.uninstalled
        return cls.every


class SimpleOpProgress(apt.progress.text.OpProgress):

    """ Handles progress updates for Operations """

    def __init__(self, msg=None):
        self.msg = msg if msg else 'Doing operation'
        self.current_percent = 0

    def update(self, percent=None):
        if percent:
            self.current_percent = percent

    def done(self, otherarg=None):
        self.current_percent = 0

    def set_msg(self, s):
        self.msg = s


class SimpleFetchProgress(
        apt.progress.text.AcquireProgress, apt.progress.text.OpProgress):
    """ Handles progress updates for Fetches """

    def __init__(self, msg=None):
        self.msg = msg if msg else 'Fetching'
        apt.progress.text.OpProgress.__init__(self)
        apt.progress.text.AcquireProgress.__init__(self)

    def _write(self, msg, newline=True, maximize=False):
        """ Write the message on the terminal, fill remaining space. """
        self._file.write('\r')
        self._file.write(msg)
        msglen = len(strip_codes(msg))
        # Fill remaining stuff with whitespace
        if self._width > msglen:
            self._file.write((self._width - msglen) * ' ')
        elif maximize:  # Needed for OpProgress.
            self._width = max(self._width, msglen)
        if newline:
            self._file.write('\n')
        else:
            self._file.flush()

    def fail(self, item):
        """ Called when an item is failed. """
        apt.progress.base.AcquireProgress.fail(self, item)
        if item.owner.status == item.owner.STAT_DONE:
            self._write(' '.join((
                str(C(_('Ign'), fore='yellow')),
                item.description)
            ))
        else:
            self._write(' '.join((
                str(C(_('Err'), fore='red')),
                item.description)
            ))
            if item.owner.error_text:
                self._write(
                    ' {}'.format(str(C(item.owner.error_text, fore='red')))
                )

    def fetch(self, item):
        """ Called when some of the item's data is fetched. """
        apt.progress.base.AcquireProgress.fetch(self, item)
        # It's complete already (e.g. Hit)
        if item.owner.complete:
            return
        item.owner.id = self._id
        self._id += 1
        line = '{}{} {}'.format(
            C(_('Get:'), fore='lightblue'),
            C(item.owner.id, fore='blue', style='bright'),
            C(item.description, fore='green')
        )

        if item.owner.filesize:
            line += ''.join((' ', self.format_filesize(item.owner.filesize)))

        self._write(line)

    @staticmethod
    def format_filesize(filesize):
        """ Format/colorize a file size. """

        sizeraw = apt_pkg.size_to_str(filesize).split()
        if len(sizeraw) == 1:
            size = sizeraw[0]
            multiplier = ''
        else:
            size, multiplier = sizeraw

        return '[{} {}]'.format(
            C(size, fore='blue'),
            C(''.join((multiplier, 'B')), fore='lightblue')
        )

    def ims_hit(self, item):
        """Called when an item is update (e.g. not modified on the server)."""
        apt.progress.base.AcquireProgress.ims_hit(self, item)
        line = ' '.join((
            str(C(_('Hit'), fore='green')),
            item.description
        ))
        if item.owner.filesize:
            line += ''.join((' ', self.format_filesize(item.owner.filesize)))
        self._write(line)

    def start(self):
        print_status(self.msg)

    def stop(self):
        print_status('\nFinished ' + self.msg)

    def set_msg(self, s):
        self.msg = s


class SimpleInstallProgress(apt.progress.base.InstallProgress):

    """ Handles progress updates for Installs """

    def __init__(self, msg=None, pkgname=None):
        self.msg = msg if msg else 'Installing'
        self.pkgname = pkgname if pkgname else None

        apt.progress.base.InstallProgress.__init__(self)
        # Redirect dpkg's messages to stdout.
        self.writefd = sys.stdout

    def error(self, pkg, errormsg):
        """ Handles errors from dpkg. """

        print_err(
            '\nError while installing: {}\n{}'.format(pkg.name, errormsg)
        )

    def finish_update(self):
        """ Handles end of installation """

        if self.pkgname:
            print_status(
                '\nFinished {}: {}'.format(self.msg.lower(), self.pkgname)
            )


class IterCache(apt.Cache):

    """ Allows searching the package cache while loading. """

    def __init__(self, progress=None, rootdir=None,
                 memonly=False, do_open=True):
        self._cache = None
        self._depcache = None
        self._records = None
        self._list = None
        self._callbacks = {}
        self._callbacks2 = {}
        self._weakref = weakref.WeakValueDictionary()
        self._set = set()
        self._fullnameset = set()
        self._changes_count = -1
        self._sorted_set = None
        if hasattr(self, 'connect2'):
            # Use newer method in case of reference cycles.
            self.connect2('cache_post_open', apt.Cache._inc_changes_count)
            self.connect2('cache_post_change', apt.Cache._inc_changes_count)
        else:
            self.connect('cache_post_open', self._inc_changes_count)
            self.connect('cache_post_change', self._inc_changes_count)

        if memonly:
            # force apt to build its caches in memory
            apt_pkg.config.set('Dir::Cache::pkgcache', '')
        if rootdir:
            if os.path.exists(rootdir + '/etc/apt/apt.conf'):
                apt_pkg.read_config_file(apt_pkg.config,
                                         rootdir + '/etc/apt/apt.conf')
            if os.path.isdir(rootdir + '/etc/apt/apt.conf.d'):
                apt_pkg.read_config_dir(apt_pkg.config,
                                        rootdir + '/etc/apt/apt.conf.d')
            apt_pkg.config.set('Dir', rootdir)
            apt_pkg.config.set('Dir::State::status',
                               rootdir + '/var/lib/dpkg/status')
            # also set dpkg to the rootdir path so that its called for the
            # --print-foreign-architectures call
            apt_pkg.config.set('Dir::bin::dpkg',
                               os.path.join(rootdir, 'usr', 'bin', 'dpkg'))
            # create required dirs/files when run with special rootdir
            # automatically
            self._check_and_create_required_dirs(rootdir)
            # Call InitSystem so the change to Dir::State::Status is actually
            # recognized (LP: #320665)
            apt_pkg.init_system()

        if do_open:
            self.open(progress)

    def _pre_iter_open(self, progress=None):
        """ Things to do before the actual iter_open,
            this allows you to get the rough size before iterating.
        """

        self._run_callbacks('cache_pre_open')

        self._cache = apt_pkg.Cache(progress)
        self._depcache = apt_pkg.DepCache(self._cache)
        self._records = apt_pkg.PackageRecords(self._cache)
        self._list = apt_pkg.SourceList()
        self._list.read_main_list()
        self._set.clear()
        self._fullnameset.clear()
        self._sorted_set = None
        self._weakref.clear()

        self._have_multi_arch = len(apt_pkg.get_architectures()) > 1
        self.rough_size = len(self._cache.packages)

    def iter_open(self, progress=None):
        """ Open the package cache, yielding packages as they are loaded
        """
        if progress is None:
            progress = apt.progress.base.OpProgress()
        self.op_progress = progress

        # Need to load the cache?
        if self._cache is None:
            self._pre_iter_open(progress=progress)

        progress.op = _('Building data structures')
        i = last = 0
        size = len(self._cache.packages)

        for pkg in self._cache.packages:
            if progress is not None and last + 100 < i:
                progress.update(i / float(size) * 100)
                last = i
            # drop stuff with no versions (cruft)
            if pkg.has_versions:
                pkgname = pkg.get_fullname(pretty=True)
                self._set.add(pkgname)
                if self._have_multi_arch:
                    self._fullnameset.add(pkg.get_fullname(pretty=False))
                # Yield this package as it is loaded...
                yield self.__getitem__(pkgname)

            i += 1

        progress.done()
        self._run_callbacks('cache_post_open')

    def iter_open_no_progress(self):
        """ same as iter_open, with no progress-related features.
            possible performance enhancement, not tested.
        """

        if self._cache is None:
            self._pre_iter_open(progress=None)

        for pkg in self._cache.packages:
            if pkg.has_versions:
                pkgname = pkg.get_fullname(pretty=True)
                self._set.add(pkgname)
                if self._have_multi_arch:
                    self._fullnameset.add(pkg.get_fullname(pretty=False))
                yield self.__getitem__(pkgname)


# History package info.
class HistoryLine(object):

    """ Simple class to hold Apt History line info.
        The information comes from a single line in dpkg.log.
        It can be parsed and then accessed through the attributes of this
        class. Such as: myhistoryline.name, myhl.version, myhl.action ..etc.

        Handles parsing and formatting:
            log-line -> object -> string.
        Handles package/state matching based on regex:
            self.matches('^install')
    """

    def __init__(self, **kwargs):
        self.line = None
        self.name = None
        self.packagename = None
        self.version = None
        self.previous_version = None
        self.arch = None
        self.statustype = None
        self.action = None
        self.time = None

        self.__dict__.update(kwargs)

    def __repr__(self):
        """ Same as __str__()... """
        return self.__str__()

    def __str__(self):
        """ Print a formatted version of this history line. """
        if self.action:
            saction = self.action
        else:
            saction = self.statustype

        fmt = '[{time}] {name} ({stattype})'
        fmtargs = {
            'time': str(self.time),
            'stattype': saction,
            'name': self.name.ljust(25),
            'version': self.version
        }
        # Upgrades (and possibly installs) can show the previous version.
        if self.previous_version:
            fmt = ' '.join((fmt, '{fromver} -> {version}'))
            fmtargs['fromver'] = self.previous_version.ljust(30)
        else:
            fmt = ' '.join((fmt, '- {version}'))

        return fmt.format(**fmtargs)

    @classmethod
    def from_dpkg_line(cls, line):
        """ Parses a single line from dpkg.log, and returns a dict with info
            about the line.
        """
        line = line.strip()
        if not line:
            return None

        parts = line.split(' ')
        timestr = ' '.join((parts[0], parts[1]))
        timefmt = '%Y-%m-%d %H:%M:%S'
        try:
            statustime = datetime.strptime(timestr, timefmt)
        except ValueError as extime:
            print_err(
                '\nError parsing history time: {}\n{}'.format(timestr, extime)
            )
            return None

        try:
            statustype = parts[2]
            action = None
            pkgfromver = None
            if statustype == 'status':
                action = parts[3]
                pkgnameraw = parts[4]
                pkgname, pkgarch = pkgnameraw.split(':')
                pkgver = parts[5]
            elif statustype in {'configure', 'trigproc'}:
                pkgnameraw = parts[3]
                pkgname, pkgarch = pkgnameraw.split(':')
                pkgver = parts[4]
            elif statustype in {'install', 'upgrade'}:
                pkgnameraw = parts[3]
                pkgname, pkgarch = pkgnameraw.split(':')
                pkgfromver = parts[4] if (parts[4] != '<none>') else None
                pkgver = parts[5]
            else:
                # For debugging: These are usually 'startup' lines.
                # print_err('Invalid history line: {}'.format(line))
                return None
        except IndexError as exindex:
            print_err(
                '\nError parsing history line: {}\n{}'.format(line, exindex))
            return None

        pkginfo = cls(
            line=line,
            name=pkgname,
            packagename=pkgnameraw,
            version=pkgver,
            previous_version=pkgfromver,
            arch=pkgarch,
            statustype=statustype,
            action=action,
            time=statustime
        )
        return pkginfo

    def matches(self, repat):
        """ See if this history line matches a regex pattern.
            This tests the raw line, status type, date/time.
            If repat is None, then False is returned.
        """
        if not repat:
            # No filter applied.
            return True

        targets = (
            self.line,
            self.name,
            self.packagename,
            self.version,
            self.arch,
            self.statustype,
            self.action,
            str(self.time)
        )
        for targetstr in targets:
            if not targetstr:
                continue
            if repat.search(targetstr) is not None:
                return True
        return False


class PackageVersions(UserList):

    def __init__(self, pkg):
        """ Initialize version info for a single package. """
        self.package = pkg
        if not hasattr(pkg, 'versions'):
            raise TypeError(
                'Expecting a Package with a `versions` attribute.'
            )

        self.data = [v.version for v in pkg.versions]
        if pkg.installed:
            self.installed = pkg.installed.version
        else:
            self.installed = None
        if not self.data:
            raise ValueError('Empty `versions` attribute for Package.')
        self.latest = self.data[0]

    def formatted(self, header=True):
        """ Return a formatted string for the latest/installed version. """
        verstr = self.format_ver_latest()
        verinfo = '{} {}'.format(self.format_name(), verstr)
        if header:
            return 'Version:\n    {}'.format(
                verinfo
            )
        return verinfo

    def formatted_all(self, header=True):
        """ Return a formatted string for all versions. """
        length = len(self)
        plural = 'version' if length == 1 else 'versions'
        versions = (self.format_ver(v) for v in self)
        if header:
            headerstr = '\nFound {} {} for: {}'.format(
                C(str(length), fore='blue'),
                plural,
                self.format_name())
        else:
            headerstr = self.format_name()

        return '\n'.join((
            headerstr,
            '    {}'.format('\n    '.join(versions))
        ))

    def format_desc(self):
        """ Return a formatted description for the package version. """
        return '\nDescription:\n{}\n'.format(
            C(
                format_block(
                    get_pkg_description(self.package),
                    maxwidth=76,
                    newlines=True,
                    prepend='    '),
                fore='green'
            )
        )

    def format_name(self):
        """ Colorize the name for this package. """
        return pkg_format_name(self.package.name)

    def format_ver(self, s):
        """ Colorize a single version number according to it's install state.
        """
        verstr = None
        if s == self.latest:
            verstr = C(' ').join(
                C(s, fore='blue'),
                C('latest', fore='blue').join('(', ')')
            )
        if s == self.installed:
            if not verstr:
                verstr = C(s, fore='green', style='bright')
            verstr = C(' ').join(
                verstr,
                C('installed', fore='green').join('(', ')')
            )
        if verstr:
            return str(verstr)
        # Not latest, or not installed.
        return str(C(s, fore='red'))

    def format_ver_latest(self):
        """ Format the latest/installed version number.
            This contains slightly more information than format_ver().
        """
        if self.latest == self.installed:
            return str(C(' ').join(
                C(self.installed, fore='green'),
                C('latest version is installed', fore='green').join('(', ')')
            ))
        if self.installed:
            # Installed, but warn about not being the latest version.
            return str(C(' ').join(
                C(self.installed, fore='green'),
                (C('installed', fore='green')
                    .reset(', latest version is: ')
                    .yellow(self.latest))
            ))

        return str(C(' ').join(
            C(self.latest, fore='red'),
            C('latest version available', fore='red').join('(', ')')
        ))


# Fatal Errors that will end this script when raised.
class BadSearchQuery(ValueError):
    def __init__(self, pattern, re_error):
        self.pattern = getattr(pattern, 'pattern', str(pattern))
        self.message = str(re_error)

    def __str__(self):
        return 'Bad search query \'{}\': {}'.format(
            self.pattern,
            self.message
        )


class CacheNotLoaded(Exception):
    pass


class NothingSingleton(object):
    """ A value to use as None, where None may actually have a meaning. """
    def __str__(self):
        return '<Nothing>'
Nothing = NothingSingleton()


# custom progress reporters
oprogress = SimpleOpProgress()
fprogress = SimpleFetchProgress()

# Apply monkey patch.
apt.Cache.get = cache_get

# START ---------------------------------------------------
if __name__ == '__main__':
    # Disable colors for non-ttys.
    colr_auto_disable()
    # Get actual terminal size.
    # TERM_WIDTH, TERM_HEIGHT = get_terminal_size()

    main_argd = docopt(
        USAGESTR,
        version='{} v. {}'.format(NAME, __version__))
    # grab start time for timing.
    start_time = time()
    try:
        ret = main(main_argd)
    except KeyboardInterrupt:
        print_err('\nUser cancelled.\n')
        ret = 2
    except (BadSearchQuery, CacheNotLoaded) as ex:
        print_err('\n{}'.format(ex))
        ret = 1

    # Report how long it took
    duration = time() - start_time
    if duration > 0.01:
        print_runtime(duration)

    sys.exit(ret)
