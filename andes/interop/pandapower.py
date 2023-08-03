"""
Simple pandapower (2.7.0) interface
"""

import logging
import numpy as np
from functools import wraps

from andes.shared import pd, rad2deg, deg2rad
from andes.shared import pandapower as pp

logger = logging.getLogger(__name__)


def require_pandapower(f):
    """
    Decorator for functions that require pandapower.
    """

    @wraps(f)
    def wrapper(*args, **kwds):
        try:
            getattr(pp, '__version__')
        except AttributeError:
            raise ModuleNotFoundError("pandapower needs to be manually installed.")

        return f(*args, **kwds)

    return wrapper


def build_group_table(ssa, group, columns, mdl_name=[]):
    """
    Build the table for devices in a group in an ANDES System.

    Parameters
    ----------
    ssa : andes.system.System
        The ANDES system to build the table
    group : string
        The ANDES group
    columns : list of string
        The common columns of a group that to be included in the table.
    mdl_name : list of string
        The list of models that to be included in the table. Default as all models.

    Returns
    -------
    DataFrame

        The output Dataframe contains the columns from the device
    """
    group_df = pd.DataFrame(columns=columns)
    group = getattr(ssa, group)
    if not mdl_name:
        mdl_dict = getattr(group, 'models')
        for key in mdl_dict:
            mdl = getattr(ssa, key)
            group_df = pd.concat([group_df, mdl.as_df()[columns]], axis=0)
    else:
        for key in mdl_name:
            mdl = getattr(ssa, key)
            group_df = pd.concat([group_df, mdl.as_df()[columns]], axis=0)
    return group_df.reset_index(drop=True)


def make_link_table(ssa):
    """
    Build the link table for generators and generator controllers in an ANDES
    System, including ``SynGen`` and ``DG`` for now.

    Parameters
    ----------
    ssa : andes.system.System
        The ANDES system to link

    Returns
    -------
    DataFrame

        Each column in the output Dataframe contains the ``idx`` of linked
        ``StaticGen``, ``Bus``, ``DG``, ``RenGen``, ``RenExciter``, ``SynGen``,
        ``Exciter``, and ``TurbineGov``, ``gammap``, ``gammaq``.
    """
    # build StaticGen df
    ssa_stg = build_group_table(ssa, 'StaticGen', ['u', 'name', 'idx', 'bus'])
    # build TurbineGov df
    ssa_gov = build_group_table(ssa, 'TurbineGov', ['idx', 'syn'])
    # build Exciter df
    ssa_exc = build_group_table(ssa, 'Exciter', ['idx', 'syn'])
    # build SynGen df
    ssa_syg = build_group_table(ssa, 'SynGen', ['idx', 'bus', 'gen', 'gammap', 'gammaq'], ['GENCLS', 'GENROU'])
    # build DG df
    ssa_dg = build_group_table(ssa, 'DG', ['idx', 'bus', 'gen', 'gammap', 'gammaq'])
    # build RenGen df
    ssa_rg = build_group_table(ssa, 'RenGen', ['idx', 'bus', 'gen', 'gammap', 'gammaq'])
    # build RenExciter df
    ssa_rexc = build_group_table(ssa, 'RenExciter', ['idx', 'reg'])

    # output
    ssa_bus = ssa.Bus.as_df()[['name', 'idx']]
    ssa_key = pd.merge(left=ssa_stg.rename(columns={'name': 'stg_name', 'idx': 'stg_idx',
                                                    'bus': 'bus_idx', 'u': 'stg_u'}),
                       right=ssa_bus.rename(columns={'name': 'bus_name', 'idx': 'bus_idx'}),
                       how='left', on='bus_idx')
    ssa_syg = pd.merge(left=ssa_key, how='right', on='stg_idx',
                       right=ssa_syg.rename(columns={'idx': 'syg_idx', 'gen': 'stg_idx'}))
    ssa_dg = pd.merge(left=ssa_key, how='right', on='stg_idx',
                      right=ssa_dg.rename(columns={'idx': 'dg_idx', 'gen': 'stg_idx'}))
    ssa_rg = pd.merge(left=ssa_key, how='right', on='stg_idx',
                      right=ssa_rg.rename(columns={'idx': 'rg_idx', 'gen': 'stg_idx'}))
    ssa_key0 = pd.merge(left=ssa_key, how='left', on='stg_idx',
                        right=ssa_syg[['stg_idx', 'syg_idx']])
    ssa_key0 = pd.merge(left=ssa_key0, how='left', on='stg_idx',
                        right=ssa_dg[['stg_idx', 'dg_idx']])
    ssa_key0 = pd.merge(left=ssa_key0, how='left', on='stg_idx',
                        right=ssa_rg[['stg_idx', 'rg_idx']])
    ssa_key0.fillna(False, inplace=True)
    ssa_key0['dyr'] = ssa_key0['syg_idx'].astype(
        bool) + ssa_key0['dg_idx'].astype(bool) + ssa_key0['rg_idx'].astype(bool)
    ssa_key0['dyr'] = 1 - ssa_key0['dyr'].astype(int)
    ssa_key0['dyr'] = ssa_key0['dyr'].astype(bool)
    ssa_dyr0 = ssa_key0[ssa_key0.dyr].drop(['dyr'], axis=1)
    ssa_dyr0['gammap'] = 1
    ssa_dyr0['gammaq'] = 1
    ssa_key = pd.concat([ssa_syg, ssa_dg, ssa_rg, ssa_dyr0], axis=0)
    ssa_key = pd.merge(left=ssa_key,
                       right=ssa_exc.rename(columns={'idx': 'exc_idx', 'syn': 'syg_idx'}),
                       how='left', on='syg_idx')
    ssa_key = pd.merge(left=ssa_key,
                       right=ssa_gov.rename(columns={'idx': 'gov_idx', 'syn': 'syg_idx'}),
                       how='left', on='syg_idx')
    ssa_key = pd.merge(left=ssa_key, how='left', on='rg_idx',
                       right=ssa_rexc.rename(columns={'idx': 'rexc_idx', 'reg': 'rg_idx'}))

    cols = ['stg_name', 'stg_u', 'stg_idx', 'bus_idx', 'dg_idx', 'rg_idx', 'rexc_idx',
            'syg_idx', 'exc_idx', 'gov_idx', 'bus_name', 'gammap', 'gammaq']
    return ssa_key[cols].reset_index(drop=True)


