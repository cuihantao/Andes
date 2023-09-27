# -*- coding: utf-8 -*-
"""
Created on Fri Sep 22 12:52:21 2023

@author: haya.monawwar
"""

from andes.core import (Algeb, ConstService, ExtParam,
                        ExtState, IdxParam, Model, ModelData, NumParam)
import math


class TCSCBaseData(ModelData):
    """
    Base data for turbine governors.
    """

    def __init__(self):
        super().__init__()
        self.tcsc = IdxParam(model='TCSC',
                            info='Thyristor controlled series compensator idx',
                            mandatory=True,
                            unique=True,
                            )
        self.P = NumParam(info='TCSC power rating. Equal to `Sn` if not provided.',
                           tex_name='P',
                           unit='MVA',
                           default=0.0,
                           )
        self.wref0 = NumParam(info='Base speed reference',
                              tex_name=r'\omega_{ref0}',
                              default=1.0,
                              unit='p.u.',
                              )
        self.Xc = NumParam(info='Capacitive reactance ',
                          tex_name='X_c',
                          unit='p.u.',
                          power=True,
                          )
        self.Xl = NumParam(info='Inductive reactance ',
                          tex_name='X_l',
                          unit='p.u.',
                          power=True,
                          )
        
        self.alpha = NumParam(info='Firing angle',
                            tex_name='alpha',
                            default=0.0,
                            unit='p.u.',
                            )

class TCSCBase(Model):
        """
        Base TCSC model.
        
        """

        def __init__(self, system, config, ):
            Model.__init__(self, system, config)
            self.flags.update({'tds': True})
            self.Sg = ExtParam(src='Sn', # Where do we get Sn from? 
                               model='SynGen',
                               indexer=self.syn,
                               tex_name='S_n',
                               info='Rated power from generator',
                               unit='MVA',
                               export=False,
                               )
            

            self.Vn = ExtParam(src='Vn',
                               model='SynGen',
                               indexer=self.syn,
                               tex_name='V_n',
                               info='Rated voltage from generator',
                               unit='kV',
                               export=False,
                               )


            self.wref = Algeb(info='Speed reference variable',
                              tex_name=r'\omega_{ref}',
                              v_str='wref0',
                              e_str='wref0 - wref',
                              )

class TCSC(TCSCModelData, TCSCBase):
    def __init__(self, system, config):
        TCSCModelData.__init__(self)
        TCSCBase.__init__(self, system, config)
           
