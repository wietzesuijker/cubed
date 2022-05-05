import numbers
from functools import partial
from math import prod
from typing import Callable, Dict, NamedTuple

import numpy as np
from dask.array.core import normalize_chunks
from dask.blockwise import make_blockwise_graph
from dask.core import flatten
from dask.utils import cached_cumsum
from rechunker.api import _zarr_empty
from rechunker.types import ArrayProxy, Pipeline, Stage
from toolz import map

from barry.utils import to_chunksize

sym_counter = 0


def gensym(name):
    global sym_counter
    sym_counter += 1
    return f"{name}-{sym_counter:03}"


class BlockwiseSpec(NamedTuple):
    function: Callable
    reads_map: Dict[str, ArrayProxy]
    write: ArrayProxy


def apply_blockwise(graph_item, *, config=BlockwiseSpec):
    out_chunk_key, in_name_chunk_keys = graph_item
    args = []
    for name, in_chunk_key in in_name_chunk_keys:
        arg = np.asarray(config.reads_map[name].array[in_chunk_key])
        args.append(arg)
    config.write.array[out_chunk_key] = config.function(*args)


def get_item(chunks, idx):

    starts = tuple(cached_cumsum(c, initial_zero=True) for c in chunks)

    loc = tuple((start[i], start[i + 1]) for i, start in zip(idx, starts))
    return tuple(slice(*s, None) for s in loc)


def blockwise(
    func, out_ind, *args, max_mem, target_store, dtype, adjust_chunks=None, **kwargs
):
    """Apply a function across blocks from multiple source Zarr arrays.

    Parameters
    ----------
    func : callable
        Function to apply to individual tuples of blocks
    out_ind : iterable
        Block pattern of the output, something like 'ijk' or (1, 2, 3)
    *args : sequence of Array, index pairs
        Sequence like (x, 'ij', y, 'jk', z, 'i')
    max_mem : int
        Maximum memory allowed for a single task of this operation, measured in bytes
    target_store : string
        Path to output Zarr store
    dtype : np.dtype
        The ``dtype`` of the output array.
    adjust_chunks : dict
        Dictionary mapping index to function to be applied to chunk sizes
    **kwargs : dict
        Extra keyword arguments to pass to function

    Returns
    -------
    pipeline:  Pipeline to run the operation
    target:  ArrayProxy for the Zarr array output
    required_mem: minimum memory required per-task, in bytes
    """

    # Use dask's make_blockwise_graph, a lot of this is from dask's blockwise function
    arrays = args[::2]
    array_names = [f"in_{i}" for i in range(len(arrays))]
    array_map = {name: array for name, array in zip(array_names, arrays)}

    inds = args[1::2]

    arginds = zip(arrays, inds)

    numblocks = {}
    for name, array in zip(array_names, arrays):
        chunks = normalize_chunks(array.chunks, array.shape)
        numblocks[name] = tuple(map(len, chunks))

    argindsstr = []
    for name, ind in zip(array_names, inds):
        argindsstr.extend((name, ind))

    chunkss = {}
    # For each dimension, use the input chunking that has the most blocks;
    # this will ensure that broadcasting works as expected, and in
    # particular the number of blocks should be correct if the inputs are
    # consistent.
    for arg, ind in arginds:
        arg_chunks = normalize_chunks(
            arg.chunks, arg.shape, dtype=arg.dtype
        )  # have to normalize zarr chunks
        for c, i in zip(arg_chunks, ind):
            if i not in chunkss or len(c) > len(chunkss[i]):
                chunkss[i] = c
    chunks = [chunkss[i] for i in out_ind]
    if adjust_chunks:
        for i, ind in enumerate(out_ind):
            if ind in adjust_chunks:
                if callable(adjust_chunks[ind]):
                    chunks[i] = tuple(map(adjust_chunks[ind], chunks[i]))
                elif isinstance(adjust_chunks[ind], numbers.Integral):
                    chunks[i] = tuple(adjust_chunks[ind] for _ in chunks[i])
                elif isinstance(adjust_chunks[ind], (tuple, list)):
                    if len(adjust_chunks[ind]) != len(chunks[i]):
                        raise ValueError(
                            f"Dimension {i} has {len(chunks[i])} blocks, adjust_chunks "
                            f"specified with {len(adjust_chunks[ind])} blocks"
                        )
                    chunks[i] = tuple(adjust_chunks[ind])
                else:
                    raise NotImplementedError(
                        "adjust_chunks values must be callable, int, or tuple"
                    )
    chunks = tuple(chunks)
    shape = tuple(map(sum, chunks))

    graph = make_blockwise_graph(func, "out", out_ind, *argindsstr, numblocks=numblocks)

    # convert chunk indexes to chunk keys (slices)
    graph_mappable = []
    for k, v in graph.items():
        out_chunk_key = get_item(chunks, k[1:])
        name_chunk_keys = []
        name_chunk_inds = v[1:]  # remove func
        # flatten (nested) lists indicating contraction
        # note this only works for dimensions of size 1 (used for squeeze impl)
        if isinstance(name_chunk_inds[0], list):
            name_chunk_inds = list(flatten(name_chunk_inds))
            assert len(name_chunk_inds) == 1
        for name_chunk_ind in name_chunk_inds:
            name = name_chunk_ind[0]
            chunk_ind = name_chunk_ind[1:]
            arr = array_map[name]
            chks = normalize_chunks(
                arr.chunks, arr.shape, dtype=arr.dtype
            )  # have to normalize zarr chunks
            chunk_key = get_item(chks, chunk_ind)
            name_chunk_keys.append((name, chunk_key))
        graph_mappable.append((out_chunk_key, name_chunk_keys))

    # now use the graph_mappable in a pipeline

    chunksize = to_chunksize(chunks)
    target_array = _zarr_empty(shape, target_store, chunksize, dtype)

    func_with_kwargs = partial(func, **kwargs)
    read_proxies = {
        name: ArrayProxy(array, array.chunks) for name, array in array_map.items()
    }
    write_proxy = ArrayProxy(target_array, chunksize)
    spec = BlockwiseSpec(func_with_kwargs, read_proxies, write_proxy)
    stages = [
        Stage(
            apply_blockwise,
            gensym("apply_blockwise"),
            mappable=graph_mappable,
        )
    ]

    # calculate (minimum) memory requirement
    required_mem = np.dtype(dtype).itemsize * prod(chunksize)  # output
    for array in arrays:  # inputs
        required_mem += array.dtype.itemsize * prod(array.chunks)

    if required_mem > max_mem:
        raise ValueError(
            f"Blockwise memory ({required_mem}) exceeds max_mem ({max_mem})"
        )

    num_tasks = len(graph)

    return Pipeline(stages, config=spec), target_array, required_mem, num_tasks