@require_pandapower
def runopp_map(ssp, link_table, **kwargs):
    """
    Run OPF in pandapower using ``pp.runopp()`` and map results back to ANDES
    based on the link table.

    Parameters
    ----------
    ssp : pandapower network
        The pandapower network

    link_table : DataFrame
        The link table of ANDES system

    Returns
    -------
    DataFrame

        The DataFrame contains the OPF results with columns ``p_mw``,
        ``q_mvar``, ``vm_pu`` in p.u., and the corresponding ``idx`` of
        ``StaticGen``, ``Exciter``, ``TurbineGov`` in ANDES.

    Notes
    -----
      - The pandapower net and the ANDES system must have same base MVA.
      - Multiple ``DG`` connected to the same ``StaticGen`` will be converted to one generator.
        The power is dispatched to each ``DG`` by the power ratio ``gammap``
    """

    try:
        pp.runopp(ssp, **kwargs)
        logger.warning("ACOPF is solved.")
    except Exception:
        pp.rundcopp(ssp, **kwargs)
        logger.warning("ACOPF failed. DCOPF is solved.")

    # take dispatch results from pp
    ssp_gen = ssp.gen.rename(columns={'name': 'stg_idx'})
    ssp_res = pd.concat([ssp_gen[['stg_idx']],
                        ssp.res_gen[['p_mw', 'q_mvar', 'vm_pu']]], axis=1)

    ssp_res = pd.merge(left=ssp_res,
                       right=ssp_gen[['stg_idx', 'controllable']],
                       how='left', on='stg_idx')
    ssp_res = pd.merge(left=ssp_res, right=link_table,
                       how='left', on='stg_idx')
    ssp_res['p'] = ssp_res['p_mw'] * ssp_res['gammap'] / ssp.sn_mva
    ssp_res['q'] = ssp_res['q_mvar'] * ssp_res['gammaq'] / ssp.sn_mva
    col = ['stg_idx', 'p', 'q', 'vm_pu', 'bus_idx', 'controllable',
           'dg_idx', 'rg_idx', 'syg_idx', 'gov_idx', 'exc_idx']
    return ssp_res[col]


