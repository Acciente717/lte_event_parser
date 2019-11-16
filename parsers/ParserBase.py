### Copyright [2019] Zhiyao Ma
import sys

from abc import ABC, abstractmethod

class ParserBase(ABC):
    """ The base class for all event parsers. """

    def __init__(self, shared_states):
        """ Instantiate the ParserBase with a `shared_states` dictionary.

        The `shared_states` dictionary are accessed by several parsers.
        It is used by parsers to communicate between each other. For
        instance, if any parser detects the UE has reestablished a
        connection to eNB, it can set a value in the dictionary and
        inform other parsers.
        """
        self.shared_states = shared_states

    @abstractmethod
    def run(self, event):
        """ Feed the parser with a new event.

        `event` should be a 3-element tuple, in the form
        `(timestamp, packet_type, fields)`, where the `timestamp` shows
        the happening time of the event, `packet_type` reveals the type
        of the event, and `fields` is a dictionary storing properties of
        the event.
        """
        pass

    @abstractmethod
    def reset(self):
        """ Reset the states of the parser. """
        pass

    @staticmethod
    def eprint(*pargs, **kargs):
        print('\u001b[31m', end='', file=sys.stderr)
        print(*pargs, file=sys.stderr, **kargs)
        print('\u001b[0m', end='', file=sys.stderr)
