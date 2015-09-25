#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" apttool.py
    provides a few apt-related functions based on the 'apt' module.
    -Christopher Welborn
    06-2013
"""


from datetime import datetime      # timing, log parsing
from enum import Enum              # install states.
import os.path                     # for file/dir
import re                          # search pattern matching
import sys                         # for args (Scriptname)
import weakref                     # for IterCache()

try:
    import apt                        # apt tools
    import apt_pkg                    # for IterCache()
    from apt_pkg import gettext as _  # for IterCache()
    import apt.progress.text          # apt tools
except ImportError as eximp:
    print('\n'.join([
        '\nMissing important module or modules!\n{}'.format(eximp),
        '\nThese must be installed:',
        '      apt: ..uses apt.progress.text and others',
        '  apt_pkg: ..uses apt_pkg.gettext and others.',
        '\nTry doing: pip install <modulename>\n'
    ]))
    sys.exit(1)


try:
    from docopt import docopt        # cmdline arg parser
except ImportError as exdoc:
    print('\nDocopt must be installed, '
          'try: pip install docopt.\n\n{}'.format(exdoc))
    sys.exit(1)

__version__ = '0.3.2'
NAME = 'AptTool'

# Get short script name.
SCRIPT = os.path.split(sys.argv[0])[-1]

USAGESTR = """{name} v. {version}

    Usage:
        {script} -c file [-n]
        {script} -i package
        {script} -d package | -p package
        {script} -e package | -f package
        {script} (-P package | -R package) [-I | -N]
        {script} -H [QUERY] [COUNT]
        {script} -h | -v
        {script} (-l | -L) PACKAGES...
        {script} -u
        {script} -V PACKAGES... [-a]
        {script} <pkgname> [-I | -N] [-D | -n] [-r] [-s] [-x]

    Options:
        COUNT                        : Number of history lines to return.
        PACKAGES                     : One or many package names to try.
                                       If a file name is given, the names
                                       are read from the file. If '-' is given,
                                       names are read from stdin.
        QUERY                        : Query to filter history with. The
                                       default is 'installed'.
        -a,--all                     : When viewing package version, list all
                                       available versions.
        -c file,--containsfile file  : Search all installed packages for an
                                       installed file using regex or text.
        -D,--dev                     : Search for development packages.
        -d pkg,--delete pkg          : Uninstall/delete/remove a package.
        -e pkg,--executables pkg     : Show installed executables for a
                                       package.
                                       It just shows files installed to
                                       /bin directories.
        -f pkg,--files pkg           : Show installed files for package.
        -h,--help                    : Show this help message and exit.
        -H,--history                 : Show package history.
                                       (installs, uninstalls, etc.)
        -i pkg,--install pkg         : Install a package.
        -I,--INSTALLED               : When searching for a package, only
                                       include installed packages.
        -l,--locate                  : Determine whether or not a package
                                       exists. You can pass a file name to
                                       read from, or use - for stdin. Otherwise
                                       a full package name is needed. Multiple
                                       names can be passed.
        -L,--LOCATE                  : Same as --locate, but only shows
                                       existing packages that are found.
        -n,--names                   : When searching for packages, only search
                                       names, not descriptions.
                                       When searching with -c, don't use the
                                       full file path, only the file name.
        -N,--NOTINSTALLED            : When searching for a package, only
                                       include non-installed packages.
        -p pkg,--purge pkg           : Purge the package completely,
                                       remove all configuration.
        -P pkg,--dependencies pkg    : List all dependencies for a package.
        -s,--short                   : When searching, don't print the
                                       description.
        -R pkg,--reversedeps pkg     : Show reverse dependencies.
        -r,--reverse                 : When searching, return packages that
                                       DON'T match.
        -u,--update                  : Update the cache.
                                       ..Just like `apt-get update`
        -v,--version                 : Show version and exit.
        -V,--VERSION                 : Show a package's installed or available
                                       versions.
        -x,--nocase                  : Make the search query case-insensitive.

    Notes:
        If no options are given, the default behaviour is to search for
        packages by name and description, then print results.

        In the search results:
            [i] = package is installed
            [u] = package is not installed

