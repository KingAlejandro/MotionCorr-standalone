"""Frozen actual native-order CCF weight oracle: the scalar-double expression of MotioncorrRunner::ccfWeightAt, cast to float32, for the fixed 32x42
patch (half spectrum 32x22). Same expression and order as the earlier reviewed saved-array verification (verify_saved_arrays.py), with x_norm as a parameter.
x_norm 42 is the full width (local full-width weight); 22 is the inherited pnx/2+1."""
import numpy as np
NY, NFX, B = 32, 22, 150.0

def weight_map(x_norm):
    w = np.empty((NY, NFX), dtype=np.float32)
    for y in range(NY):
        ly = y - NY if y > NY // 2 else y
        for x in range(NFX):
            w[y, x] = np.exp(-2 * (ly * float(ly) / (NY * float(NY)) + x * float(x) / (float(x_norm) * float(x_norm))) * B)
    return w
