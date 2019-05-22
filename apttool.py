#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" apttool.py
    Provides a few apt-related functions based on the 'apt' module.
    -Christopher Welborn 06-??-2013

    Revisited: 4-7-2019
"""

from collections import namedtuple, UserList
from contextlib import suppress
from datetime import datetime
from enum import Enum
import os
import re
import stat
import struct
import sys
from time import time


def import_err(name, exc, module=None):
    """ Print an error message about missing third-party libs and exit. """
    module = module or name.lower()
    # Get actual module name from exception if possible, for when dependencies
    # are not installed.
    namepat = re.compile('cannot import name \'(?P<name>[^\']+)\'')
    namematch = namepat.search(str(exc))
    excname = None
    if namematch is not None:
        excname = namematch.groupdict().get('name', None)
    modname = exc.name or excname
    propername = name if name.lower() == str(modname).lower() else modname
    print(
        '\n'.join((
            'Missing important third-party library: {name}',
            'This can be installed with `pip`: pip install {module}',
            '\nError message: {exc}'
        )).format(
            name=propername,
            module=modname if (modname and modname != module) else module,
            exc=exc,
        ),
        file=sys.stderr
    )
    if modname and (modname != module):
        print(
            '\n'.join((
                '\n{name} depends on {module} to run correctly.',
            )).format(
                name=name,
                module=modname,
            ),
            file=sys.stderr,
        )
    sys.exit(1)


try:
    import apt                        # apt tools
    import apt.progress.text          # apt tools
except ImportError as ex:
    import_err('apt', ex)
try:
    import apt_pkg                    # for IterCache()
    from apt_pkg import gettext as _  # for IterCache()
except ImportError as ex:
    import_err('apt_pkg', ex)

try:
    from colr import (
        auto_disable as colr_auto_disable,
        Colr,
        disable as colr_disable,
        docopt,
        strip_codes,
        AnimatedProgress,
        Frames,
    )
    # Aliased for easier typing and shorter lines.
    C = Colr
except ImportError as excolr:
    import_err('Colr', excolr)

try:
    from fmtblock import FormatBlock
except ImportError as exfmtblk:
    import_err('FormatBlock', exfmtblk, module='formatblock')

# ------------------------------- End Imports -------------------------------

__version__ = '0.9.1'

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


class NothingSingleton(object):
    """ A value to use as None, where None may actually have a meaning. """
    def __str__(self):
        return '<Nothing>'


Nothing = NothingSingleton()

# GLOBALS ------------------------------------------------
# placeholder for global cache
cache_main = None

# Tuple for dependency_info() returns.
DependencyInfo = namedtuple(
    'DependencyInfo',
    ('package', 'version', 'relation')
)

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

    # Search.
    if argd['PATTERNS']:
        query = query_build(argd['PATTERNS'], all_patterns=argd['--all'])
        return cmd_search(
            query,
            use_desc=not argd['--names'],
            print_no_desc=argd['--short'],
            install_state=InstallStateEnum.from_argd(argd),
            case_insensitive=argd['--ignorecase'],
            dev_only=argd['--dev'],
            reverse=argd['--reverse']
        )

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


def cache_get(self, item, default=Nothing):
    """ Supplies Cache.get()
        To monkeypatch apt.Cache to act like a dict with .get()
    """
    try:
        val = self[item]
    except KeyError:
        if default is Nothing:
            raise
        return default
    return val


def cache_load(forced=False):
    """ Load apt.Cache(), setting global `cache_main`.
        Returns `cache_main`.
        Arguments:
            forced  : Reload cache, even if cache_main is loaded already.
    """
    global cache_main
    if forced or (cache_main is None):
        cache_main = apt.Cache(memonly=True)
    return cache_main


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
        return os.path.split(s)[-1]
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
    pluralpkgs = 'package.' if totalpkgs == 1 else 'packages.'
    print_status(
        '\nFound',
        C(totalfiles, fore='blue', style='bright'),
        pluralfiles,
        'in',
        C(totalpkgs, fore='blue', style='bright'),
        pluralpkgs,
    )
    return 0


def cmd_dependencies(pkgname, installstate=None, short=False):
    """ Print all dependencies for a package.
        Optionally, filter by installed or uninstalled.
        Arguments:
            pkgname       : (str) Package name to check dependencies for.
            installstate  : InstallStateEnum, to filter dependency list.
                            Default: InstallStateEnum.every
            short         : Use shorter output.
    """
    status = noop if short else print_status
    installstate = installstate or InstallStateEnum.every

    package = cache_main.get(pkgname, None)
    if package is None:
        print_err('\nCan\'t find a package by that name: {}'.format(pkgname))
        return 1

    totalstate = 0
    total = 0
    for pkgver in package.versions:
        status(
            '\n{} dependencies for {} v. {}'.format(
                str(installstate).title(),
                package.name,
                pkgver.version))
        for deplst in pkgver.dependencies:
            total += 1
            for dep in installstate.filter_pkgs(deplst):
                depinfo = dependency_info(dep, default=dep.name)
                print(
                    pkg_format(
                        depinfo.package,
                        no_ver=short,
                        no_desc=short,
                        use_version=depinfo.version,
                        use_relation=depinfo.relation,
                    )
                )
                totalstate += 1

    if installstate == InstallStateEnum.every:
        status('\nTotal: {}'.format(total))
    else:
        statestr = str(installstate).title()
        status('\nTotal: {}, {}: {}'.format(total, statestr, totalstate))
    return 0 if totalstate > 0 else 1


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
    print_status('\nLooking for \'{}\' to install...'.format(pkgname))
    if doupdate:
        updateret = cmd_update()
        if not updateret:
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

    try:
        package = cache_main[pkgname]
    except KeyError:
        print_missing_pkg(pkgname)
        return 1

    if not pkg_install_state(package):
        print_err(
            '\nThis package is not installed: {}'.format(
                C(package.name, 'blue')
            ),
            '\nCan\'t get installed files for ',
            'uninstalled packages.',
            sep=''
        )
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
        elif only_existing:
            continue
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

    print_status('\nLooking for \'{}\' to remove...'.format(pkgname))
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
            installstate  : InstallStateEnum, to filter dependency list.
                            Default: InstallStateEnum.every
            short         : Use shorter output.
    """
    status = noop if short else print_status
    installstate = installstate or InstallStateEnum.every
    try:
        package = cache_main[pkgname]
    except KeyError:
        print_missing_pkg(pkgname)
        return 1

    status('\nSearching for {} dependents on {}...'.format(
        installstate,
        package.name))
    totalstate = 0
    total = 0
    for pkg in installstate.filter_pkgs(cache_main):
        for pkgver in pkg.versions:
            for deplst in pkgver.dependencies:
                total += 1
                for dep in filter(lambda d: d.name == package.name, deplst):
                    print(pkg_format(pkg, no_ver=short, no_desc=short))
                    totalstate += 1

    if installstate == InstallStateEnum.every:
        status('\nTotal: {}'.format(total))
    else:
        statestr = str(installstate).title()
        status('\nTotal: {}, {}: {}'.format(total, statestr, totalstate))
    return 0 if totalstate > 0 else 1


