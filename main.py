import rasterio
from rasterio.plot import show

def load_raster(path):
    with rasterio.open(path) as src:
        print(f"Coordinates: {src.crs}")
        print(f"Bounds: {src.bounds}")
        return src.read(1), src.transform

data, transform = load_raster('data/raw/viirs_data.tif')