@require_pandapower
def add_gencost(ssp, gen_cost):
    """
    Add cost function to converted pandapower net `ssp`.

    The cost data follows the same format of pypower and matpower.

    Now only poly_cost is supported.

    Parameters
    ----------
    ssp :
        The pandapower net

    gen_cost : array
        generator cost data
    """

    # check dimension
    if gen_cost.shape[0] != ssp.gen.shape[0]:
        print('Input cost function size does not match gen size.')

    for num, uid in enumerate(ssp.gen.index):
        if gen_cost[num, 0] == 2:  # poly_cost
            pp.create_poly_cost(net=ssp,
                                element=uid,
                                et='gen',
                                cp2_eur_per_mw2=gen_cost[num, 4],
                                cp1_eur_per_mw=gen_cost[num, 5],
                                cp0_eur=gen_cost[num, 6])
        else:
            # TODO: piecewise linear
            continue

    return True


def _to_pp_bus(ssp, ssa_bus):
    """Create bus in pandapower net"""
    bus_cols = ['Vn', 'name', 'u', 'vmax', 'vmin', 'zone']
    bus_df = ssa_bus[bus_cols]
    bus_df.columns = ['vn_kv', 'name', 'in_service', 'max_vm_pu', 'min_vm_pu', 'zone']
    bus_df['type'] = 'b'
    bus_df['in_service'] = bus_df['in_service'].astype('bool')
    bus_df.reset_index(inplace=True, drop=True)
    setattr(ssp, 'bus', bus_df)
    return ssp


