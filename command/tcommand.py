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

    def installReactor(self):
        """
        Override me to install your own reactor.
        """
        from twisted.internet import reactor
        self.reactor = reactor

    ### command.Command implementations
    def do(self, args):
        self.installReactor()

        def later():
            try:
                d = defer.maybeDeferred(self.doLater, args)
            except Exception:
                f = failure.Failure()
                self.warning('Exception during doLater: %r',
                    f.getErrorMessage())
                self.stderr.write('Exception: %s\n' % f.value)
                self.reactor.stop()
                raise

            d.addCallback(lambda _: self.reactor.stop())
            def eb(f):
                self.warning('errback: %r', f.getErrorMessage())
                self.stderr.write('Failure: %s\n' % f.value)

                self.reactor.stop()
            d.addErrback(eb)

        self.reactor.callLater(0, later)

        self.debug('running reactor')
        self.reactor.run()
        self.debug('ran reactor')

    ### command.TwistedCommand methods to implement by subclasses
    def doLater(self):
        """
        @rtype: L{defer.Deferred}
        """
        raise NotImplementedError
