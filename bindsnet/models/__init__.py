import torch
import numpy as np

from typing import Optional, Union, Tuple

from ..network import Network
from ..learning import PostPre
from ..network.topology import Connection, LocallyConnectedConnection, MeanFieldConnection
from ..network.nodes import Input, RealInput, LIFNodes, DiehlAndCookNodes, IzhikevichNodes


class TwoLayerNetwork(Network):
    # language=rst
    """
    Implements an ``Input`` instance connected to a ``LIFNodes`` instance with a fully-connected ``Connection``.
    """
    def __init__(self, n_inpt: int, n_neurons: int = 100, dt: float = 1.0, nu_pre: float = 1e-4, nu_post: float = 1e-2,
                 wmin: float = 0.0, wmax: float = 1.0, norm: float = 78.4) -> None:
        # language=rst
        """
        Constructor for class ``TwoLayerNetwork``.

        :param n_inpt: Number of input neurons. Matches the 1D size of the input data.
        :param n_neurons: Number of neurons in the ``LIFNodes`` population.
        :param dt: Simulation time step.
        :param nu_pre: Pre-synaptic learning rate.
        :param nu_post: Post-synaptic learning rate.
        :param wmin: Minimum allowed weight on ``Input`` to ``LIFNodes`` synapses.
        :param wmax: Maximum allowed weight on ``Input`` to ``LIFNodes`` synapses.
        :param norm: ``Input`` to ``LIFNodes`` layer connection weights normalization constant.
        """
        super().__init__(dt=dt)
        
        self.n_inpt = n_inpt
        self.n_neurons = n_neurons
        self.dt = dt
        
        self.add_layer(Input(n=self.n_inpt, traces=True, trace_tc=5e-2), name='X')
        self.add_layer(LIFNodes(n=self.n_neurons, traces=True, rest=-65.0, reset=-65.0, thresh=-52.0, refrac=5,
                                decay=1e-2, trace_tc=5e-2), name='Y')

        w = 0.3 * torch.rand(self.n_inpt, self.n_neurons)
        self.add_connection(Connection(source=self.layers['X'], target=self.layers['Y'], w=w, update_rule=PostPre,
                                       nu=(nu_pre, nu_post), wmin=wmin, wmax=wmax, norm=norm),
                            source='X', target='Y')
        

class DiehlAndCook2015(Network):
    # language=rst
    """
    Implements the spiking neural network architecture from `(Diehl & Cook 2015)
    <https://www.frontiersin.org/articles/10.3389/fncom.2015.00099/full>`_.
    """
    def __init__(self, n_inpt: int, n_neurons: int = 100, exc: float = 22.5, inh: float = 17.5, dt: float = 1.0,
                 nu_pre: float = 1e-4, nu_post: float = 1e-2, wmin: float = 0.0, wmax: float = 1.0, norm: float = 78.4,
                 theta_plus: float = 0.05, theta_decay: float = 1e-7, X_Ae_decay: Optional[float] = None,
                 Ae_Ai_decay: Optional[float] = None, Ai_Ae_decay: Optional[float] = None) -> None:
        # language=rst
        """
        Constructor for class ``DiehlAndCook2015``.

        :param n_inpt: Number of input neurons. Matches the 1D size of the input data.
        :param n_neurons: Number of excitatory, inhibitory neurons.
        :param exc: Strength of synapse weights from excitatory to inhibitory layer.
        :param inh: Strength of synapse weights from inhibitory to excitatory layer.
        :param dt: Simulation time step.
        :param nu_pre: Pre-synaptic learning rate.
        :param nu_post: Post-synaptic learning rate.
        :param wmin: Minimum allowed weight on input to excitatory synapses.
        :param wmax: Maximum allowed weight on input to excitatory synapses.
        :param norm: Input to excitatory layer connection weights normalization constant.
        :param theta_plus: On-spike increment of ``DiehlAndCookNodes`` membrane threshold potential.
        :param theta_decay: Time constant of ``DiehlAndCookNodes`` threshold potential decay.
        :param X_Ae_decay: Decay of activation of connection from input to excitatory neurons.
        :param Ae_Ai_decay: Decay of activation of connection from excitatory to inhibitory neurons.
        :param Ai_Ae_decay: Decay of activation of connection from inhibitory to excitatory neurons.
        """
        super().__init__(dt=dt)
        
        self.n_inpt = n_inpt
        self.n_neurons = n_neurons
        self.exc = exc
        self.inh = inh
        self.dt = dt
        
        self.add_layer(Input(n=self.n_inpt, traces=True, trace_tc=5e-2), name='X')
        self.add_layer(DiehlAndCookNodes(n=self.n_neurons, traces=True, rest=-65.0, reset=-60.0, thresh=-52.0, refrac=5,
                                         decay=1e-2, trace_tc=5e-2, theta_plus=theta_plus, theta_decay=theta_decay),
                       name='Ae')
        
        self.add_layer(LIFNodes(n=self.n_neurons, traces=False, rest=-60.0, reset=-45.0, thresh=-40.0, decay=1e-1,
                                refrac=2, trace_tc=5e-2),
                       name='Ai')

        w = 0.3 * torch.rand(self.n_inpt, self.n_neurons)
        self.add_connection(Connection(source=self.layers['X'], target=self.layers['Ae'], w=w, update_rule=PostPre,
                                       nu=(nu_pre, nu_post), wmin=wmin, wmax=wmax, norm=norm, decay=X_Ae_decay),
                            source='X', target='Ae')

        w = self.exc * torch.diag(torch.ones(self.n_neurons))
        self.add_connection(Connection(source=self.layers['Ae'], target=self.layers['Ai'], w=w, wmin=0, wmax=self.exc,
                                       decay=Ae_Ai_decay),
                            source='Ae', target='Ai')

        w = -self.inh * (torch.ones(self.n_neurons, self.n_neurons) - torch.diag(torch.ones(self.n_neurons)))
        self.add_connection(Connection(source=self.layers['Ai'], target=self.layers['Ae'], w=w, wmin=-self.inh, wmax=0,
                                       decay=Ai_Ae_decay),
                            source='Ai', target='Ae')

