# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4

"""
A helper class for Twisted commands.
"""

from twisted.internet import defer
from twisted.python import failure

import command

class TwistedCommand(command.Command):
    """
    I am a Command that integrates with Twisted and its reactor.

    Instead of implementing the do() method, subclasses should implement a
    doLater() method which returns a deferred.
    """

    def installReactor(self, reactor=None):
        """
        Override me to install your own reactor in the parent
        ReactorCommand.
        """
        self.debug('installing reactor %r in ancestor ReactorCommand',
            reactor)
        c = self
        while c.parentCommand and not isinstance(c, ReactorCommand):
            c = c.parentCommand

        if not c:
            raise AssertionError(
                '%r does not have a parent ReactorCommand' % self)

        self.debug('installing reactor %r in ancestor ReactorCommand %r',
            reactor, c)

        c.installReactor(reactor)

    ### command.Command implementations
    def do(self, args):
        self.debug('%r: installing reactor using method %r', self,
            self.installReactor)
        self.installReactor()

        d = self.doLater(args)
        if isinstance(d, defer.Deferred):
            self.debug('doLater returns a deferred, install reactor')

        return d

    ### command.TwistedCommand methods to implement by subclasses
    def doLater(self):
        """
        @rtype: L{defer.Deferred}
        """
        raise NotImplementedError


class ReactorCommand(command.Command):
    """
    I am a Command that runs a reactor for its subcommands if they
    return a L{defer.Deferred} from their doLater() method.
    """

    reactor = None
    returnValue = None

    def installReactor(self, reactor=None):
        """
        Override me to install your own reactor.
        """
        self.debug('ReactorCommand: installing reactor %r', reactor)
        if not reactor:
            from twisted.internet import reactor

        self.reactor = reactor

    ### command.Command overrides

    def parse(self, argv):
        """
        @returns: a deferred that will fire when the command is parsed and
                  executed.
        """
        self.debug('parse: chain up')
        try:
            r = command.Command.parse(self, argv)
        except Exception:
            f = failure.Failure()
            self.warning('Exception during %r.parse: %r\n%s\n',
                self, f.getErrorMessage(), f.getTraceback())
            self.stderr.write('Exception: %s\n' % f.value)
            raise

        self.debug('parse: result %r', r)

        if not isinstance(r, defer.Deferred):
            return r

        # We have a deferred, so we need to run a reactor
        d = r

        # child commands could have installed a reactor
        if not self.reactor:
            self.installReactor()

        def parseCb(ret):
            if ret is None:
                self.debug('parse returned None, defaults to exit code 0')
                ret = 0
            elif ret:
                self.debug('parse returned %r' % ret)
            elif self.parser.help_printed or self.parser.usage_printed:
                ret = 0
            self.debug('parse: cb: done')
            self.returnValue = ret
            self.reactor.stop()
            return ret

        def eb(failure):
            self.debug('parse: eb: failure %s' %
                failure.getErrorMessage())
            self.reactor.stop()
            if failure.check(command.CommandExited):
                self.stderr.write(failure.value.msg + '\n')
                reason = failure.value.code
                self.returnValue = reason
                return reason
            else:
                self.warning('errback: %r', failure.getErrorMessage())
                self.stderr.write('Failure: %s\n' % failure.value)
                self.returnValue = failure
                return failure

        d.addCallback(parseCb)
        d.addErrback(eb)

        self.debug('running reactor %r', self.reactor)
        self.reactor.run()
        self.debug('ran reactor, returning %r' % self.returnValue)

        return self.returnValue