def cmd_search(
        query, use_desc=True, print_no_desc=False, print_no_ver=False,
        install_state=None, case_insensitive=False, dev_only=False,
        reverse=False):
    """ print results while searching the cache...
        Arguments:
            query             : Seach term for package name/desc.
            use_desc          : Whether to search inside pkg descs.
                                Default: True
            print_no_desc     : If True, don't print descriptions of packages.
                                Default: False
            print_no_ver      : If True, don't print the latest versions.
                                Default: False
            install_state     : InstallStateEnum to filter packages.
                                Default: InstallStateEnum.every
            case_insensitive  : Whether searches are case insensitive.
            dev_only          : Whether to search only dev packages.
            reverse           : Reverses the match, to show packages that
                                DON'T match the pattern.
    """
    if dev_only:
        # This little feature would be wrecked by adding '$' to the pattern.
        if query.endswith('$'):
            query = query[:-1]
            queryend = '$'
        else:
            queryend = ''
        # Adding 'dev' to the query to search for development packages.
        query = '{}(.+)dev{}'.format(query, queryend)
    try:
        re_pat = re.compile(
            query,
            re.IGNORECASE if case_insensitive else 0)
    except re.error as ex:
        raise BadSearchQuery(query, ex)
    if sys.stdout.isatty():
        spinner = AnimatedProgress(
            'Loading APT Cache...',
            fmt=' {frame} {elapsed:<2.0f}s {text}',
            frames=Frames.dots_orbit.as_gradient(name='blue', style='bright'),
        )
        with spinner:
            cache = apt.cache.FilteredCache(progress=oprogress)
    else:
        # No animated spinner, stdout is not a tty.
        cache = apt.cache.FilteredCache(progress=oprogress)
    msg = C('').join(
        C('Searching ', 'blue'),
        C(install_state),
        ' ({})'.format(C('names only', 'blue')) if not use_desc else '',
        ' {}'.format(C(query, 'cyan')),
        (
            ' ({})'.format(C('case-insensitive', 'red'))
            if not case_insensitive
            else ''
        ),
    )
    print_status(msg)
    cache.set_filter(AptToolFilter(
        re_pat,
        use_desc=use_desc,
        install_state=install_state,
        reverse=reverse,
        print_no_desc=print_no_desc,
        print_no_ver=print_no_ver,
    ))

    result_cnt = len(cache)
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
        cache_load()

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
    status('\nLooking for \'{}\' versions...'.format(pkgname))
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
                'installstate': InstallStateEnum.from_argd(argd),
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
                'installstate': InstallStateEnum.from_argd(argd),
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
    return DependencyInfo(deppkg, depver, deprel)


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
        except Exception:
            pass
    cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
    if not cr:
        try:
            fd = os.open(os.ctermid(), os.O_RDONLY)
            cr = ioctl_GWINSZ(fd)
            os.close(fd)
        except Exception:
            pass
    if not cr:
        try:
            cr = (os.environ['LINES'], os.environ['COLUMNS'])
        except Exception:
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
            'Error checking executable stats: {}\n{}'.format(filename, ex))
        # Fallback to crude path check.
        return ('/bin/' in filename) and (not os.path.isdir(filename))
    return (
        stat.S_ISREG(st.st_mode) and
        st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    )


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
            installstate     : InstallStateEnum to match against.
                               Default: InstallStateEnum.every
    """

    desc_search = kwargs.get('desc_search', True)
    reverse = kwargs.get('reverse', False)
    installstate = (
        kwargs.get('installstate', InstallStateEnum.every) or
        InstallStateEnum.every)

    # Trim filtered packages.
    if not installstate.matches_pkg(pkg):
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
    pkgdesc = FormatBlock(pkgdesc_full).format(
        width=descmax,
        strip_first=True,
        prepend=padding,
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

    maxdesclines = 2
    maxdesclen = (descmax * maxdesclines) - 3
    if len(pkgdesc) > maxdesclen:
        pkgdesc = '{}...'.format(pkgdesc[:maxdesclen].rstrip())

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

        If expected is passed (a InstallStateEnum enum),
        returns True if the InstallStateEnum matches the packages install
        state, or if InstallState.every is used.
    """
    expected = expected or InstallStateEnum.installed
    # This function is useless with InstallStateEnum.every.
    if expected == InstallStateEnum.every:
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
        # Last try, could be a dependency object.
        pkg = cache_main.get(getattr(pkg, 'name', None), None)
        if pkg is not None:
            return pkg_install_state(pkg, expected=expected)
        # API fell through?
        # (it has happened before, hince the need for the 2 ifs above)
        print_err(
            'Please file a bug, API failed install state check: {!r}'.format(
                pkg
            )
        )
        actualstate = False

    if expected == InstallStateEnum.installed:
        return actualstate
    if expected == InstallStateEnum.uninstalled:
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
        C(kwargs.get('sep', ' ')).join(
            a if isinstance(a, C) else C(a, 'red')
            for a in args
        ),
        **kwargs
    )