def _to_pp_line(ssa, ssp, ssa_bus):
    """Create line in pandapower net"""
    # TODO: 1) from- and to- sides `Y`; 2)`g`
    omega = 2 * np.pi * ssp.f_hz

    ssa_bus_slice = ssa.Bus.as_df()[['idx', 'Vn']].rename(columns={"idx": "bus1", "Vn": "Vb"})
    ssa_line = ssa.Line.as_df().merge(ssa_bus_slice, on='bus1', how='left')

    ssa_line['Zb'] = ssa_line["Vb"]**2 / ssa_line["Sn"]
    ssa_line['Yb'] = ssa_line["Sn"] / ssa_line["Vb"]**2
    ssa_line['R'] = ssa_line["r"] * ssa_line['Zb']  # ohm
    ssa_line['X'] = ssa_line["x"] * ssa_line['Zb']  # ohm
    ssa_line['C'] = ssa_line["b"] / ssa_line['Zb'] / omega * 1e9  # nF
    ssa_line['G'] = ssa_line["g"] * ssa_line['Yb'] * 1e6  # mS
    # default rate_a is 2000 MVA
    ssa_line['rate_a'] = ssa_line['rate_a'].replace(0, 2000)
    ssa_line['max_i_ka'] = ssa_line["rate_a"] / ssa_line['Vb'] / np.sqrt(3)  # kA

    ssa_bus1 = ssa_bus[['idx']]
    ssa_bus1['from_bus'] = ssa_bus.index
    ssa_bus1.rename(columns={'uid': 'from_bus', 'idx': 'bus1'}, inplace=True)
    ssa_bus1 = ssa_bus1.reset_index(drop=True)
    ssa_bus2 = ssa_bus1.copy()
    ssa_bus2.rename(columns={'from_bus': 'to_bus', 'bus1': 'bus2'}, inplace=True)
    ssa_line = ssa_line.merge(ssa_bus1, on='bus1', how='left')
    ssa_line = ssa_line.merge(ssa_bus2, on='bus2', how='left')

    ssa_line['name'] = _rename(ssa_line['name'])

    line_cols = ['name', 'from_bus', 'to_bus', 'u', 'R', 'X', 'C', 'G', 'max_i_ka']
    line_df = ssa_line[line_cols][ssa_line['trans'] == 0].reset_index(drop=True)
    line_df['length_km'] = 1
    line_df['type'] = 'ol'
    line_df['parallel'] = 1
    line_df['max_loading_percent'] = 100
    line_df['df'] = 1
    line_df['std_type'] = None
    line_df.rename(columns={'R': 'r_ohm_per_km', 'X': 'x_ohm_per_km',
                            'C': 'c_nf_per_km', 'G': 'g_us_per_km',
                            'u': 'in_service'}, inplace=True)
    line_df['in_service'] = line_df['in_service'].astype('bool')
    setattr(ssp, 'line', line_df)

    tf_df = ssa_line[ssa_line['trans'] == 1].reset_index(drop=True)
    if tf_df.shape[0] > 1:
        tf_df.rename(columns={'R': 'r_ohm_per_km', 'X': 'x_ohm_per_km',
                              'C': 'c_nf_per_km', 'G': 'g_us_per_km',
                              'u': 'in_service'}, inplace=True)
        tf_df['in_service'] = tf_df['in_service'].astype('bool')

        tf_df['hv_bus'] = tf_df[['from_bus', 'to_bus', 'Vn1', 'Vn2']].apply(
            lambda x: x[0] if x[2] >= x[3] else x[1], axis=1)
        tf_df['lv_bus'] = tf_df[['from_bus', 'to_bus', 'Vn1', 'Vn2']].apply(
            lambda x: x[0] if x[2] < x[3] else x[1], axis=1)
        tf_df[['hv_bus', 'lv_bus']] = tf_df[['hv_bus', 'lv_bus']].astype('int')
        tf_df['vn_hv_kv'] = tf_df[['from_bus', 'to_bus', 'Vn1', 'Vn2']].apply(
            lambda x: x[2] if x[2] >= x[3] else x[3], axis=1)
        tf_df['vn_lv_kv'] = tf_df[['from_bus', 'to_bus', 'Vn1', 'Vn2']].apply(
            lambda x: x[2] if x[2] < x[3] else x[3], axis=1)
        tf_df['tap_side'] = tf_df[['Vn1', 'Vn2']].apply(lambda x: 'hv' if x[0] >= x[1] else 'lv', axis=1)

        tf_df['zk'] = (tf_df['r'] ** 2 + tf_df['x'] ** 2) ** 0.5
        tf_df['sn_mva'] = 99999
        tf_df['vk_percent'] = np.sign(tf_df['x']) * tf_df['zk'] * tf_df['sn_mva'] * 100 / ssp.sn_mva
        tf_df['vkr_percent'] = tf_df['r'] * tf_df['sn_mva'] * 100 / ssp.sn_mva
        tf_df['max_loading_percent'] = 100
        tf_df['pfe_kw'] = 0
        tf_df['i0_percent'] = -tf_df['b'] * 100 * ssp.sn_mva / tf_df['sn_mva']
        tf_df['shift_degree'] = tf_df['phi'] * rad2deg
        tf_df['tap_step_percent'] = abs((tf_df['tap'] - 1) * 100)
        tf_df['tap_pos'] = np.sign((tf_df['tap'] - 1) * 100)
        tf_df['tap_neutral'] = 0
        tf_df['parallel'] = 1
        tf_df['oltc'] = False
        tf_df['tap_phase_shifter'] = False
        tf_df['tap_step_degree'] = np.NaN
        tf_df['df'] = 1
        tf_df['std_type'] = None

        trafo_cols = ['name', 'hv_bus', 'lv_bus', 'sn_mva', 'vn_hv_kv',
                      'vn_lv_kv', 'vk_percent', 'vkr_percent', 'pfe_kw', 'i0_percent',
                      'shift_degree', 'tap_side', 'tap_neutral',
                      'tap_step_percent', 'tap_pos', 'in_service',
                      'max_loading_percent', 'parallel', 'tap_phase_shifter',
                      'tap_step_degree', 'df', 'std_type']

        tf_df[trafo_cols].reset_index(drop=True)
        setattr(ssp, 'trafo', tf_df[trafo_cols].reset_index(drop=True))
    return ssp


def _to_pp_load(ssa, ssp, ssa_bus):
    """Create load in pandapower net"""
    ssa_pq = ssa.PQ.as_df()
    ssa_pq['p_mw'] = ssa_pq["p0"] * ssp.sn_mva
    ssa_pq['q_mvar'] = ssa_pq["q0"] * ssp.sn_mva

    ssa_pq['name'] = _rename(ssa_pq['name'])
    pq_cols = ['name', 'u', 'p_mw', 'q_mvar', 'bus']
    load_df = ssa_pq[pq_cols].reset_index(drop=True)
    load_df.rename(columns={'u': 'in_service', 'bus': 'idx'}, inplace=True)
    load_df['in_service'] = load_df['in_service'].astype('bool')
    load_df = load_df.merge(ssa_bus[['idx', 'bus']], on='idx', how='left')
    load_df['sn_mva'] = ssp.sn_mva
    load_df['controllable'] = False
    load_df['type'] = None
    load_df['const_i_percent'] = 0
    load_df['const_z_percent'] = 0
    load_df['scaling'] = 1
    load_df.drop(['idx'], axis=1, inplace=True)
    setattr(ssp, 'load', load_df)
    return ssp


