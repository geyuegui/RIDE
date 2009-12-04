#!/usr/bin/env python

# Copyright 2008-2009 Nokia Siemens Networks Oyj
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Packaging script for RIDE

Usage:  package.py command version_number [release_tag]

Argument 'command' can have one of the following values:
  - sdist    : create source distribution
  - wininst  : create Windows installer
  - all      : create both packages
  - version  : update only version information in 'src/robot/version.py'

'version_number' must be a version number in format 'x.y(.z)', 'trunk' or
'keep'. With 'keep', version information is not updated.

'release_tag' must be either 'alpha', 'beta', 'rc' or 'final', where all but
the last one can have a number after the name like 'alpha1' or 'rc2'. When
'version_number' is 'trunk', 'release_tag' is automatically assigned to the
current date.

This script uses 'setup.py' internally. Distribution packages are created
under 'dist' directory, which is deleted initially. Depending on your system,
you may need to run this script with administrative rights (e.g. with 'sudo').

Examples:
  package.py sdist 0.17 final
  package.py wininst keep
  package.py all 0.19 alpha
  package.py sdist trunk
  package.py version trunk
"""

import sys
import os
import shutil
import re
import time
import csv
from urllib2 import urlopen
from string import Template
from StringIO import StringIO

from robot.utils import HtmlWriter, html_escape


ROOT_PATH = os.path.dirname(__file__)
DIST_PATH = os.path.join(ROOT_PATH, 'dist')
BUILD_PATH = os.path.join(ROOT_PATH, 'build')
RIDE_PATH = os.path.join(ROOT_PATH, 'src', 'robotide')
SETUP_PATH = os.path.join(ROOT_PATH, 'setup.py')
VERSION_PATH = os.path.join(RIDE_PATH, 'version.py')
VERSIONS = [re.compile('^\d+\.\d+(\.\d+)?$'), 'trunk', 'keep']
RELEASES = [re.compile('^alpha\d*$'), re.compile('^beta\d*$'),
            re.compile('^rc\d*$'), 'final']
VERSION_CONTENT = """# Automatically generated by 'package.py' script.

VERSION = '%(version_number)s'
RELEASE = '%(release_tag)s'
TIMESTAMP = '%(timestamp)s'

def get_version(sep=' '):
    if RELEASE == 'final':
        return VERSION
    return VERSION + sep + RELEASE

if __name__ == '__main__':
    import sys
    print get_version(*sys.argv[1:])
"""

def sdist(*version_info):
    version(*version_info)
    _clean()
    _create_sdist()
    _announce()

def wininst(*version_info):
    version(*version_info)
    _clean()
    if _verify_platform(*version_info):
        _create_wininst()
        _announce()

def all(*version_info):
    version(*version_info)
    _clean()
    _create_sdist()
    if _verify_platform(*version_info):
        _create_wininst()
    _announce()

def version(version_number, release_tag=None):
    _verify_version(version_number, VERSIONS)
    if version_number == 'keep':
        _keep_version()
    elif version_number =='trunk':
        _update_version(version_number, '%d%02d%02d' % time.localtime()[:3])
        _update_release_notes_plugin("")
    else:
        _update_version(version_number, _verify_version(release_tag, RELEASES))
        _create_release_notes(version_number)

def _verify_version(given, valid):
    for item in valid:
        if given == item or (hasattr(item, 'search') and item.search(given)):
            return given
    raise ValueError

def _update_version(version_number, release_tag):
    timestamp = '%d%02d%02d-%02d%02d%02d' % time.localtime()[:6]
    vfile = open(VERSION_PATH, 'w')
    vfile.write(VERSION_CONTENT % locals())
    vfile.close()
    print 'Updated version to %s %s' % (version_number, release_tag)

def _keep_version():
    sys.path.insert(0, RIDE_PATH)
    from version import get_version
    print 'Keeping version %s' % get_version()

def _create_release_notes(version):
    changes = _download_and_format_issues(version)
    _update_release_notes_plugin(changes)

def _download_and_format_issues(version):
    URL = Template('http://code.google.com/p/robotframework-ride/issues/csv?'
                   'sort=priority+type&colspec=ID%20Type%20Priority%20Summary'
                   '&q=target%3A${version}&can=1')
    reader = csv.reader(urlopen(URL.substitute(locals())))
    total_issues = 0
    writer = HtmlWriter(StringIO())
    writer.element('h2', 'Release notes for %s' % version)
    writer.start('table', attrs={'border': '1'})
    for row in reader:
        if not row or row[1] == 'Task':
            continue
        writer.start('tr')
        if reader.line_num == 1:
            row = [ '*%s*' % cell for cell in row ]
        else:
            row[0] = '<a href="http://code.google.com/p/robotframework-ride/'\
                     'issues/detail?id=%s">Issue %s</a>' % (row[0], row[0])
            total_issues += 1
        for cell in row:
            if reader.line_num == 1:
                cell = html_escape(cell, formatting=True)
            writer.element('td', cell, escape=False)
        writer.end('tr')
    writer.end('table')
    writer.element('p', 'Altogether %d issues.' % total_issues)
    return writer.output.getvalue()

def _update_release_notes_plugin(changes):
    plugin_path = os.path.join(RIDE_PATH, 'application', 'releasenotes.py')
    content = open(plugin_path).read().rsplit('RELEASE_NOTES =', 1)[0]
    content += 'RELEASE_NOTES = """\n%s"""\n' % changes
    open(plugin_path, 'w').write(content)

def _clean():
    print 'Cleaning up...'
    for path in [DIST_PATH, BUILD_PATH]:
        if os.path.exists(path):
            shutil.rmtree(path)

def _verify_platform(version_number, release_tag=None):
    if release_tag == 'final' and os.sep != '\\':
        print 'Final Windows installers can only be created in Windows.'
        print 'Windows installer was not created.'
        return False
    return True

def _create_sdist():
    _create('sdist', 'source distribution')

def _create_wininst():
    _create('bdist_wininst', 'Windows installer')
    if os.sep != '\\':
        print 'Warning: Windows installers created on other platforms may not'
        print 'be exactly identical to ones created in Windows.'

def _create(command, name):
    print 'Creating %s...' % name
    rc = os.system('%s %s %s' % (sys.executable, SETUP_PATH, command))
    if rc != 0:
        print 'Creating %s failed.' % name
        sys.exit(rc)
    print '%s created successfully.' % name.capitalize()

def _announce():
    print 'Created:'
    for path in os.listdir(DIST_PATH):
        print os.path.abspath(os.path.join(DIST_PATH, path))


if __name__ == '__main__':
    try:
        globals()[sys.argv[1]](*sys.argv[2:])
    except (KeyError, IndexError, TypeError, ValueError):
        print __doc__