def print_example_usage():
    """ Print specific usage examples when -? is used. """
    CmdExample = namedtuple('CmdExample', ('cmd', 'desc'))

    print('\n'.join((
        '{name} v. {ver}'.format(
            name=C(NAME, 'blue', style='bright'),
            ver=C(__version__, 'blue'),
        ),
        '\nExample Usage:',
    )))
    cmdexamples = (
        CmdExample(
            'foo -I',
            'Shows installed packages with \'foo\' in the name or desc.',
        ),
        CmdExample(
            'bar -n -N',
            'Show non-installed packages with \'bar\' in the name only.',
        ),
        CmdExample(
            '-f python',
            'Show installed files for the \'python\' package.',
        ),
        CmdExample(
            '-e python',
            'Show installed executables for the \'python\' package.',
        ),
        CmdExample(
            '-S python',
            'Show suggested packages for the \'python\' package.',
        ),
        CmdExample(
            '-l pythonfoo',
            '\n    '.join((
                'Determine whether a full package name exists in the cache.',
                'This is quicker than a full search.',
            ))
        ),
        CmdExample(
            '-H install',
            'Search dpkg history for latest installs/half-installs.',
        ),
        CmdExample(
            '-c foo',
            'Show packages containing files with \'foo\' in the path.',
        ),
        CmdExample(
            '-h',
            'Show full help/options.',
        ),
    )
    for cmdexample in cmdexamples:
        print('\n    {}'.format(C(cmdexample.desc, 'cyan')))
        print('    {} {}'.format(
            C(SCRIPT, 'blue', style='bright'),
            C(cmdexample.cmd, 'blue'),
        ))

    StateExample = namedtuple('StateExample', ('char', 'desc'))
    print('\nMarker Legend:')
    stateexamples = (
        StateExample('i', 'package is installed'),
        StateExample('u', 'package is not installed'),
        StateExample('?', 'package name was not found in the cache'),
    )
    for stateexample in stateexamples:
        print('    {} = {}'.format(
            C(stateexample.char, 'blue').join('[', ']'),
            C(stateexample.desc, 'cyan'),
        ))

    print('\nNotes:')
    print(
        C(
            '\n'.join((
                '    If no options are given, the default behaviour is to',
                '    search for packages by name and description, then',
                '    print results.',
            )),
            'cyan',
        )
    )


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


