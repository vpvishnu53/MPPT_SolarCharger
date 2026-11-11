"""Minimal reader for LTspice binary .raw files (transient, optionally .step'ped).

Format (LTspice 17-26): UTF-16LE text header ending with "Binary:\n", then for each
point: time as float64, every other variable as float32 (unless the "double" flag is set).
Stepped runs are concatenated; a new step starts where time returns to its start value.
With waveform compression LTspice may store time with a negative sign, so abs() is taken.
"""
import re

import numpy as np


def read_raw(path):
    with open(path, "rb") as f:
        data = f.read()
    marker = "Binary:\n".encode("utf-16-le")
    hdr_end = data.find(marker)
    if hdr_end < 0:
        raise ValueError("not a binary LTspice raw file")
    header = data[:hdr_end].decode("utf-16-le")
    body = data[hdr_end + len(marker):]

    nvars = int(re.search(r"No\. Variables:\s*(\d+)", header).group(1))
    npts = int(re.search(r"No\. Points:\s*(\d+)", header).group(1))
    flags = re.search(r"Flags:\s*(.*)", header).group(1)
    names = []
    vblock = header.split("Variables:")[-1].strip().splitlines()
    for line in vblock[:nvars]:
        parts = line.split()
        names.append(parts[1])

    if "double" in flags:
        dt = np.dtype([(n, "<f8") for n in names])
    else:
        dt = np.dtype([(names[0], "<f8")] + [(n, "<f4") for n in names[1:]])
    arr = np.frombuffer(body, dtype=dt, count=npts)

    t = np.abs(arr[names[0]].astype(np.float64))
    # step boundaries: time goes backwards
    starts = np.concatenate(([0], np.where(np.diff(t) < 0)[0] + 1, [len(t)]))
    steps = []
    for a, b in zip(starts[:-1], starts[1:]):
        d = {"time": t[a:b]}
        for n in names[1:]:
            d[n] = arr[n][a:b].astype(np.float64)
        steps.append(d)
    return names, steps


def parse_meas_log(path):
    """Return (step_params, {meas_name: [values per step]}) from an LTspice .log."""
    text = open(path, encoding="latin-1").read()
    params = []
    for m in re.finditer(r"^\.step (.+)$", text, re.M):
        params.append(dict(kv.split("=") for kv in m.group(1).split()))
    meas = {}
    for block in re.finditer(r"Measurement: (\w+)\n\s+step[^\n]*\n((?:\s+\d+\s+[^\n]*\n)+)", text):
        vals = [float(line.split()[1]) for line in block.group(2).strip().splitlines()]
        meas[block.group(1)] = vals
    return params, meas
