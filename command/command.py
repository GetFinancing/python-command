# -*- Mode: Python; test-case-name: test_command -*-
# vi:si:et:sw=4:sts=4:ts=4

# This file is released under the standard PSF license.

"""
Command class.
"""

import optparse
import sys


class CommandHelpFormatter(optparse.IndentedHelpFormatter):
    """
    I format the description as usual, but add an overview of commands
    after it if there are any, formatted like the options.
    """

    _commands = None
    _aliases = None
    _klass = None

    def addCommand(self, name, description):
        if self._commands is None:
            self._commands = {}
        self._commands[name] = description

    def addAlias(self, alias):
        if self._aliases is None:
            self._aliases = []
        self._aliases.append(alias)

    def setClass(self, klass):
        self._klass = klass

    def getCommands(self):
        ret = ""

        if self._commands:
            commandDesc = []
            commandDesc.append("Commands:")
            keys = self._commands.keys()
            keys.sort()
            length = 0
            for key in keys:
                if len(key) > length:
                    length = len(key)
            for name in keys:
                formatString = "  %-" + "%d" % length + "s  %s"
                commandDesc.append(formatString % (name, self._commands[name]))
            ret += "\n" + "\n".join(commandDesc) + "\n"

        return ret


    ### override parent method

    def format_description(self, description, width=None):
        # textwrap doesn't allow for a way to preserve double newlines
        # to separate paragraphs, so we do it here.
        paragraphs = description.split('\n\n')
        rets = []

        for paragraph in paragraphs:
            # newlines starting with a space/dash are treated as a table, ie as
            # is
            lines = paragraph.split('\n -')
            formatted = []
            for line in lines:
                formatted.append(
                    optparse.IndentedHelpFormatter.format_description(
                        self, line))
            rets.append(" -".join(formatted))

        ret = "\n".join(rets)

        # add aliases
        if self._aliases:
            ret += "\nAliases: " + ", ".join(self._aliases) + "\n"

        # add subcommands
        ret += self.getCommands()

        # add class info
        ret += "\nImplemented by: %s.%s\n" % (
            self._klass.__module__, self._klass.__name__)

        return ret


class CommandOptionParser(optparse.OptionParser):
    """
    I parse options as usual, but I explicitly allow setting stdout
    so that our print_help() method (invoked by default with -h/--help)
    defaults to writing there.

    I also override exit() so that I can be used in interactive shells.

    @ivar help_printed:  whether help was printed during parsing
    @ivar usage_printed: whether usage was printed during parsing
    """
    help_printed = False
    usage_printed = False

    _stdout = sys.stdout
    _stderr = sys.stderr

    def set_stdout(self, stdout):
        self._stdout = stdout

    def set_stderr(self, stderr):
        self._stderr = stderr

    def parse_args(self, args=None, values=None):
        self.help_printed = False
        self.usage_printed = False
        try:
            return optparse.OptionParser.parse_args(self, args, values)
        except UnboundLocalError:
            raise
            # this can happen when an option is used that requires a
            # value but none is specified
            raise CommandError("Missing argument to option")

    # we're overriding the built-in file, but we need to since this is
    # the signature from the base class
    __pychecker__ = 'no-shadowbuiltin'

    def print_commands(self, file=None):
        if file is None:
            file = self._stdout
        file.write(self.formatter.getCommands())

    def print_help(self, file=None):
        # we are overriding a parent method so we can't do anything about file
        __pychecker__ = 'no-shadowbuiltin'
        if file is None:
            file = self._stdout
        file.write(self.format_help())
        self.help_printed = True

    def print_usage(self, file=None):
        optparse.OptionParser.print_usage(self, file)
        self.usage_printed = True

    def exit(self, status=0, msg=None):
        if msg:
            self._stderr.write(msg)

        return status

    # since we override exit not to exit, we need to override error to do
    def error(self, msg):
        self.print_usage(self._stderr)
        raise CommandError(msg)

