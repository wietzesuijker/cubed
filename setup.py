import setuptools

REQUIRED_PACKAGES = [
    "dask[array]",
    "fsspec",
    "gcsfs",
    "networkx",
    "rechunker",
    "yarl",
    "zarr",
]

setuptools.setup(
    name="barry",
    version="0.0.1",
    install_requires=REQUIRED_PACKAGES,
    packages=setuptools.find_packages(),
)