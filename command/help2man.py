# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4

# Morituri - for those about to RIP

# Copyright (C) 2009 Thomas Vander Stichele

# This file is part of morituri.
#
# morituri is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# morituri is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with morituri.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import optparse
import tempfile
import pickle
import shutil
import StringIO

def walk(command, level=0):
    # print "%s%s: %s" % (" " * level, command.name, command.summary)
    for name, c in command.subCommands.items():
        walk(c, level + 2)

def manwalk(command):
    ret = []

    ret.append(".SH %s" % command.getFullName())
    # avoid printing the summary twice; once here and once in usage
    if command.summary and command.description:
        ret.append(command.summary)
        ret.append("")

    s = StringIO.StringIO()
    command.outputHelp(file=s)
    ret.append(s.getvalue())
    ret.append("")

    names = command.subCommands.keys()
    names.sort()
    for name in names:
        c = command.subCommands[name]
        ret.extend(manwalk(c))

    return ret

def main():
    # inspired by twisted.python.reflect.namedAny
    names = sys.argv[1].split('.')
    im = ".".join(names[:-1])
    top = __import__(im)
    obj = top
    for n in names[1:]:
        print obj
        print dir(obj)
        obj = getattr(obj, n)
    
    # ugly hack so that help output uses first argument for %prog instead of
    # 'doc.py'
    sys.argv[0] = sys.argv[2]


    man = []
    man.append('.TH "rip" "1" "October 2009"')
    man.extend(manwalk(obj(width=70)))

    print "\n".join(man)

main()