def py_ver_at_least(major=0, minor=0, micro=0):
    """ Returns True if the current python version is equal or greater to
        the one given.
    """
    return (
        sys.version_info.major >= major and
        sys.version_info.minor >= minor and
        sys.version_info.micro >= micro
    )


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
    status = noop if argd['--short'] else print_status
    # Initialize
    if sys.stdout.isatty():
        spinner = AnimatedProgress(
            'Loading APT Cache...',
            fmt=' {frame} {elapsed:<2.0f}s {text}',
            frames=Frames.dots_orbit.as_gradient(name='blue', style='bright'),
        )
        with spinner:
            cache_load()
    else:
        # No amimated spinner, stdout is not a tty.
        cache_load()

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
class AptToolFilter(apt.cache.Filter):
    """ A filter that uses apttool config to filter packages. """
    def __init__(
            self, pattern, use_desc=True, install_state=None, reverse=False,
            print_no_desc=False, print_no_ver=False):
        self.pattern = pattern
        self.use_desc = use_desc
        self.install_state = install_state or InstallStateEnum.every
        self.reverse = reverse

        # Display options
        self.print_no_desc = print_no_desc
        self.print_no_ver = print_no_ver

    def apply(self, pkg):
        # Trim filtered packages.
        if not self.install_state.matches_pkg(pkg):
            return False

        def matchfunc(targetstr, reverse=False):
            rematch = self.pattern.search(targetstr)
            matched = (rematch is None) if reverse else (rematch is not None)
            return matched

        # Try matching the name. (reverse handled also.)
        if matchfunc(pkg.name, self.reverse):
            return self.on_match(pkg)
        if not self.use_desc:
            return False

        pkgdesc = get_pkg_description(pkg)

        # Try matching description.
        if pkgdesc and matchfunc(pkgdesc, self.reverse):
            return self.on_match(pkg)
        # No match/no desc to search
        return False

    def on_match(self, pkg):
        print('\n{}'.format(
            pkg_format(
                pkg,
                no_desc=self.print_no_desc,
                no_ver=self.print_no_ver
            )
        ))
        return True


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


