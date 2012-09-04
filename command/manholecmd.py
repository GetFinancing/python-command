# -*- test-case-name: twisted.conch.test.test_manhole -*-
# Copyright (c) 2001-2007 Twisted Matrix Laboratories.
# See LICENSE for details.

# taken from twisted.conch.manhole

"""
Line-input oriented interactive interpreter loop.

Provides classes for handling Python source input and arbitrary output
interactively from a Twisted application.  Also included is syntax coloring
code with support for VT102 terminals, control code handling (^C, ^D, ^Q),
and reasonable handling of Deferreds.

@author: Jp Calderone
"""

import os
import sys
import cmd
import code
import termios
import tty

from twisted.conch import recvline
from twisted.internet import stdio, defer

from twisted.conch.insults.insults import ServerProtocol


class FileWrapper:
    """Minimal write-file-like object.

    Writes are translated into addOutput calls on an object passed to
    __init__.  Newlines are also converted from network to local style.
    """

    softspace = 0
    state = 'normal'

    def __init__(self, o):
        self.o = o

    def flush(self):
        pass

    def write(self, data):
        self.o.addOutput(data.replace('\r\n', '\n'))

    def writelines(self, lines):
        self.write(''.join(lines))


# FIXME: not sure where this is from
class Interpreter(object):

    def __init__(self, handler, namespace=None):
        self.handler = handler

    def push(self, line):
        raise NotImplementedError

# FIXME: again from twisted.conch.manhole
class ManholeInterpreter(Interpreter, code.InteractiveInterpreter):
    """Interactive Interpreter with special output and Deferred support.

    Aside from the features provided by L{code.InteractiveInterpreter}, this
    class captures sys.stdout output and redirects it to the appropriate
    location (the Manhole protocol instance).  It also treats Deferreds
    which reach the top-level specially: each is formatted to the user with
    a unique identifier and a new callback and errback added to it, each of
    which will format the unique identifier and the result with which the
    Deferred fires and then pass it on to the next participant in the
    callback chain.
    """

    numDeferreds = 0
    buffer = None

    def __init__(self, handler, locals=None, filename="<console>"):
        Interpreter.__init__(self, handler)
        code.InteractiveInterpreter.__init__(self, locals)
        self._pendingDeferreds = {}
        self.filename = filename
        self.resetBuffer()

    ### code.InteractiveInterpreter methods

    def runcode(self, *a, **kw):
        orighook, sys.displayhook = sys.displayhook, self.displayhook
        try:
            origout, sys.stdout = sys.stdout, FileWrapper(self.handler)
            try:
                code.InteractiveInterpreter.runcode(self, *a, **kw)
            finally:
                sys.stdout = origout
        finally:
            sys.displayhook = orighook

    def write(self, data, async=False):
        self.handler.addOutput(data, async)

    ### Interpreter methods

    def resetBuffer(self):
        """Reset the input buffer."""
        self.buffer = []

    def push(self, line):
        """Push a line to the interpreter.

        The line should not have a trailing newline; it may have
        internal newlines.  The line is appended to a buffer and the
        interpreter's runsource() method is called with the
        concatenated contents of the buffer as source.  If this
        indicates that the command was executed or invalid, the buffer
        is reset; otherwise, the command is incomplete, and the buffer
        is left as it was after the line was appended.  The return
        value is 1 if more input is required, 0 if the line was dealt
        with in some way (this is the same as runsource()).

        """
        self.buffer.append(line)
        source = "\n".join(self.buffer)
        more = self.runsource(source, self.filename)
        if not more:
            self.resetBuffer()
        return more


    # FIXME: privatize

    def displayhook(self, obj):
        self.locals['_'] = obj
        if isinstance(obj, defer.Deferred):
            # XXX Ick, where is my "hasFired()" interface?
            if hasattr(obj, "result"):
                self.write(repr(obj))
            elif id(obj) in self._pendingDeferreds:
                self.write("<Deferred #%d>" % (
                    self._pendingDeferreds[id(obj)][0], ))
            else:
                d = self._pendingDeferreds
                k = self.numDeferreds
                d[id(obj)] = (k, obj)
                self.numDeferreds += 1
                obj.addCallbacks(
                    self._cbDisplayDeferred, self._ebDisplayDeferred,
                    callbackArgs=(k, obj), errbackArgs=(k, obj))
                self.write("<Deferred #%d>" % (k, ))
        elif obj is not None:
            self.write(repr(obj))

    def _cbDisplayDeferred(self, result, k, obj):
        self.write("Deferred #%d called back: %r" % (k, result), True)
        del self._pendingDeferreds[id(obj)]
        return result

    def _ebDisplayDeferred(self, failure, k, obj):
        self.write("Deferred #%d failed: %r" % (
            k, failure.getErrorMessage()), True)
        del self._pendingDeferreds[id(obj)]
        return failure

