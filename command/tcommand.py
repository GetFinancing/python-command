# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4

"""
A helper class for Twisted commands.
"""

from twisted.internet import defer

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
                self.reactor.stop()
                raise

            d.addCallback(lambda _: self.reactor.stop())
            def eb(failure):
                self.stderr.write('Failure: %s\n' % failure.getErrorMessage())

                self.reactor.stop()
            d.addErrback(eb)

        self.reactor.callLater(0, later)

        self.reactor.run()

    ### command.TwistedCommand methods to implement by subclasses
    def doLater(self):
        """
        @rtype: L{defer.Deferred}
        """
        raise NotImplementedError
