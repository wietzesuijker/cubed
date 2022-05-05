import fsspec
import numpy as np
import pytest
import zarr
from numpy.testing import assert_array_equal
from rechunker.executors.python import PythonPipelineExecutor

import barry as xp
from barry.rechunker_extensions.executors.beam import (
    BeamDagExecutor,
    BeamPipelineExecutor,
)
from barry.tests.utils import create_zarr


@pytest.fixture()
def spec(tmp_path):
    return xp.Spec(tmp_path, max_mem=100000)


@pytest.fixture(
    scope="module",
    params=[PythonPipelineExecutor(), BeamDagExecutor(), BeamPipelineExecutor()],
)
def executor(request):
    return request.param


# Test API


def test_asarray(spec, executor):
    a = xp.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9]], chunks=(2, 2), spec=spec)
    assert_array_equal(
        a.compute(executor=executor), np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    )


def test_ones(spec, executor):
    a = xp.ones((3, 3), chunks=(2, 2), spec=spec)
    assert_array_equal(a.compute(executor=executor), np.ones((3, 3)))


def test_add(spec, executor):
    a = xp.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9]], chunks=(2, 2), spec=spec)
    b = xp.asarray([[1, 1, 1], [1, 1, 1], [1, 1, 1]], chunks=(2, 2), spec=spec)
    c = xp.add(a, b)
    assert_array_equal(
        c.compute(executor=executor), np.array([[2, 3, 4], [5, 6, 7], [8, 9, 10]])
    )


def test_equal(spec, executor):
    a = xp.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9]], chunks=(2, 2), spec=spec)
    b = xp.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9]], chunks=(2, 2), spec=spec)
    c = xp.equal(a, b)
    assert_array_equal(c.compute(executor=executor), np.full((3, 3), True))


def test_negative(spec, executor):
    a = xp.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9]], chunks=(2, 2), spec=spec)
    b = xp.negative(a)
    assert_array_equal(
        b.compute(executor=executor),
        np.array([[-1, -2, -3], [-4, -5, -6], [-7, -8, -9]]),
    )


def test_all(spec, executor):
    a = xp.asarray(
        [[True, True, True], [True, True, True], [True, True, True]],
        chunks=(2, 2),
        spec=spec,
    )
    b = xp.all(a)
    assert_array_equal(
        b.compute(executor=executor),
        np.array([[True, True, True], [True, True, True], [True, True, True]]).all(),
    )


def test_outer(spec, executor):
    a = xp.asarray([0, 1, 2], chunks=2, spec=spec)
    b = xp.asarray([10, 50, 100], chunks=2, spec=spec)
    c = xp.outer(a, b)
    assert_array_equal(c.compute(executor=executor), np.outer([0, 1, 2], [10, 50, 100]))


def test_matmul(spec, executor):
    a = xp.asarray(
        [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]],
        chunks=(2, 2),
        spec=spec,
    )
    b = xp.asarray(
        [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]],
        chunks=(2, 2),
        spec=spec,
    )
    c = xp.matmul(a, b)
    x = np.array([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]])
    y = np.array([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]])
    expected = np.matmul(x, y)
    assert_array_equal(c.compute(executor=executor), expected)


@pytest.mark.cloud
def test_matmul_cloud(executor):
    tmp_path = "gs://barry-zarr-test/matmul"
    spec = xp.Spec(tmp_path, max_mem=100000)
    try:
        a = xp.asarray(
            [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]],
            chunks=(2, 2),
            spec=spec,
        )
        b = xp.asarray(
            [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]],
            chunks=(2, 2),
            spec=spec,
        )
        c = xp.matmul(a, b)
        x = np.array([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]])
        y = np.array([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]])
        expected = np.matmul(x, y)
        assert_array_equal(c.compute(executor=executor), expected)
    finally:
        fs = fsspec.open(tmp_path).fs
        fs.rm(tmp_path, recursive=True)


def test_permute_dims(spec, executor):
    a = xp.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9]], chunks=(2, 2), spec=spec)
    b = xp.permute_dims(a, (1, 0))
    assert_array_equal(
        b.compute(executor=executor),
        np.transpose(np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])),
    )


def test_squeeze_1d(spec, executor):
    a = xp.asarray([[1, 2, 3]], chunks=(1, 2), spec=spec)
    b = xp.squeeze(a, 0)
    assert_array_equal(b.compute(executor=executor), np.squeeze([[1, 2, 3]], 0))


def test_squeeze_2d(spec, executor):
    a = xp.asarray([[[1], [2], [3]]], chunks=(1, 2, 1), spec=spec)
    b = xp.squeeze(a, (0, 2))
    assert_array_equal(
        b.compute(executor=executor), np.squeeze([[[1], [2], [3]]], (0, 2))
    )


def test_sum(spec, executor):
    a = xp.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9]], chunks=(2, 2), spec=spec)
    b = xp.sum(a)
    assert_array_equal(
        b.compute(executor=executor), np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]]).sum()
    )


def test_sum_axis_0(spec, executor):
    a = xp.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9]], chunks=(2, 2), spec=spec)
    b = xp.sum(a, axis=0)
    assert_array_equal(b.compute(executor=executor), np.array([12, 15, 18]))


# Other


def test_regular_chunks(spec):
    a = xp.ones((5, 5), chunks=((2, 2, 1), (5,)), spec=spec)
    a.compute()
    with pytest.raises(ValueError):
        a = xp.ones((5, 5), chunks=((2, 1, 2), (5,)), spec=spec)
        a.compute()


def test_from_zarr(tmp_path, spec, executor):
    store = store = tmp_path / "source.zarr"
    create_zarr(
        [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
        chunks=(2, 2),
        store=store,
    )
    a = xp.from_zarr(store, spec=spec)
    assert_array_equal(
        a.compute(executor=executor), np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    )


def test_to_zarr(tmp_path, spec, executor):
    a = xp.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9]], chunks=(2, 2), spec=spec)
    output = tmp_path / "output.zarr"
    xp.to_zarr(a, output, executor=executor)
    res = zarr.open(output)
    assert_array_equal(res[:], np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]]))


def test_map_blocks_with_kwargs(spec, executor):
    # based on dask test
    a = xp.asarray([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], chunks=5, spec=spec)
    b = xp.map_blocks(np.max, a, axis=0, keepdims=True, dtype=a.dtype, chunks=(1,))
    assert_array_equal(b.compute(executor=executor), np.array([4, 9]))


def test_multiple_ops(spec, executor):
    a = xp.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9]], chunks=(2, 2), spec=spec)
    b = xp.asarray([[1, 1, 1], [1, 1, 1], [1, 1, 1]], chunks=(2, 2), spec=spec)
    c = xp.add(a, b)
    d = xp.negative(c)
    assert_array_equal(
        d.compute(executor=executor),
        np.array([[-2, -3, -4], [-5, -6, -7], [-8, -9, -10]]),
    )


def test_compute_is_idempotent(spec, executor):
    a = xp.ones((3, 3), chunks=(2, 2), spec=spec)
    b = xp.negative(a)
    assert_array_equal(b.compute(executor=executor), -np.ones((3, 3)))
    assert_array_equal(b.compute(executor=executor), -np.ones((3, 3)))


def test_default_spec(executor):
    # default spec works for small computations
    a = xp.ones((3, 3), chunks=(2, 2))
    b = xp.negative(a)
    assert_array_equal(
        b.compute(executor=executor),
        -np.ones((3, 3)),
    )


def test_default_spec_max_mem_exceeded():
    # default spec fails for large computations
    a = xp.ones((100000, 100000), chunks=(10000, 10000))
    with pytest.raises(ValueError):
        xp.negative(a)


def test_reduction_multiple_rounds(tmp_path, executor):
    spec = xp.Spec(tmp_path, max_mem=110)
    a = xp.ones((100, 10), dtype=np.uint8, chunks=(1, 10), spec=spec)
    b = xp.sum(a, axis=0)
    assert_array_equal(b.compute(executor=executor), np.ones((100, 10)).sum(axis=0))