CTRL_C = '\x03'
CTRL_D = '\x04'
CTRL_BACKSLASH = '\x1c'
CTRL_L = '\x0c'


class Manhole(recvline.HistoricRecvLine):
    """Mediator between a fancy line source and an interactive interpreter.

    This accepts lines from its transport and passes them on to a
    L{ManholeInterpreter}.  Control commands (^C, ^D, ^\) are also handled
    with something approximating their normal terminal-mode behavior.  It
    can optionally be constructed with a dict which will be used as the
    local namespace for any code executed.
    """

    namespace = None
    interpreterClass = ManholeInterpreter

    def __init__(self, namespace=None):
        recvline.HistoricRecvLine.__init__(self)
        if namespace is not None:
            self.namespace = namespace.copy()

        self._setupInterpreter()

    def connectionMade(self):
        recvline.HistoricRecvLine.connectionMade(self)
        self.keyHandlers[CTRL_C] = self.handle_INT
        self.keyHandlers[CTRL_D] = self.handle_EOF
        self.keyHandlers[CTRL_L] = self.handle_FF
        self.keyHandlers[CTRL_BACKSLASH] = self.handle_QUIT

    # FIXME: this was in connectionMade, but why ?
    # Doing it earlier allows us to set prompts from the interpreter

    def _setupInterpreter(self):
        self.interpreter = self.interpreterClass(self, self.namespace)

    def handle_INT(self):
        """
        Handle ^C as an interrupt keystroke by resetting the current input
        variables to their initial state.
        """
        self.pn = 0
        self.lineBuffer = []
        self.lineBufferIndex = 0
        self.interpreter.resetBuffer()

        self.terminal.nextLine()
        self.terminal.write("KeyboardInterrupt")
        self.terminal.nextLine()
        self.terminal.write(self.ps[self.pn])

    def handle_EOF(self):
        if self.lineBuffer:
            self.terminal.write('\a')
        else:
            self.handle_QUIT()

    def handle_FF(self):
        """
        Handle a 'form feed' byte - generally used to request a screen
        refresh/redraw.
        """
        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.drawInputLine()

    def handle_QUIT(self):
        self.terminal.loseConnection()

    def _needsNewline(self):
        w = self.terminal.lastWrite
        return not w.endswith('\n') and not w.endswith('\x1bE')

    def addOutput(self, bytes, async=False):
        if async:
            self.terminal.eraseLine()
            self.terminal.cursorBackward(
                len(self.lineBuffer) + len(self.ps[self.pn]))

        self.terminal.write(bytes)

        if async:
            if self._needsNewline():
                self.terminal.nextLine()

            self.terminal.write(self.ps[self.pn])

            if self.lineBuffer:
                oldBuffer = self.lineBuffer
                self.lineBuffer = []
                self.lineBufferIndex = 0

                self._deliverBuffer(oldBuffer)

    def lineReceived(self, line):
        d = defer.maybeDeferred(self.interpreter.push, line)

        def cb(more):
            self.pn = bool(more)
            if self._needsNewline():
                self.terminal.nextLine()
            self.terminal.write(self.ps[self.pn])
        d.addCallback(cb)
        return d

### this is our code

# gets instantiated when the first command is entered and passed

class CmdInterpreter(Interpreter):
    cmdClass = None # subclasses should set this

    _cmd = None

    def __init__(self, handler, localss=None):
        Interpreter.__init__(self, handler, localss)
        # this instantiation is so we can get the prompt; but we don't
        # have self.handler.terminal yet
        self._cmd = self.cmdClass()
        self.handler.ps = (self._cmd.prompt, '... ')

    # FIXME: integrate into Twisted

    def push(self, line):
        """
        This version of push returns a deferred that will fire when the command
        is done and the interpreter can show the next prompt.
        """

        assert type(line) is not unicode
        # now we have self.handler.terminal
        self._cmd = self.cmdClass(stdout=self.handler.terminal)
        # set stdout on the root command too
        # FIXME: pokes in internals
        if hasattr(self._cmd, 'command'):
            self._cmd.command.getRootCommand()._stdout = self.handler.terminal
        r = self._cmd.onecmd(line)

        # push should only return something if it wants a more prompt
        # return r

    # called by handle_INT
    def resetBuffer(self):
        pass