def _to_pp_shunt(ssa, ssp, ssa_bus):
    """Create shunt in pandapower net"""
    ssa_shunt = ssa.Shunt.as_df()
    ssa_shunt['p_mw'] = ssa_shunt["g"] * ssp.sn_mva
    ssa_shunt['q_mvar'] = ssa_shunt["b"] * (-1) * ssp.sn_mva

    ssa_shunt['name'] = _rename(ssa_shunt['name'])
    shunt_cols = ['name', 'u', 'p_mw', 'q_mvar', 'bus', 'Vn']
    shunt_df = ssa_shunt[shunt_cols].reset_index(drop=True)
    shunt_df.rename(inplace=True,
                    columns={'u': 'in_service', 'bus': 'idx',
                             'Vn': 'vn_kv'})
    shunt_df['in_service'] = shunt_df['in_service'].astype('bool')
    shunt_df = shunt_df.merge(ssa_bus[['idx', 'bus']], on='idx', how='left')
    shunt_df['step'] = 1
    shunt_df['max_step'] = 1
    shunt_df.drop(['idx'], axis=1, inplace=True)
    setattr(ssp, 'shunt', shunt_df)
    return ssp


def _to_pp_gen_pre(ssa):
    """Create generator data in pandapower net"""
    # build StaticGen df
    stg_cols = ['idx', 'u', 'bus', 'v0', 'vmax', 'vmin']
    stg_calc_cols = ['p0', 'q0', 'pmax', 'pmin', 'qmax', 'qmin']
    ssa_stg = build_group_table(ssa, 'StaticGen', stg_cols + stg_calc_cols)
    ssa_stg['name'] = ssa_stg.idx
    ssa_stg.rename(inplace=True,
                   columns={"bus": "bus_idx",
                            "u": "stg_u",
                            "idx": "stg_idx"})
    # retrieve Bus idx in pp net
    ssa_busn = ssa.Bus.as_df().copy().reset_index()[["uid", "idx"]].rename(
        columns={"uid": "pp_bus", "idx": "bus_idx"})

    ssa_stg = pd.merge(ssa_stg, ssa_busn,
                       how="left", on="bus_idx")

    return ssa_stg


def _to_pp_gen(ssa, ssp, ctrl=[]):
    """Create shunt in pandapower net"""
    # TODO: Add RenGen
    ssa_sg = _to_pp_gen_pre(ssa)

    # assign slack bus
    ssa_sg["slack"] = False
    ssa_sg["slack"][ssa_sg["bus_idx"] == ssa.Slack.bus.v[0]] = True

    # compute the actual value
    stg_calc_cols = ['p0', 'q0', 'pmax', 'pmin', 'qmax', 'qmin']
    ssa_sg[stg_calc_cols] = ssa_sg[stg_calc_cols].apply(lambda x: x * ssp.sn_mva)
    if 'gammap' not in _to_pp_gen_pre(ssa).columns:
        ssa_sg['gammap'] = 1
        ssa_sg['gammaq'] = 1
    else:
        ssa_sg['p0'] = ssa_sg['p0'] * ssa_sg['gammap']
        ssa_sg['q0'] = ssa_sg['q0'] * ssa_sg['gammaq']

    # default controllable is determined by governor
    if len(ctrl) > 0:
        if len(ctrl) != len(ssa_sg):
            raise ValueError("ctrl length does not match StaticGen length")
    else:
        ctrl = [1] * len(ssa_sg)
    ssa_sg["ctrl"] = [bool(x) for x in ctrl]

    ssa_sg['name'] = _rename(ssa_sg['name'])
    gen_cols = ['name', 'slack', 'pp_bus', 'p0', 'v0', 'ctrl',
                'stg_u', 'pmax', 'pmin', 'qmax', 'qmin']
    gen_df = ssa_sg[gen_cols].copy()
    gen_df.rename(inplace=True,
                  columns={'pp_bus': 'bus', 'p0': 'p_mw',
                           'v0': 'vm_pu', 'ctrl': 'controllable',
                           'stg_u': 'in_service', 'pmax': 'max_p_mw',
                           'pmin': 'min_p_mw', 'qmax': 'max_q_mvar',
                           'qmin': 'min_q_mvar'})
    gen_df['in_service'] = gen_df['in_service'].astype('bool')
    gen_df['controllable'] = gen_df['controllable'].astype('bool')
    gen_df['slack_weight'] = gen_df['slack'].astype('float')
    gen_df['scaling'] = 1
    gen_df['sn_mva'] = ssp.sn_mva
    setattr(ssp, 'gen', gen_df)
    return ssp