class LocallyConnectedNetwork(Network):
    # language=rst
    """
    Defines a two-layer network in which the input layer is "locally connected" to the output layer, and the output
    layer is recurrently inhibited connected such that neurons with the same input receptive field inhibit each other.
    """

    def __init__(self, n_inpt: int, kernel_size: Union[int, Tuple[int, int]], stride: Union[int, Tuple[int, int]],
                 n_filters: int, inh: float = 25.0, dt: float = 1.0, nu_pre: float = 1e-4, nu_post: float = 1e-2,
                 theta_plus: float = 0.05, theta_decay: float = 1e-7, wmin: float = 0.0, wmax: float = 1.0,
                 norm: float = 0.2) -> None:
        # language=rst
        """
        Constructor for class ``LocallyConnectedNetwork``. Uses ``DiehlAndCookNodes`` to avoid multiple spikes per
        timestep in the output layer population.

        :param n_inpt: Number of input neurons. Matches the 1D size of the input data.
        :param kernel_size: Size of input windows. Integer or two-tuple of integers.
        :param stride: Length of horizontal, vertical stride across input space. Integer or two-tuple of integers.
        :param n_filters: Number of locally connected filters per input region. Integer or two-tuple of integers.
        :param inh: Strength of synapse weights from output layer back onto itself.
        :param dt: Simulation time step.
        :param nu_pre: Pre-synaptic learning rate.
        :param nu_post: Post-synaptic learning rate.
        :param wmin: Minimum allowed weight on ``Input`` to ``DiehlAndCookNodes`` synapses.
        :param wmax: Maximum allowed weight on ``Input`` to ``DiehlAndCookNodes`` synapses.
        :param theta_plus: On-spike increment of ``DiehlAndCookNodes`` membrane threshold potential.
        :param theta_decay: Time constant of ``DiehlAndCookNodes`` threshold potential decay.
        :param norm: ``Input`` to ``DiehlAndCookNodes`` layer connection weights normalization constant.
        """
        super().__init__(dt=dt)

        self.n_inpt = n_inpt
        self.kernel_size = kernel_size
        self.stride = stride
        self.n_filters = n_filters
        self.inh = inh
        self.dt = dt
        self.theta_plus = theta_plus
        self.theta_decay = theta_decay
        self.wmin = wmin
        self.wmax = wmax
        self.norm = norm

        sqrt = int(np.sqrt(self.n_inpt))
        if kernel_size == sqrt:
            conv_size = 1
        else:
            conv_size = int((sqrt - kernel_size) / stride) + 1

        input_layer = Input(n=self.n_inpt, traces=True, trace_tc=5e-2)
        output_layer = DiehlAndCookNodes(
            n=self.n_filters * conv_size ** 2, traces=True, rest=-65.0, reset=-60.0, thresh=-52.0,
            refrac=5, decay=1e-2, trace_tc=5e-2, theta_plus=theta_plus, theta_decay=theta_decay
        )
        input_output_conn = LocallyConnectedConnection(
            input_layer, output_layer, kernel_size=kernel_size, stride=stride, n_filters=n_filters,
            nu=(nu_pre, nu_post), update_rule=PostPre, wmin=wmin, wmax=wmax, norm=norm
        )

        w = torch.zeros(n_filters, conv_size, conv_size, n_filters, conv_size, conv_size)
        for fltr1 in range(n_filters):
            for fltr2 in range(n_filters):
                if fltr1 != fltr2:
                    for i in range(conv_size):
                        for j in range(conv_size):
                            w[fltr1, i, j, fltr2, i, j] = -inh

        recurrent_conn = Connection(output_layer, output_layer, w=w)

        self.add_layer(input_layer, name='X')
        self.add_layer(output_layer, name='Y')
        self.add_connection(input_output_conn, source='X', target='Y')
        self.add_connection(recurrent_conn, source='Y', target='Y')
