from six import add_metaclass

from spinn_utilities.abstract_base import AbstractBase
from spinn_utilities.abstract_base import abstractproperty
from spinn_utilities.abstract_base import abstractmethod


@add_metaclass(AbstractBase)
class SimulatorInterface(object):

    __slots__ = ()

    @abstractmethod
    def add_socket_address(self, x):
        pass

    @abstractproperty
    def buffer_manager(self):
        pass

    @abstractproperty
    def config(self):
        pass

    @abstractproperty
    def graph_mapper(self):
        pass

    @abstractproperty
    def graph_mapper(self):
        pass

    @abstractproperty
    def has_ran(self):
        pass

    @abstractproperty
    def has_ran(self):
        pass

    @abstractproperty
    def increment_none_labelled_vertex_count(self):
        pass

    @abstractproperty
    def machine_time_step(self):
        pass

    @abstractproperty
    def placements(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractproperty
    def transceiver(self):
        pass