@require_pandapower
def to_pandapower(ssa, ctrl=[], verify=True, tol=1e-6):
    """
    Convert an ANDES system to a pandapower network for power flow studies.

    Parameters
    ----------
    ssa : andes.system.System
        The ANDES system to be converted
    ctrl : list
        The controlability of generators. The length should be the same with the
        number of ``StaticGen``.
        If not given, controllability of generators will be assigned by default.
        Example input: [1, 0, 1, ...]; ``PV`` first, then ``Slack``.
    verify : bool
        If True, the converted network will be verified with the source ANDES system
        using AC power flow.
    tol : float
        The tolerance of error.

    Returns
    -------
    pandapower.auxiliary.pandapowerNet
        A pandapower net with the same bus, branch, gen, and load data as the
        ANDES system

    Notes
    -----
    Handling of the following parameters:
      - This interface tracks static power flow model in ANDES: `Bus`, `Line`, `PQ`, `Shunt`, `PV`, and `Slack`.
        However, it does not track the dynamic models in ANDES, including but not limited to
        `TurbineGov`, `SynGen`, and `Exciter`.
      - The interface converts the ``Slack`` in ANDES to ``gen`` in pandapower rather than ``ext_gen``.
      - MUST NOT verify power flow after initializing TDS in ANDES. ANDES does not allow running ``PFlow``
        for systems with initialized TDS as it will break variable addressing.
      - If you want to track dynamic model outputs in ANDES and feedback into pandapower,
        you might need to manually transfer the results from ANDES to pandapower.
      - Generator cost is not included in the conversion. Use ``add_gencost()``
        to add cost data.
      - By default, all generators in ``ssp`` are controllable unless user-defined controllability
        is given
      - The online status of generators are determined by the online status of ``StaticGen``
        that connected to the ``SynGen`` or ``DG``
      - ``ssp.gen.name`` is from ``ssa.StaticGen.idx``, which should be unique
    """

    # create a PP network
    ssp = pp.create_empty_network(f_hz=ssa.config.freq,
                                  sn_mva=ssa.config.mva,
                                  )

    # build bus table
    ssa_bus = ssa.Bus.as_df()
    ssa_bus['name'] = _rename(ssa_bus['name'])
    ssa_bus['bus'] = ssa_bus.index

    # --- 1. convert buses ---
    ssp = _to_pp_bus(ssp, ssa_bus)

    # --- 2. convert Line ---
    ssp = _to_pp_line(ssa, ssp, ssa_bus)

    # --- 3. load ---
    ssp = _to_pp_load(ssa, ssp, ssa_bus)

    # --- 4. shunt ---
    ssp = _to_pp_shunt(ssa, ssp, ssa_bus)

    # --- 5. generator ---
    ssp = _to_pp_gen(ssa, ssp, ctrl)

    if verify:
        _verify_pf(ssa, ssp, tol)

    return ssp