class InstallStateEnum(Enum):

    """ For querying packages with a certain install state. """
    uninstalled = -1
    every = 0
    installed = 1

    def __colr__(self):
        """ Colr representation. """
        return C(str(self), 'blue', style='bright')

    def __str__(self):
        """ Enhanced representation for console. """
        return {
            InstallStateEnum.uninstalled.value: 'uninstalled',
            InstallStateEnum.every.value: 'all',
            InstallStateEnum.installed.value: 'installed'
        }.get(self.value, 'unknown')

    def filter_pkgs(self, pkglst):
        """ Return a filter object with packages matching this install state.
        """

        return filter(
            lambda pkg: pkg_install_state(pkg, expected=self),
            pkglst
        )

    @classmethod
    def from_argd(cls, argd):
        """ Maps a filter arg to an actual InstallStateEnum. """
        if argd['--INSTALLED']:
            return cls.installed
        if argd['--NOTINSTALLED']:
            return cls.uninstalled
        return cls.every

    def matches_pkg(self, pkg):
        """ Return True if the `pkg` matches this install state filter. """
        return pkg_install_state(pkg, expected=self)


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
                try:
                    pkgname, pkgarch = pkgnameraw.split(':')
                except ValueError:
                    pkgname = pkgnameraw
                    pkgarch = None
                pkgver = parts[5]
            elif statustype in {'configure', 'trigproc'}:
                pkgnameraw = parts[3]
                try:
                    pkgname, pkgarch = pkgnameraw.split(':')
                except ValueError:
                    pkgname = pkgnameraw
                    pkgarch = None
                pkgver = parts[4]
            elif statustype in {'install', 'upgrade'}:
                pkgnameraw = parts[3]
                try:
                    pkgname, pkgarch = pkgnameraw.split(':')
                except ValueError:
                    pkgname = pkgnameraw
                    pkgarch = None
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
            If repat is None, then True is returned.
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

        # self.data = [v.version for v in pkg.versions]
        self.data = []
        for ver in pkg.versions:
            self.data.append(ver)
            ver.has_backport = False
            for origin in ver.origins:
                if origin.archive.endswith('backports'):
                    ver.has_backport = True
                    break

        self.installed = pkg.installed or None

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
        if header:
            headerstr = '\nFound {} {} for: {}'.format(
                C(length, fore='blue'),
                'version' if length == 1 else 'versions',
                self.format_name())
        else:
            headerstr = self.format_name()

        return '\n'.join((
            headerstr,
            '    {}'.format(
                '\n    '.join(
                    self.format_ver(v) for v in self
                )
            )
        ))

    def format_desc(self):
        """ Return a formatted description for the package version. """
        return '\nDescription:\n{}\n'.format(
            C(
                FormatBlock(get_pkg_description(self.package)).format(
                    width=76,
                    newlines=True,
                    prepend='    '
                ),
                fore='green'
            )
        )

    def format_name(self):
        """ Colorize the name for this package. """
        return pkg_format_name(self.package.name)

    def format_ver(self, ver):
        """ Colorize a single version number according to it's install state.
        """
        s = ver.version
        verstr = None
        if ver == self.latest:
            verstr = C(' ').join(
                C(s, fore='blue'),
                C('latest', fore='blue').join('(', ')')
            )
        if ver == self.installed:
            if not verstr:
                verstr = C(s, fore='green', style='bright')
            verstr = C(' ').join(
                verstr,
                C('installed', fore='green').join('(', ')')
            )
        if ver.has_backport:
            verstr = C(' ').join(
                verstr,
                C('backports', fore='cyan').join('(', ')')
            )
        if verstr:
            return str(verstr)
        # Not latest, or not installed.
        return str(C(s, fore='red'))

    def format_ver_latest(self):
        """ Format the latest/installed version number.
            This contains slightly more information than format_ver().
        """
        backportcheckver = self.latest
        if self.latest == self.installed:
            fmt = C(' ').join(
                C(self.installed.version, fore='green'),
                C('latest version is installed', fore='green').join('(', ')')
            )
        elif self.installed:
            # Installed, but warn about not being the latest version.
            fmt = C(' ').join(
                C(self.installed.version, fore='green'),
                (C('installed', fore='green')
                    .reset(', latest version is: ')
                    .yellow(self.latest))
            )
            backportcheckver = self.installed
        else:
            fmt = C(' ').join(
                C(self.latest.version, fore='red'),
                C('latest version available', fore='red').join('(', ')')
            )

        if backportcheckver.has_backport:
            fmt = C(' ').join(
                fmt,
                C('backports', fore='cyan').join('(', ')')
            )
        return str(fmt)


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
    TERM_WIDTH, TERM_HEIGHT = get_terminal_size()
    TERM_WIDTH -= 10
    main_argd = docopt(
        USAGESTR,
        version='{} v. {}'.format(NAME, __version__),
        script=SCRIPT,
    )
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
    finally:
        try:
            cache_main.close()
        except AttributeError:
            # Cache was never loaded.
            pass
    # Report how long it took
    duration = time() - start_time
    if duration > 0.01:
        print_runtime(duration)

    sys.exit(ret)
