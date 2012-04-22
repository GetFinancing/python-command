# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4

"""
A helper class for Twisted commands.
"""

from twisted.internet import defer

import command

# FIXME: move this to the command module
class TwistedCommand(command.Command):

    def installReactor(self):
        """
        Override me to install your own reactor.
        """
        from twisted.internet import reactor
        self.reactor = reactor

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

    def doLater(self):
        raise NotImplementedError
