"""Profiler agent — GPU-accelerated column statistics (Numba CUDA).

Sits between Scout and Architect. Computes per-column statistics over the full
dataset and stores them in state["data_profile"] so the Architect can make
better-informed transformation decisions.

GPU path: fires when CUDA is available AND row count >= GPU_THRESHOLD.
CPU path: plain NumPy, used as fallback.
"""
import math
from datetime import datetime

import numpy as np

try:
    import numba
    from numba import cuda
    _CUDA_AVAILABLE = cuda.is_available()
except ImportError:
    _CUDA_AVAILABLE = False

GPU_THRESHOLD = 100_000  # rows
BLOCK_SIZE = 256


# ── CUDA kernels ──────────────────────────────────────────────────────────────

if _CUDA_AVAILABLE:
    @cuda.jit
    def _null_count_kernel(is_null, out):
        """Each thread checks one row; atomically increments null counter."""
        i = cuda.grid(1)
        if i < is_null.size and is_null[i]:
            cuda.atomic.add(out, 0, 1)

    @cuda.jit
    def _stats_kernel(values, is_null, blk_min, blk_max, blk_sum, blk_cnt):
        """
        Per-block reduction of min / max / sum / count for valid (non-null) values.
        Uses shared memory for the within-block reduction; writes one result per
        block to the output arrays. Final cross-block reduction runs on the CPU.
        """
        shared_min = cuda.shared.array(BLOCK_SIZE, dtype=numba.float64)
        shared_max = cuda.shared.array(BLOCK_SIZE, dtype=numba.float64)
        shared_sum = cuda.shared.array(BLOCK_SIZE, dtype=numba.float64)
        shared_cnt = cuda.shared.array(BLOCK_SIZE, dtype=numba.float64)

        tid = cuda.threadIdx.x
        i = cuda.grid(1)

        # Load element or identity values into shared memory
        if i < values.size and not is_null[i]:
            v = values[i]
            shared_min[tid] = v
            shared_max[tid] = v
            shared_sum[tid] = v
            shared_cnt[tid] = 1.0
        else:
            shared_min[tid] = math.inf
            shared_max[tid] = -math.inf
            shared_sum[tid] = 0.0
            shared_cnt[tid] = 0.0

        cuda.syncthreads()

        # Tree reduction: halve active threads each round
        stride = cuda.blockDim.x >> 1
        while stride > 0:
            if tid < stride:
                if shared_min[tid + stride] < shared_min[tid]:
                    shared_min[tid] = shared_min[tid + stride]
                if shared_max[tid + stride] > shared_max[tid]:
                    shared_max[tid] = shared_max[tid + stride]
                shared_sum[tid] += shared_sum[tid + stride]
                shared_cnt[tid] += shared_cnt[tid + stride]
            cuda.syncthreads()
            stride >>= 1

        # Thread 0 writes this block's result
        if tid == 0:
            blk_min[cuda.blockIdx.x] = shared_min[0]
            blk_max[cuda.blockIdx.x] = shared_max[0]
            blk_sum[cuda.blockIdx.x] = shared_sum[0]
            blk_cnt[cuda.blockIdx.x] = shared_cnt[0]


# ── Column preparation ────────────────────────────────────────────────────────

def _to_float_array(rows: list, col: str):
    """Return (float64 values array, bool null mask) for a column."""
    vals, nulls = [], []
    for row in rows:
        v = row.get(col)
        try:
            vals.append(float(v))
            nulls.append(False)
        except (TypeError, ValueError):
            vals.append(0.0)
            nulls.append(True)
    return np.array(vals, dtype=np.float64), np.array(nulls, dtype=np.bool_)


# ── Per-column stat computation ───────────────────────────────────────────────

def _gpu_stats(values: np.ndarray, is_null: np.ndarray) -> dict:
    n = len(values)
    n_blocks = math.ceil(n / BLOCK_SIZE)

    d_values = cuda.to_device(values)
    d_is_null = cuda.to_device(is_null)

    # Null count
    d_null_out = cuda.to_device(np.zeros(1, dtype=np.int64))
    _null_count_kernel[n_blocks, BLOCK_SIZE](d_is_null, d_null_out)
    null_count = int(d_null_out.copy_to_host()[0])

    # Min / max / sum / count via block reduction
    d_blk_min = cuda.to_device(np.full(n_blocks, np.inf, dtype=np.float64))
    d_blk_max = cuda.to_device(np.full(n_blocks, -np.inf, dtype=np.float64))
    d_blk_sum = cuda.to_device(np.zeros(n_blocks, dtype=np.float64))
    d_blk_cnt = cuda.to_device(np.zeros(n_blocks, dtype=np.float64))

    _stats_kernel[n_blocks, BLOCK_SIZE](
        d_values, d_is_null,
        d_blk_min, d_blk_max, d_blk_sum, d_blk_cnt,
    )

    h_cnt = d_blk_cnt.copy_to_host()
    total = int(h_cnt.sum())

    if total == 0:
        return {"null_count": null_count, "min": None, "max": None, "mean": None}

    return {
        "null_count": null_count,
        "min": float(d_blk_min.copy_to_host().min()),
        "max": float(d_blk_max.copy_to_host().max()),
        "mean": float(d_blk_sum.copy_to_host().sum() / total),
    }


def _cpu_stats(values: np.ndarray, is_null: np.ndarray) -> dict:
    valid = values[~is_null]
    null_count = int(is_null.sum())
    if len(valid) == 0:
        return {"null_count": null_count, "min": None, "max": None, "mean": None}
    return {
        "null_count": null_count,
        "min": float(valid.min()),
        "max": float(valid.max()),
        "mean": float(valid.mean()),
    }


# ── Profiler node ─────────────────────────────────────────────────────────────

def profiler_node(state: dict) -> dict:
    raw_data = state.get("raw_data", [])
    raw_schema = state.get("raw_schema", {})
    audit_log = list(state.get("audit_log", []))

    n_rows = len(raw_data)
    use_gpu = _CUDA_AVAILABLE and n_rows >= GPU_THRESHOLD
    backend = "cuda" if use_gpu else "cpu"

    data_profile = {
        "row_count": n_rows,
        "backend": backend,
        "columns": {},
    }

    for col, dtype in raw_schema.items():
        col_profile: dict = {"type": dtype}

        if dtype in ("int", "float"):
            values, is_null = _to_float_array(raw_data, col)
            stats = _gpu_stats(values, is_null) if use_gpu else _cpu_stats(values, is_null)
            col_profile.update(stats)
        else:
            raw_vals = [row.get(col) for row in raw_data]
            col_profile["null_count"] = sum(1 for v in raw_vals if v is None or v == "")
            col_profile["unique_count"] = len(set(v for v in raw_vals if v is not None))

        data_profile["columns"][col] = col_profile

    audit_log.append({
        "timestamp": datetime.utcnow().isoformat(),
        "agent": "Profiler",
        "action": "profile",
        "summary": (
            f"Profiled {n_rows:,} rows × {len(raw_schema)} columns via {backend}."
        ),
    })

    return {
        "data_profile": data_profile,
        "audit_log": audit_log,
    }