""".format(name=NAME, script=SCRIPT, version=__version__)


# GLOBALS ------------------------------------------------
# placeholder for global cache
cache_main = None
# Something besides None to represent no value (where None has meaning)
NoValue = object()


# MAIN ---------------------------------------------------
def main(argd):
    """ Main entry point for apttool """
    global cache_main, oprogress, fprogress

    # Search (iter_open the cache, not pre-load. for performance)
    if argd['<pkgname>']:
        try:
            return cmdline_search(
                argd['<pkgname>'],
                desc_search=(not argd['--names']),
                print_no_desc=argd['--short'],
                installstate=InstallStateFilter.from_argd(argd),
                case_insensitive=argd['--nocase'],
                dev_only=argd['--dev'],
                reverse=argd['--reverse'])
        except KeyboardInterrupt:
            print('\nUser Cancelled, goodbye.')
            return 1

    if argd['--history']:
        # Just show apt history and exit.
        cnt = argd['COUNT']
        if cnt:
            try:
                cnt = int(cnt)
                if cnt < 1:
                    raise ValueError('Must be greater than 0!')
            except (TypeError, ValueError) as exint:
                print('\nInvalid number for count: {}\n{}'.format(cnt, exint))
                return 1

        return get_history(argd['QUERY'], count=cnt)

    # -----v-- Actions that may benefit from cache pre-loading --v------
    return run_preload_cmd(argd)


# FUNCTIONS -----------------------------------------------
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


def cmdline_search(query, **kwargs):
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
    print('Initializing Cache...')
    cache = IterCache(do_open=False)
    cache._pre_iter_open()
    print('Searching ~' + str(cache.rough_size) + ' packages for ' + query)

    # Update arguments for use with search_itercache().
    kwargs.update({
        'cache': cache,
        'progress': None,
    })

    result_cnt = 0
    try:
        for result in search_itercache(query, **kwargs):
            print('\n{}'.format(format_pkg(
                result,
                no_desc=print_no_desc,
                no_ver=print_no_ver)))
            result_cnt += 1
    except BadSearchQuery as expat:
        print('\nInvalid query: {}\n    {}'.format(query, expat))
        return 1

    # except Exception as ex:
    #    print('Error while searching:\n' + str(ex))
    #    raise Exception(ex)

    result_str = ' result.' if result_cnt == 1 else ' results.'
    print('\nFinished searching, found ' + str(result_cnt) + result_str)
    return 0


def dependencies(pkgname, installstate=None):
    """ Print all dependencies for a package.
        Optionally, filter by installed or uninstalled.
        Arguments:
            pkgname       : (str) Package name to check dependencies for.
            installstate  : InstallStateFilter, to filter dependency list.
                            Default: InstallStateFilter.every
    """
    installstate = installstate or InstallStateFilter.every

    package = cache_main.get(pkgname, None)
    if package is None:
        print('\nCan\'t find a package by that name: {}'.format(pkgname))
        return 1

    is_match = (
        lambda dep:
            get_install_state(dep.name, expected=installstate))
    total = 0
    for pkgver in package.versions:
        print(
            '\n{} dependencies for {} v. {}'.format(
                str(installstate).title(),
                package.name,
                pkgver.version))
        for deplst in pkgver.dependencies:
            for dep in filter(is_match, deplst):
                print('    {d.name:<40} {d.relation} {d.version}:'.format(
                    d=dep
                ))
                total += 1

    print('\nTotal ({}): {}'.format(installstate, total))
    return 0 if total > 0 else 1


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


def format_pkg(result, no_desc=False, no_ver=False):
    """ prints a single search result to the console

        Keyword Arguments:
            no_desc : If True, only prints state and name.
            no_ver  : If True, print package version also (even with no_desc).
    """

    # name formatting
    pkgname = '[{}] {:<30}'.format(
        'i' if get_install_state(result) else 'u',
        result.name)

    # No description needed RETURN only the name....
    if no_desc:
        if no_ver:
            return pkgname
        # Give an extra 50 chars for the pkgname since no desc is needed.
        return '{:<50} {}'.format(pkgname, get_latest_ver(result))

    # Get Package Description....
    pkgdesc_full = get_pkg_description(result)
    # No description to search?
    if not pkgdesc_full:
        return pkgname

    padlen = len(pkgname) + 3
    descmax = 80 - padlen
    padding = ' ' * padlen
    if len(pkgdesc_full) <= descmax:
        # already short description
        pkgdesc = pkgdesc_full
        if not no_ver:
            # Add a second line for the version.
            pkgdesc = '\n'.join((
                pkgdesc_full,
                '    {}'.format(get_latest_ver(result))
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
            pkgver = '    {}'.format(get_latest_ver(result))
            if len(pkglines) > 1:
                # Replace part of the second line with the version.
                pkglines[1] = ''.join((
                    pkgver,
                    pkglines[1][len(pkgver):]
                ))
            else:
                # Add a second line for the version.
                pkglines.append(pkgver)

            pkgdesc = '\n'.join(pkglines)

    if len(pkgdesc) > 188:
        pkgdesc = '{}...'.format(pkgdesc[:185].rstrip())

    return ' : '.join((pkgname, pkgdesc))


def format_pkg_OLD(result, no_desc=False, no_ver=False):
    """ prints a single search result to the console

        Keyword Arguments:
            no_desc : If True, only prints state and name.
            no_ver  : If True, print package version also (even with no_desc).
    """

    # max text lengths
    desc_max = 46
    # name formatting
    pkgname = '[{}] {:<30}'.format(
        'i' if get_install_state(result) else 'u',
        result.name)

    # No description needed RETURN only the name....
    if no_desc:
        if no_ver:
            return pkgname
        # Give an extra 50 chars for the pkgname since no desc is needed.
        return '{:<50} {}'.format(pkgname, get_latest_ver(result))

    # Get Package Description....
    pkgdesc_full = get_pkg_description(result)
    # No description to search?
    if not pkgdesc_full:
        return pkgname

    # description slicing, remove newlines
    if '\n' in pkgdesc_full:
        pkgdesc_full = pkgdesc_full[:pkgdesc_full.index('\n')]

    if len(pkgdesc_full) <= desc_max:
        # already short description
        pkgdesc = pkgdesc_full
    else:
        # trim to 2 lines worth, or use first sentence.
        pkgdesc_full = pkgdesc_full[:(desc_max * 2)]
        if '.' in pkgdesc_full:
            # use first sentance.
            pkgline = pkgdesc_full[:pkgdesc_full.index('.') + 1]
        else:
            # set up to use two lines of text.
            pkgline = pkgdesc_full
        padding = (' ' * (len(pkgname) + 3))
        pkgdesc_lines = [
            pkgline[:desc_max],
            '{}{}'.format(padding, pkgline[desc_max:].strip()[:-4]),
        ]

        if not pkgdesc_lines[1].strip():
            # One line description.
            if no_ver:
                pkgdesc = pkgdesc_lines[0]
            else:
                # Add a second line for the version.
                pkgdesc = '\n'.join((
                    pkgdesc_lines[0],
                    '    {}'.format(get_latest_ver(result))
                ))
        else:
            if not no_ver:
                # Replace part of the second line with the latest version.
                pkgver = '    {}'.format(get_latest_ver(result))
                pkgdesc_lines[1] = ''.join((
                    pkgver,
                    pkgdesc_lines[1][len(pkgver):]
                ))
            pkgdesc = '{}...'.format('\n'.join(pkgdesc_lines))

    return ' : '.join((pkgname, pkgdesc))


def get_actual_package(possiblepkg):
    """ Returns the original package if this is the old apt API,
        If this is the new apt API, then further processing is done
        to retrieve the actual installed package.
    """

    if hasattr(possiblepkg, 'description'):
        return possiblepkg
    elif hasattr(possiblepkg, 'installed'):
        return possiblepkg.installed


def get_history(filtertext=None, count=None):
    """ Search dpkg log for lines containing text, print the formatted lines.
        If filtertext is None, all lines are formatted and printed.
    """
    repat = None
    if filtertext is not None:
        try:
            repat = re.compile(filtertext)
        except re.error as exre:
            errfmt = 'Invalid filter text: {}\n{}'
            print(errfmt.format(filtertext, exre))
            return False

    cnt_exceeded = (lambda i: False) if not count else (lambda i: (i >= count))
    total = 0
    try:
        for historyline in iter_history():
            if historyline.matches(repat):
                total += 1
                print(str(historyline))
            if cnt_exceeded(total):
                break
        entryplural = 'entry' if total == 1 else 'entries'
        print('\nFound {} {}.'.format(total, entryplural))

    except (EnvironmentError, FileNotFoundError, re.error) as excancel:
        print('\nUnable to retrieve history:\n    {}'.format(excancel))
        return False
    except Exception as exgeneral:
        print('\nUnexpected error: {}'.format(exgeneral))
        return False

    return True


def get_install_state(pkg, expected=None):
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
                return get_install_state(pkg, expected=expected)

        # API fell through?
        # (it has happened before, hince the need for the 2 ifs above)
        actualstate = False

    if expected == InstallStateFilter.installed:
        return actualstate
    if expected == InstallStateFilter.uninstalled:
        return not actualstate
    # Should not reach this.
    print_err(
        '\nUnreachable code in get_install_state({!r}, expected={})!'
        .format(pkg, expected))
    return True


def get_latest_ver(pkg):
    """ Return the latest version for a package. """
    try:
        ver = pkg.versions[0]
    except AttributeError:
        return 'unknown'
    else:
        return (ver.version or 'unknown').strip()


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


def install_package(pkgname, doupdate=False):
    """ Install a package. """
    print('\nLooking for \'{}\'...'.format(pkgname))
    if doupdate:
        updateret = update()
        if updateret:
            print('\nCan\'t update cache!')

    if pkgname in cache_main.keys():
        package = cache_main[pkgname]
        if get_install_state(package):
            print('\nThis package is already installed: '
                  '{}'.format(package.name))
            return 1

        print('Installing package: {}'.format(package.name))
        # Mark for install.
        if not hasattr(package, 'mark_install'):
            print(
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
            print(
                '\nCan\'t install package, '
                'make sure you have proper permissions. (are you root?)\n'
                '\nError Message:\n{}'.format(exlock))
            return 1
        except SystemError as exsys:
            # dpkg is already being used by something else.
            print(
                '\nCan\'t install package, '
                'make sure all other package managers are closed.\n'
                '\nError Message:\n{}'.format(exsys))
            return 1

    else:
        print('\nCan\'t find a package by that name: {}'.format(pkgname))
        return 1
    return 0


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
    if not get_install_state(pkg, expected=installstate):
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
        fmtline = lambda s: s

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
        is_skipped = lambda l: l.startswith('#') or (not l)
    else:
        is_skipped = lambda l: (not l)
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

            newlines     : Whether to preserve newlines in the original string.
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


def locate_packages(lst, only_existing=False):
    """ Locate one or more packages.
        Arguments:
            lst            : A list of package names, or file names to read
                             from. If '-' is encountered in the list then stdin
                             is used. (stdin) can only be used once.
            only_existing  : Only show existing packages.
    """
    existing = 0
    checked = 0
    for pname in parse_packages_arg(lst):
        if package_exists(pname, print_missing=not only_existing):
            existing += 1
        checked += 1

    plural = 'package' if existing == 1 else 'packages'
    print('\nFound {} of {} {}.'.format(existing, checked, plural))
    return 0 if (checked > 0) and (existing == checked) else 1


def package_exists(pname, print_missing=True):
    """ Helper or locate_packages().
        Prints a message if the package exists.
        Returns True for existing package, False for missing package.
    """
    if pname.lower().strip() in cache_main:
        print('{}: exists'.format(pname.rjust(20)))
        return True
    if print_missing:
        print('{}: missing'.format(pname.rjust(20)))
    return False


def parse_packages_arg(names):
    """ Parse the --PACKAGES arg, which accepts package names,
        file names, or '-' for stdin.
        Yields package names as they are read (from arg, from file, or stdin).
    """
    did_stdin = False
    for pname in names:
        if pname.strip() == '-':
            if did_stdin:
                print('Already read from stdin.')
                continue
            if sys.stdin.isatty() and sys.stdout.isatty():
                print('\nReading package names from stdin...\n')
            did_stdin = True
            for s in sys.stdin.read().split():
                yield s.strip()
        elif os.path.isfile(pname):
            try:
                with open(pname, 'r') as f:
                    for s in f:
                        yield s.strip()
            except EnvironmentError as ex:
                print('\nError reading from file: {}\n{}'.format(pname, ex))
                continue
        else:
            yield pname


def print_err(*args, **kwargs):
    """ Like print(), except `file` is always set to sys.stderr. """
    kwargs['file'] = sys.stderr
    return print(*args, **kwargs)


def print_installed_files(pkgname, execs_only=False):
    """ Print a list of installed files for a package. """
    print('\nGetting installed {} for \'{}\'\n'.format(
        'executables' if execs_only else 'files',
        pkgname))
    if pkgname not in cache_main.keys():
        print('\nCan\'t find a package with that name: {}'.format(pkgname))
        return 1
    package = cache_main[pkgname]

    if not get_install_state(package):
        print(''.join(['\nThis package is not installed: ',
                       '{}'.format(package.name),
                       '\nCan\'t get installed files for ',
                       'uninstalled packages.']))
        return 1

    if not hasattr(package, 'installed_files'):
        print(''.join(['\nUnable to get installed files for ',
                       '{}'.format(package.name),
                       ', apt/apt_pkg module may be out of date.']))
        return 1

    files = sorted(package.installed_files)
    if execs_only:
        # Show executables only (/bin directory files.)
        # Returns true for a path if it looks like an executable.
        is_exec = lambda s: ('/bin' in s) and (not s.endswith('/bin'))
        files = [s for s in files if is_exec(s)]
        label = 'executables'
    else:
        # Show installed files.
        label = 'installed files'

    if files:
        print('Found {} {} for {}:'.format(len(files), label, package.name))
        print('    {}\n'.format('\n    '.join(sorted(files))))
        return 0

    # No files found (possibly after trimming to only executables)
    print('Found 0 {} for: {}'.format(label, package.name))
    return 1


def print_package_version(pkgname, allversions=False):
    """ Retrieve and print the current version info for a package.
        Returns 0 for success, 1 for error.
    """
    print('\nLooking for \'{}\'...'.format(pkgname))
    if pkgname not in cache_main.keys():
        print('\nCan\'t find a package with that name: {}'.format(pkgname))
        return 1

    package = cache_main[pkgname]

    if not hasattr(package, 'versions'):
        print(''.join(['\nUnable to retrieve versions for ',
                       '{}'.format(pkgname),
                       ', apt/apt_pkg may be out of date.']))
        return 1

    versions = [v.version for v in package.versions]
    if package.installed:
        installedver = package.installed.version
    else:
        installedver = None

    latestver = versions[0]
    latestinstalled = latestver == installedver
    versions[0] = '{} (latest)'.format(latestver)
    versions = ['{} (installed)'.format(v)
                if v.split()[0] == installedver else v for v in versions]

    if allversions:
        verlen = len(versions)
        plural = 'version' if verlen == 1 else 'versions'
        print('\nFound {} {} for: {}'.format(
            verlen,
            plural,
            package.name))
        print('    {}'.format('\n    '.join(versions)))
    else:
        print('\nVersion:')
        if latestinstalled:
            fmtargs = package.name, installedver
            print('    {} {} (latest version is installed)\n'.format(*fmtargs))
        elif installedver:
            fmtargs = package.name, installedver, latestver
            fmtline = '    {} {} installed, latest version is: {}\n'
            print(fmtline.format(*fmtargs))
        else:
            fmtargs = package.name, latestver
            print('    {} {} (latest version available)\n'.format(*fmtargs))

    pkgdesc = format_block(
        get_pkg_description(package),
        maxwidth=76,
        newlines=True,
        prepend='    ')
    print('Description:\n{}\n'.format(pkgdesc))

    return 0


def print_package_versions(pkgnames, allversions=False):
    """ Same as print_package_version(), but expects a list of package names.
    """
    errs = 0
    div = '-' * 80
    for pname in parse_packages_arg(pkgnames):
        print('\n{}'.format(div))
        errs += print_package_version(pname, allversions=allversions)
    return errs


def remove_package(pkgname, purge=False):
    """ Remove or Purge a package by name """

    print('\nLooking for \'{}\'...'.format(pkgname))
    if purge:
        opaction = 'purge'
        opstatus = 'Purging'
    else:
        opaction = 'remove'
        opstatus = 'Removing'

    package = cache_main.get(pkgname, None)
    if package is None:
        print('\nCan\'t find a package by that name: {}'.format(pkgname))
        return 1

    if not get_install_state(package):
        print('\nThis package is not installed: {}'.format(package.name))
        return 1

    print('Removing package: {}'.format(package.name))
    # Mark for delete.
    if not hasattr(package, 'mark_delete'):
        print('\napt_pkg doesn\'t have \'mark_delete\' attribute, '
              'apt/apt_pkg module may be out of date.\n'
              'Stopping.')
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
        print(''.join([
            '\nCan\'t {} package, '.format(opaction),
            'make sure you have proper permissions. (are you root?)\n',
            '\nError Message:\n{}'.format(exlock),
        ]))
        return 1
    except SystemError as exsys:
        # dpkg is already being used by something else.
        print(''.join([
            'Can\'t {} package, '.format(opaction),
            'make sure all other package managers are closed.\n'
            '\nError Message:\n{}'.format(exsys),
        ]))
        return 1


def reverse_dependencies(pkgname, installstate=None):
    """ Print all reverse dependencies for a package.
        Optionally, filter by installed or uninstalled.
        Arguments:
            pkgname       : (str) Package name to check dependencies for.
            installstate  : InstallStateFilter, to filter dependency list.
                            Default: InstallStateFilter.every
    """
    installstate = installstate or InstallStateFilter.every

    package = cache_main.get(pkgname, None)
    if package is None:
        print('\nCan\'t find a package by that name: {}'.format(pkgname))
        return 1

    print('\nSearching for {} dependents on {}...'.format(
        installstate,
        package.name))
    total = 0
    for pkg in cache_main:
        for pkgver in pkg.versions:
            for deplst in pkgver.dependencies:
                for dep in filter(lambda d: d.name == package.name, deplst):
                    if not get_install_state(pkg, expected=installstate):
                        continue
                    print(
                        '    {p.name:<40} {v.version}'.format(
                            p=pkg,
                            v=pkgver
                        ))
                    total += 1

    print('\nTotal ({}): {}'.format(installstate, total))
    return 0 if total > 0 else 1


def run_preload_cmd(argd):
    """ Handle command-line options that may benefit from preloading the
        cache.
    """
    global cache_main

    # Initialize
    print('Loading APT Cache...')
    cache_main = apt.Cache()
    if not cache_main:
        print('Failed to load apt cache!')
        return 1

    # Cache was loaded properly.
    print('Loaded {} packages.'.format(len(cache_main)))

    funcmap = {
        '--containsfile': {
            'func': search_file,
            'args': (argd['--containsfile'],),
            'kwargs': {'shortnamesonly': argd['--names']}
        },
        '--dependencies': {
            'func': dependencies,
            'args': (argd['--dependencies'],),
            'kwargs': {
                'installstate': InstallStateFilter.from_argd(argd)
            }
        },
        '--delete': {  # --purge
            'func': remove_package,
            'args': (argd['--delete'] or argd['--purge'],),
            'kwargs': {'purge': bool(argd['--purge'])}
        },
        '--executables': {
            'func': print_installed_files,
            'args': (argd['--executables'],),
            'kwargs': {'execs_only': True}
        },
        '--files': {
            'func': print_installed_files,
            'args': (argd['--files'],)
        },
        '--install': {
            'func': install_package,
            'args': (argd['--install'],)
        },
        '--locate': {  # --LOCATE
            'func': locate_packages,
            'args': (argd['PACKAGES'],),
            'kwargs': {'only_existing': argd['--LOCATE']}
        },
        '--reversedeps': {
            'func': reverse_dependencies,
            'args': (argd['--reversedeps'],),
            'kwargs': {
                'installstate': InstallStateFilter.from_argd(argd)
            }
        },
        '--update': {'func': update},
        '--VERSION': {
            'func': print_package_versions,
            'args': (argd['PACKAGES'],),
            'kwargs': {'allversions': argd['--all']}
        },
    }
    funcmap['--purge'] = funcmap['--delete']
    funcmap['--LOCATE'] = funcmap['--locate']

    for opt in funcmap:
        if argd[opt]:
            return funcmap[opt]['func'](
                *funcmap[opt].get('args', []),
                **funcmap[opt].get('kwargs', {})
            )


def search_file(name, shortnamesonly=False):
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
        print('\nInvalid search term!: {}\n{}'.format(name, ex))
        return 1

    # Setup filename methods (long or short, removes an 'if' from the loop.)
    getfilenameshort = lambda s: os.path.split(s)[1]
    # Pick filename retrieval function..
    filenamefunc = getfilenameshort if shortnamesonly else (lambda s: s)

    # Iterate all packages...
    totalpkgs = 0
    totalfiles = 0

    for pkgname in cache_main.keys():
        pkg = cache_main[pkgname]
        matchingfiles = []
        if not get_install_state(pkg):
            continue
        if not hasattr(pkg, 'installed_files'):
            print(''.join(['\nUnable to retrieve installed files for ',
                           '{}'.format(pkgname),
                           ', apt/apt_pkg may be out of date!']))
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
            print('\n{}'.format(pkgname))
            print('    {}'.format('\n    '.join(matchingfiles)))

    print('\nFound {} files in {} packages.'.format(totalfiles, totalpkgs))
    return 0


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
        raise CacheNotLoaded('No apt cache to search.')

    try:
        re_pat = re.compile(
            regex,
            re.IGNORECASE if case_insensitive else 0)
    except re.error as ex:
        raise BadSearchQuery(str(ex))

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


def update(load_cache=False):
    """ update the cache,
        init or re-initialize the cache if load_cache is True
    """
    global cache_main
    if load_cache:
        cache_main = apt.Cache()

    try:
        cache_main.update(SimpleFetchProgress(msg='Updating...'))
        cache_main.open(progress=SimpleOpProgress(msg='Opening cache...'))
        print('Loaded ' + str(len(cache_main.keys())) + ' packages.')
    except KeyboardInterrupt:
        print('\nUser cancelled.\n')
    except apt.cache.FetchFailedException as exfail:
        print('\nFailed to complete download.\n{}'.format(exfail))
    except Exception as ex:
        print('\nError during update!:\n{0}\n'.format(ex))
    return True

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


class SimpleFetchProgress(apt.progress.text.TextProgress):

    """ Handles progress updates for Fetches """

    def __init__(self, msg=None):
        self.msg = msg if msg else 'Fetching'
        apt.progress.text.TextProgress.__init__(self)

    # existing pulse() function works pretty good, just leave it alone.
    def pulse(self, owner=None):
        if hasattr(apt.progress.text.TextProgress, 'pulse'):
            return apt.progress.text.TextProgress.pulse(self, owner)
        else:
            return True

    def start(self):
        print(self.msg)

    def stop(self):
        print('Finished ' + self.msg)

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

        print('\nError while installing: {}\n{}'.format(pkg.name, errormsg))

    def finish_update(self):
        """ Handles end of installation """

        if self.pkgname:
            print('\nFinished {}: {}'.format(self.msg.lower(), self.pkgname))


class IterCache(apt.Cache):

    """ Allows searching the package cache while loading. """

    def __init__(self, progress=None, rootdir=None,
                 memonly=False, do_open=True):
        self._cache = None
        self._depcache = None
        self._records = None
        self._list = None
        self._callbacks = {}
        self._weakref = weakref.WeakValueDictionary()
        self._set = set()
        self._fullnameset = set()
        self._changes_count = -1
        self._sorted_set = None

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


# Fatal Errors that when raised will end this script.
class BadSearchQuery(Exception):
    pass


class CacheNotLoaded(Exception):
    pass

# History package info.


class HistoryLine(object):

    """ Simple class to hold Apt History line info.
        The information comes from a single lin in dpkg.log.
        It can be parsed and then accessed through the attributes of this
        class. Such as: myhistoryline.name, myhl.version, myhl.action ..etc.

        Handles parsing and formatting: log-line -> object -> string.
        Handles package/state matching based on regex: self.matches('^install')
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
            errmsg = '\nError parsing history time: {}\n{}'
            print(errmsg.format(timestr, extime))
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
            elif statustype in ('configure', 'trigproc'):
                pkgnameraw = parts[3]
                pkgname, pkgarch = pkgnameraw.split(':')
                pkgver = parts[4]
            elif statustype in ('install', 'upgrade'):
                pkgnameraw = parts[3]
                pkgname, pkgarch = pkgnameraw.split(':')
                pkgfromver = parts[4] if (parts[4] != '<none>') else None
                pkgver = parts[5]
            else:
                # For debugging: These are usually 'startup' lines.
                # print('Invalid history line: {}'.format(line))
                return None
        except IndexError as exindex:
            print('\nError parsing history line: {}\n{}'.format(line, exindex))
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
            if repat.search(targetstr):
                return True
        return False

# custom progress reporters
oprogress = SimpleOpProgress()
fprogress = SimpleFetchProgress()

# Apply monkey patch.
apt.Cache.get = cache_get


# START ---------------------------------------------------
if __name__ == '__main__':
    main_argd = docopt(
        USAGESTR,
        version='{} v. {}'.format(NAME, __version__))
    # grab start time for timing.
    start_time = datetime.now()
    try:
        ret = main(main_argd)
    except KeyboardInterrupt:
        print('\nUser cancelled.\n')
        ret = 2
    # Report how long it took
    duration = (datetime.now() - start_time).total_seconds()
    print(str(duration)[:5] + 's')

    sys.exit(ret)