def _verify_pf(ssa, ssp, tol=1e-6):
    """
    Verify power flow results between ANDES and pandapower.

    Parameters
    ----------
    tol : float
        The tolerance of error.

    Returns
    -------
    True
        If the difference between the two results is within the tolerance
    False
        If the difference is larger than the tolerance, OR time-domain
        simulation has been run in the ANDES system. ANDES is not able to run
        power flow after initializing time-domain simulation.
    """

    if ssa.TDS.initialized:
        return False

    ssa.PFlow.run()
    pp.runpp(ssp)

    pf_bus = ssa.Bus.as_df()[["name"]]

    # ssa
    pf_bus['v_andes'] = ssa.Bus.v.v
    pf_bus['a_andes'] = ssa.Bus.a.v

    # ssp
    pf_bus['v_pp'] = ssp.res_bus['vm_pu']
    pf_bus['a_pp'] = ssp.res_bus['va_degree'] * deg2rad

    # align ssa angle with slcka bus angle
    row_slack = np.argmin(np.abs(pf_bus['a_pp']))
    pf_bus['a_andes'] = pf_bus['a_andes'] - pf_bus['a_andes'].iloc[row_slack]

    pf_bus['v_diff'] = pf_bus['v_andes'] - pf_bus['v_pp']
    pf_bus['a_diff'] = pf_bus['a_andes'] - pf_bus['a_pp']

    if (np.max(np.abs(pf_bus['v_diff'])) < tol) and \
            (np.max(np.abs(pf_bus['a_diff'])) < tol):
        logger.info("Power flow results are consistent. Conversion is successful.")
        return True
    else:
        logger.warning("Warning: Power flow results are inconsistent. Please check!")
        return False


def _rename(pds_in):
    """
    Rename the duplicated elelemts in a pandas.Series.
    """
    if pds_in.duplicated().any():
        pds = pds_in.copy()
        dp_index = pds.duplicated()[pds.duplicated()].index
        pds.iloc[dp_index] = pds.iloc[dp_index] + ' ' + pds.iloc[dp_index].index.astype(str)
        return pds
    else:
        return pds_in


# TODO: add test for make GSF
@require_pandapower
def make_GSF(ppn, verify=True, using_sparse_solver=False):
    """
    Build the Generation Shift Factor matrix of a pandapower net.

    Parameters
    ----------
    ppn : pandapower.network.Network
        Pandapower network
    verify : bool
        True to verify the GSF with that from DC power flow
    using_sparse_solver : bool
        True to use a sparse solver for pandapower maktPTDF

    Returns
    -------
    np.ndarray
        The GSF array
    """

    from pandapower.pypower.makePTDF import makePTDF
    from pandapower.pd2ppc import _pd2ppc

    # --- run DCPF ---
    pp.rundcpp(ppn)

    # --- compute PTDF ---
    _, ppci = _pd2ppc(ppn)
    ptdf = makePTDF(ppci["baseMVA"], ppci["bus"], ppci["branch"],
                    using_sparse_solver=using_sparse_solver)

    # --- get the gsf ---
    line_size = ppn.line.shape[0]
    gsf = ptdf[0:line_size, :]

    if verify:
        _verifyGSF(ppn, gsf)

    return gsf


def _verifyGSF(ppn, gsf, tol=1e-4):
    """Verify the GSF with DCPF"""
    # --- DCPF results ---
    rl = pd.concat([ppn.res_line['p_from_mw'], ppn.line[['from_bus', 'to_bus']]], axis=1)
    rp = _sumPF_ppn(ppn)
    rl_c = np.array(np.matrix(gsf) * np.matrix(rp.ngen).T)
    res_gap = rl.p_from_mw.values - rl_c.flatten()
    if np.abs(res_gap).max() <= tol:
        logger.info("GSF is consistent.")
    else:
        logger.warning("Warning: GSF is inconsistent. Pleaes check!")


def _sumPF_ppn(ppn):
    """Summarize PF results of a pandapower net"""
    rg = pd.DataFrame()
    rg['gen'] = ppn.res_gen['p_mw']
    rg['bus'] = ppn.gen['bus']
    rg = rg.groupby('bus').sum()
    rg.reset_index(inplace=True)
    rd = pd.DataFrame()
    rd['demand'] = ppn.res_load['p_mw']
    rd['bus'] = ppn.load['bus']
    rd = rd.groupby('bus').sum()
    rd.reset_index(inplace=True)
    rp = pd.DataFrame()
    rp['bus'] = ppn.bus.index
    rp = pd.merge(rp, rg, how='left', on='bus')
    rp = pd.merge(rp, rd, how='left', on='bus')
    rp.fillna(0, inplace=True)
    rp['ngen'] = rp['gen'] - rp['demand']
    return rp