class Command(object):
    """
    I am a class that handles a command for a program.
    Commands can be nested underneath a command for further processing.

    @cvar name:        name of the command, lowercase;
                       defaults to the lowercase version of the class name
    @cvar aliases:     list of alternative lowercase names recognized
    @type aliases:     list of str
    @cvar usage:       short one-line usage string;
                       %command gets expanded to a sub-command or [commands]
                       as appropriate.  Don't specify the command name itself,
                       it will be added automatically.  If not set, defaults
                       to name.
    @cvar summary:     short one-line summary of the command
    @cvar description: longer paragraph explaining the command
    @cvar subCommands: dict of name -> commands below this command
    @type subCommands: dict of str  -> L{Command}
    @cvar parser:      the option parser used for parsing
    @type parser:      L{optparse.OptionParser}
    """
    name = None
    aliases = None
    usage = None
    summary = None
    description = None
    parentCommand = None
    subCommands = None
    subCommandClasses = None
    aliasedSubCommands = None
    parser = None

    def __init__(self, parentCommand=None, stdout=None,
        stderr=None, width=None):
        """
        Create a new command instance, with the given parent.
        Allows for redirecting stdout and stderr if needed.
        This redirection will be passed on to child commands.
        """
        if not self.name:
            self.name = self.__class__.__name__.lower()
        self._stdout = stdout
        self._stderr = stderr
        self.parentCommand = parentCommand

        # create subcommands if we have them
        self.subCommands = {}
        self.aliasedSubCommands = {}
        if self.subCommandClasses:
            for C in self.subCommandClasses:
                c = C(self, stdout=stdout, stderr=stderr, width=width)
                self.subCommands[c.name] = c
                if c.aliases:
                    for alias in c.aliases:
                        self.aliasedSubCommands[alias] = c

        # create our formatter and add subcommands if we have them
        formatter = CommandHelpFormatter(width=width)
        formatter.setClass(self.__class__)
        if self.subCommands:
            if not self.description:
                if self.summary:
                    self.description = self.summary
                else:
                    raise AttributeError, \
                        "%r needs a summary or description " \
                        "for help formatting" % self

            for name, command in self.subCommands.items():
                formatter.addCommand(name, command.summary or
                    command.description or '')

        if self.aliases:
            for alias in self.aliases:
                formatter.addAlias(alias)

        # expand %command for the bottom usage
        usage = self.usage or ''
        if not usage:
            # if no usage, but subcommands, then default to showing that
            if self.subCommands:
                usage = "%command"

        # the main program name shouldn't get prepended, because %prog
        # already expands to the name
        if not usage.startswith('%prog'):
            usage = self.name + ' ' + usage

        usages = [usage, ]
        if usage.find("%command") > -1:
            if self.subCommands:
                usage = usage.split("%command")[0] + '[command]'
                usages = [usage, ]
            else:
                # %command used in a leaf command
                usages = usage.split("%command")
                usages.reverse()

        # FIXME: abstract this into getUsage that takes an optional
        # parentCommand on where to stop recursing up
        # useful for implementing subshells

        # walk the tree up for our usage
        c = self.parentCommand
        while c:
            usage = c.usage or c.name
            if usage.find(" %command") > -1:
                usage = usage.split(" %command")[0]
            usages.append(usage)
            c = c.parentCommand
        usages.reverse()
        usage = " ".join(usages)

        # create our parser
        description = self.description or self.summary
        if description:
            description = description.strip()
        self.parser = CommandOptionParser(
            usage=usage, description=description,
            formatter=formatter)
        self.parser.set_stdout(self.stdout)
        self.parser.set_stderr(self.stderr)
        self.parser.disable_interspersed_args()

        # allow subclasses to add options
        self.addOptions()

    def addOptions(self):
        """
        Override me to add options to the parser.
        """
        pass

    def do(self, args):
        """
        Override me to implement the functionality of the command.

        @rtype:   int
        @returns: an exit code, or None if no actual action was taken.
        """
        raise NotImplementedError('Implement %s.do()' % self.__class__)
        # by default, return 1 and hopefully show help
        return 1

    def parse(self, argv):
        """
        Parse the given arguments and act on them.

        @param argv: list of arguments to parse
        @type  argv: list of unicode

        @rtype:   int
        @returns: an exit code, or None if no actual action was taken.
        """
        # note: no arguments should be passed as an empty list, not a list
        # with an empty str as ''.split(' ') returns
        self.debug('calling %r.parse_args(%r)' % (self, argv))
        self.options, args = self.parser.parse_args(argv)
        self.debug('called %r.parse_args' % self)

        # if we were asked to print help or usage, we are done
        if self.parser.usage_printed or self.parser.help_printed:
            return None

        # FIXME: make handleOptions not take options, since we store it
        # in self.options now
        self.debug('calling %r.handleOptions(%r)' % (self, self.options))
        ret = self.handleOptions(self.options)
        self.debug('called %r.handleOptions, returned %r' % (self, ret))
        if ret:
            return ret

        # handle pleas for help
        if args and args[0] == 'help':
            self.debug('Asked for help, args %r' % args)

            # give help on current command if only 'help' is passed
            if len(args) == 1:
                # start on a newline for the case where we're in the
                # interpreter
                self.stdout.write('\n')
                self.outputHelp()
                return 0

            # complain if we were asked for help on a subcommand, but we don't
            # have any
            if not self.subCommands:
                self.stderr.write('No subcommands defined.\n')
                self.parser.print_usage(file=self.stderr)
                self.stderr.write(
                    "Use --help to get more information about this command.\n")
                return 1

            # rewrite the args the other way around;
            # help doap becomes doap help so it gets deferred to the doap
            # command
            args = [args[1], args[0]]

        # if we don't have args or don't have subcommands,
        # defer to our do() method
        # allows implementing a do() for commands that also have subcommands
        if not args or not self.subCommands:
            self.debug('no args or no subcommands, calling %r.do(%r)' % (
                self, args))
            try:
                ret = self.do(args)
                self.debug('done ok, returned %r', ret)
            except CommandOk, e:
                self.debug('done with exception, raised %r', e)
                ret = e.status
                if e.output is not None:
                    self.stdout.write(e.output + '\n')
            except CommandExited, e:
                self.debug('done with exception, raised %r', e)
                ret = e.status
                if e.output is not None:
                    self.stderr.write(e.output + '\n')
            except NotImplementedError:
                self.debug('done with NotImplementedError')
                self.parser.print_usage(file=self.stderr)
                self.stderr.write(
                    "Use --help to get a list of commands.\n")
                ret = 1


            # if everything's fine, we return 0
            if not ret:
                ret = 0

            return ret

        # if we do have subcommands, defer to them
        try:
            command = args[0]
        except IndexError:
            self.parser.print_usage(file=self.stderr)
            self.stderr.write(
                "Use --help to get a list of commands.\n")
            return 1

        # FIXME: check users and enable this
        # assert type(command) is unicode
        if command in self.subCommands.keys():
            return self.subCommands[command].parse(args[1:])

        if self.aliasedSubCommands:
            if command in self.aliasedSubCommands.keys():
                return self.aliasedSubCommands[command].parse(args[1:])

        if not command:
            self.stderr.write("Please specify a subcommand.\n")
        else:
            self.stderr.write("Unknown command '%s'.\n"
                % command.encode('utf-8'))
            self.parser.print_commands(file=self.stderr)
        return 1

    def handleOptions(self, options):
        """
        Handle the parsed options.
        """
        pass

    def outputHelp(self, file=None):
        """
        Output help information.
        """
        __pychecker__ = 'no-shadowbuiltin'
        self.debug('outputHelp')
        if not file:
            file = self.stderr
        self.parser.print_help(file=file)

    def outputUsage(self, file=None):
        """
        Output usage information.
        Used when the options or arguments were missing or wrong.
        """
        __pychecker__ = 'no-shadowbuiltin'
        self.debug('outputUsage')
        if not file:
            file = self.stderr
        self.parser.print_usage(file=file)

    def getRootCommand(self):
        """
        Return the top-level command, which is typically the program.
        """
        c = self
        while c.parentCommand:
            c = c.parentCommand
        return c

    def warning(self, format, *args):
        """
        Override me to handle warning output from this class.
        """
        pass

    def info(self, format, *args):
        """
        Override me to handle info output from this class.
        """
        pass


    def debug(self, format, *args):
        """
        Override me to handle debug output from this class.
        """
        pass

    def getFullName(self):
        names = []
        c = self
        while c:
            names.append(c.name)
            c = c.parentCommand
        names.reverse()
        return " ".join(names)

    def _getStd(self, what):

        ret = getattr(self, '_' + what, None)
        if ret:
            return ret

        # if I am the root command, default
        if not self.parentCommand:
            return getattr(sys, what)

        # otherwise delegate to my parent
        return getattr(self.parentCommand, what)

    def _getStdOut(self):
        return self._getStd('stdout')

    def _getStdErr(self):
        return self._getStd('stderr')

    stdout = property(_getStdOut)
    stderr = property(_getStdErr)


