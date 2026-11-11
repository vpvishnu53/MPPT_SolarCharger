"""ctypes bindings to the firmware control logic (firmware/mppt_po.c, firmware/charger_fsm.c)."""
import ctypes as ct
import os

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_NAMES = ["IDLE", "BULK_MPPT", "CC_LIMIT", "CV_ABSORB", "FLOAT", "FAULT"]
FAULT_NAMES = ["NONE", "SENSOR", "BAT_OV", "OC"]
PWM_COUNTS = 420


class PoState(ct.Structure):
    _fields_ = [("v_prev", ct.c_float), ("p_prev", ct.c_float), ("duty", ct.c_float),
                ("step", ct.c_float), ("d_min", ct.c_float), ("d_max", ct.c_float),
                ("dir", ct.c_int8)]


class ChargerCfg(ct.Structure):
    _fields_ = [(n, ct.c_float) for n in (
        "d_min", "d_max", "po_step", "v_abs", "v_float", "i_cc",
        "i_tail", "v_rebulk", "cc_exit_frac", "cv_exit_dv", "pv_start_margin", "pv_stop_margin",
        "i_reverse", "v_bat_min", "v_bat_ov", "i_oc", "v_pv_max", "v_bat_sensor_min",
        "k_i", "k_v", "dstep_max")] + [("restart_holdoff", ct.c_uint16)]


class Charger(ct.Structure):
    _fields_ = [("state", ct.c_int), ("po", PoState), ("duty", ct.c_float),
                ("pwm_on", ct.c_uint8), ("fault", ct.c_uint8), ("idle_cnt", ct.c_uint16)]


class Meas(ct.Structure):
    _fields_ = [("vpv", ct.c_float), ("vbat", ct.c_float), ("ibat", ct.c_float)]


def load(path=None):
    path = path or os.path.join(HERE, "build", "libcharger.dll")
    lib = ct.CDLL(path)
    lib.charger_default_cfg.argtypes = [ct.POINTER(ChargerCfg)]
    lib.charger_init.argtypes = [ct.POINTER(Charger), ct.POINTER(ChargerCfg)]
    lib.charger_update.argtypes = [ct.POINTER(Charger), ct.POINTER(Meas)]
    lib.charger_update.restype = ct.c_float
    lib.fsm_step.argtypes = [ct.c_int, ct.POINTER(Meas)]
    lib.fsm_step.restype = ct.c_int
    lib.po_init.argtypes = [ct.POINTER(PoState), ct.c_float, ct.c_float, ct.c_float, ct.c_float]
    lib.po_update.argtypes = [ct.POINTER(PoState), ct.c_float, ct.c_float]
    lib.po_update.restype = ct.c_float
    for fn in ("sil_sizeof_po_state", "sil_sizeof_charger", "sil_sizeof_charger_cfg"):
        getattr(lib, fn).restype = ct.c_uint
    assert lib.sil_sizeof_po_state() == ct.sizeof(PoState), "po_state_t layout mismatch"
    assert lib.sil_sizeof_charger() == ct.sizeof(Charger), "charger_t layout mismatch"
    assert lib.sil_sizeof_charger_cfg() == ct.sizeof(ChargerCfg), "charger_cfg_t layout mismatch"
    return lib


def default_cfg(lib, **overrides):
    cfg = ChargerCfg()
    lib.charger_default_cfg(ct.byref(cfg))
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg
