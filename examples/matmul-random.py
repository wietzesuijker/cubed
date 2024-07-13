import logging

import cubed
import cubed.array_api as xp
import cubed.random
from cubed.extensions.history import HistoryCallback
from cubed.extensions.rich import RichProgressBar
from cubed.extensions.timeline import TimelineVisualizationCallback

# suppress harmless connection pool warnings
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

if __name__ == "__main__":
    spec = cubed.Spec(allowed_mem="8GB")
    # 200MB chunks
    a = cubed.random.random((50000, 50000), chunks=(5000, 5000), spec=spec)
    b = cubed.random.random((50000, 50000), chunks=(5000, 5000), spec=spec)
    c = xp.astype(a, xp.float32)
    d = xp.astype(b, xp.float32)
    e = xp.matmul(c, d)

    progress = RichProgressBar()
    hist = HistoryCallback()
    timeline_viz = TimelineVisualizationCallback()
    # use store=None to write to temporary zarr
    cubed.to_zarr(
        e,
        store=None,
        callbacks=[progress, hist, timeline_viz],
    )