class CommandExited(Exception):

    def __init__(self, status, output=None):
        self.args = (status, output)
        self.status = status
        self.output = output


class CommandOk(CommandExited):

    def __init__(self, output=None):
        CommandExited.__init__(self, 0, output)


class CommandError(CommandExited):

    def __init__(self, output=None):
        CommandExited.__init__(self, 3, output)


def commandToCmdClass(command):
    """
    @type  command: L{Command}

    Take a Command instance and create a L{cmd.Cmd} class from it that
    implements a command line interpreter, using the commands under the given
    Command instance as its subcommands.

    Example use in a command:

    >>> def do(self, args):
    ...     cmd = command.commandToCmdClass(self)()
    ...     cmd.prompt = 'prompt> '
    ...     while not cmd.exited:
    ...         cmd.cmdloop()

    @rtype: L{cmd.Cmd}
    """
    import cmd

    # internal class to subclass cmd.Cmd with a Ctrl-D handler

    class _CommandWrappingCmd(cmd.Cmd):
        prompt = '(command) '
        exited = False
        command = None # the original Command subclass

        def __repr__(self):
            return "<_CommandWrappingCmd for Command %r>" % self.command

        def do_EOF(self, args):
            self.stdout.write('\n')
            self.exited = True
            sys.exit(0)

        def do_exit(self, args):
            self.exited = True
            sys.exit(0)

        def help_EOF(self):
            print 'Exit.'

        def help_exit(self):
            print 'Exit.'

    # populate the Cmd interpreter from our command class
    cmdClass = _CommandWrappingCmd
    cmdClass.command = command

    for name, subCommand in command.subCommands.items() \
        + command.aliasedSubCommands.items():
        if name == 'shell':
            continue
        command.debug('Adding shell command %s for %r' % (name, subCommand))

        # add do command
        methodName = 'do_' + name

        def generateDo(c):

            def do_(s, line):
                # line is coming from a terminal; usually it is a utf-8 encoded
                # string.
                # Instead of making every Command subclass implement do with
                # unicode decoding, we do it here.
                line = line.decode('utf-8')
                # the do_ method is passed a single argument consisting of
                # the remainder of the line
                args = line.split(' ')
                command.debug('Asking %r to parse %r' % (c, args))
                return c.parse(args)
            return do_

        method = generateDo(subCommand)
        setattr(cmdClass, methodName, method)


        # add help command
        methodName = 'help_' + name

        def generateHelp(c):

            def help_(s):
                # add a newline because we're still at the end of the help
                # command on the prompt
                c.debug('Getting help for %r', s)
                s.stdout.write('\n')
                c.parser.print_help(file=s.stdout)
            return help_

        method = generateHelp(subCommand)
        command.debug('Adding method %r with name %r to %r' % (
            method, methodName, cmdClass))
        setattr(cmdClass, methodName, method)

    return cmdClass


def commandToCmd(command):
    # for compatibility reasons
    return commandToCmdClass(command)()
