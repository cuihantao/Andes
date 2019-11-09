import numpy as np
from cvxopt import matrix  # NOQA
from cvxopt import mul, div  # NOQA
from scipy.sparse import coo_matrix

from .base import ModelBase
from ..consts import Gy  # NOQA
from ..utils.math import altb, agtb, aorb, nota
from ..utils.math import zeros, ones

from .base import Model, ModelData
from andes.core.limiter import Comparer
from andes.core.var import ExtAlgeb, Algeb
from andes.core.param import DataParam, NumParam
from andes.core.service import Service
from andes.core.block import PIController, PIControllerNumeric  # NOQA


class PQ(ModelBase):
    """Static PQ load class"""

    def __init__(self, system, name):
        super().__init__(system, name)
        self._name = 'PQ'
        self._group = 'StaticLoad'
        self._category = 'Load'
        self._data.update({
            'bus': None,
            'p': 0,
            'q': 0,
            'owner': 0,
            'vmax': 1.1,
            'vmin': 0.9,
        })
        self._units.update({
            'bus': 'na',
            'p': 'pu',
            'owner': 'na',
            'vmax': 'pu',
            'vmin': 'pu',
        })
        self._params.extend(['p', 'q', 'vmax', 'vmin'])
        self._descr.update({
            'bus': 'bus number',
            'p': 'constant p value',
            'q': 'constant q value',
            'owner': 'owner code',
            'vmax': 'max voltage before switching to Z',
            'vmin': 'min voltage before switching to Z'
        })
        self._ac = {'bus': ['a', 'v']}
        self._powers = ['p', 'q']
        self._service = ['p0', 'q0', 'v0', 'below', 'above',
                         'normal']  # p0 and q0 are used during computation
        self.calls.update({
            'gcall': True,
            'gycall': True,
            'init0': True,
            'init1': True,
            'pflow': True,
            'shunt': True,
        })
        self._init()

    def init0(self, dae):
        """Set initial p and q for power flow"""
        self.p0 = matrix(self.p, (self.n, 1), 'd')
        self.q0 = matrix(self.q, (self.n, 1), 'd')

    def init1(self, dae):
        """Set initial voltage for time domain simulation"""
        self.v0 = matrix(dae.y[self.v])

    def gcall(self, dae):
        k = ones(self.n, 1)

        if self.system.config.forcez:
            if self.v0:
                k = div(dae.y[self.v]**2, self.v0**2)
        elif self.system.config.forcepq:
            pass
        else:
            k = zeros(self.n, 1)

            self.below = altb(dae.y[self.v], self.vmin)
            k += mul(self.below, div(dae.y[self.v]**2, self.vmin**2))

            self.above = agtb(dae.y[self.v], self.vmax)
            k += mul(self.above, div(dae.y[self.v]**2, self.vmax**2))

            normal = nota(aorb(self.below, self.above))
            k += mul(normal, ones(self.n, 1))

        k = mul(self.u, k)
        self.p0 = mul(k, self.p)
        self.q0 = mul(k, self.q)

        if self.n <= 400:
            for a, v, p, q in zip(self.a, self.v, self.p0, self.q0):
                dae.g[a] += p
                dae.g[v] += q
        else:
            # use scipy.sparse.coo_matrix to accelerate for large systems

            p0 = coo_matrix(
                (np.array(self.p0).reshape((-1)), (self.a, np.zeros(self.n))),
                shape=(dae.m, 1))
            q0 = coo_matrix(
                (np.array(self.q0).reshape((-1)), (self.v, np.zeros(self.n))),
                shape=(dae.m, 1))

            dae.g += matrix(p0.toarray())
            dae.g += matrix(q0.toarray())

    def gycall(self, dae):
        k = zeros(self.n, 1)
        if self.system.config.forcepq:
            return
        elif self.system.config.forcez:
            if self.v0:
                k = div(2 * dae.y[self.v], self.v0**2)
        else:
            k += mul(self.below, div(2 * dae.y[self.v], self.vmin**2))
            k += mul(self.above, div(2 * dae.y[self.v], self.vmax**2))
        k = mul(self.u, k)

        dae.add_jac(Gy, mul(self.p, k), self.a, self.v)
        dae.add_jac(Gy, mul(self.q, k), self.v, self.v)


class PQData(ModelData):
    def __init__(self):
        super().__init__()
        self.bus = DataParam(info="linked bus idx", mandatory=True)
        self.owner = DataParam(info="owner idx")

        self.p = NumParam(default=0, info='active power load', power=True)
        self.q = NumParam(default=0, info='reactive power load', power=True)
        self.vmax = NumParam(default=1.1, info='max voltage before switching to impedance')
        self.vmin = NumParam(default=0.9, info='min voltage before switching to impedance')


class PQNew(Model, PQData):
    def __init__(self, system=None, name=None):
        Model.__init__(self, system, name)
        PQData.__init__(self)

        # TODO: Take a configuration to disable switching to impedance

        self.a = ExtAlgeb(model='BusNew', src='a', indexer=self.bus)
        self.v = ExtAlgeb(model='BusNew', src='v', indexer=self.bus)

        self.v_cmp = Comparer(var=self.v, lower=self.vmin, upper=self.vmax)

        self.a.e_symbolic = "u * (p * v_cmp_zi + \
                                  p * v_cmp_zl * (v ** 2 / vmin ** 2) + \
                                  p * v_cmp_zu * (v ** 2 / vmax ** 2))"

        self.v.e_symbolic = "u * (q * v_cmp_zi + \
                                  q * v_cmp_zl * (v ** 2 / vmin ** 2) + \
                                  q * v_cmp_zu * (v ** 2 / vmax ** 2))"

        # Experimental Zone Below
        self.v_ref = Algeb(info="Voltage reference for PI")
        self.kp = Service()
        self.ki = Service()

        self.kp.e_symbolic = "1"
        self.ki.e_symbolic = "1"
        self.pi = PIController(self.v, self.v_ref, self.kp, self.ki,
                               info='PI controller for voltage')