class CmdManhole(Manhole):

    interpreterClass = CmdInterpreter

    def __init__(self, namespace=None, connectionLostDeferred=None):
        """
        @param connectionLostDeferred: a deferred that will be fired when
                                       the connection is lost, with the reason.
        """
        Manhole.__init__(self, namespace)

        self.connectionLostDeferred = connectionLostDeferred

    def connectionLost(self, reason):
        """
        When the connection is lost, there is nothing more to do.  Stop the
        reactor so that the process can exit.

        Override me for custom behaviour.
        """
        if not self.connectionLostDeferred:
            # FIXME: should we really be handling the reactor here?
            from twisted.internet import reactor

            reactor.stop()
        else:
            self.connectionLostDeferred.callback(reason)

# we do not want loseConnection to self.reset() and clear the screen


class CmdServerProtocol(ServerProtocol):

    def loseConnection(self):
        self.transport.loseConnection()


class Stdio(object):
    _fd = None

    def setup(self):
        self._fd = sys.__stdin__.fileno()
        self._oldSettings = termios.tcgetattr(self._fd)
        self.setraw()

    def setraw(self):
        # We want to use our special command line handling
        tty.setraw(self._fd)

        # The implementation of tty.setraw strips OPOST, disabling output
        # processing, and so \n does not return to carriage.
        # Turn it back on similarly to tty.setraw
        mode = termios.tcgetattr(self._fd)
        mode[tty.OFLAG] = mode[tty.OFLAG] | termios.OPOST
        termios.tcsetattr(self._fd, termios.TCSANOW, mode)

    def getPassword(self, prompt=None):
        if self._fd is not None:
            # go to cbreak mode, where interrupts are handled
            tty.setcbreak(self._fd)
            # reset terminal, so that we can actually get the newline that
            # terminates entering the password
            termios.tcsetattr(self._fd, termios.TCSANOW, self._oldSettings)

        from twisted.python import util
        password = util.getPassword(prompt=prompt)

        if self._fd is not None:
            self.setraw()

        return password

    def connect(self, klass, *args, **kwargs):

        p = CmdServerProtocol(klass, *args, **kwargs)
        stdio.StandardIO(p)

    def teardown(self):
        os.system('stty sane')
        # we did not actually carriage return the ended prompt
        print
        termios.tcsetattr(self._fd, termios.TCSANOW, self._oldSettings)
        # this clears the screen,
        # but also fixes some problem when editing history lines
        # ESC c resets terminal
        #os.write(self._fd, "\r\x1bc\r")


def runWithProtocol(klass, *args, **kwargs):
    s = Stdio()

    s.setup()
    try:
        s.connect(klass, *args, **kwargs)

        from twisted.internet import reactor
        reactor.run()
    finally:
        s.teardown()


# example code, showing how to create your own interpreter and manhole
if __name__ == '__main__':
    # classes defined in if to not pollute module namespace

    class MyCmd(cmd.Cmd):

        prompt = 'My Command Prompt >>> '

        def do_test(self, args):
            self.stdout.write('this is a test\n')

        def do_defer(self, args):
            self.stdout.write('this is a test that returns a deferred\n')

            from twisted.internet import defer
            d = defer.Deferred()

            def cb(_):
                self.stdout.write('the deferred fired\n')
            d.addCallback(cb)

            from twisted.internet import reactor
            reactor.callLater(1, d.callback, None)

            return d

        def do_errback(self, args):
            self.stdout.write('this is a test that errbacks\n')

            from twisted.internet import defer
            d = defer.Deferred()

            d.errback(KeyError)
            return d


    class MyCmdInterpreter(CmdInterpreter):
        cmdClass = MyCmd

    class MyManhole(CmdManhole):
        interpreterClass = MyCmdInterpreter


    runWithProtocol(MyManhole)
