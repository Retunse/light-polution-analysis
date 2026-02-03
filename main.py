import rasterio
from rasterio.mask import mask
import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
import osmnx as ox

region_name = "Lesser Poland Voivodeship, Poland"
gdf = ox.geocode_to_gdf(region_name)
gdf.to_file("data/reference/voivodeship_border.geojson", driver='GeoJSON')

raster_path = 'data/raw/viirs_data.tif'
geojson_path = 'data/reference/voivodeship_border.geojson'
def process_light_pollution(raster_path, geojson_path, output_name='output_map.png'):
    borders = gpd.read_file(geojson_path)

    with rasterio.open(raster_path) as src:
        borders = borders.to_crs(src.crs)
        shapes = borders.geometry

        out_image, out_transform = mask(src, shapes, crop=True)

        out_image[out_image < 0] = 0
        data = out_image[0]

    v_bortle = np.vectorize(calculate_bortle_scale)
    bortle_map = v_bortle(data)

    plot_pollution_map(data, output_name)
    return bortle_map


def calculate_bortle_scale(radiance):
    if radiance < 0.1: return 1
    if radiance > 10.0: return 9
    return np.digitize(radiance, [0.1, 0.5, 1.5, 3.0, 5.0, 7.0, 10.0]) + 1


def plot_pollution_map(data, output_name):
    plt.figure(figsize=(12, 8))
    img = plt.imshow(np.log1p(data), cmap='magma')
    plt.colorbar(img, label='Light Intensity (Log1p Radiance)')
    plt.title('Urban Light Pollution Analysis')
    plt.axis('off')
    plt.savefig(output_name, dpi=300, bbox_inches='tight')
    plt.show()


def calculate_area_statistics(bortle_map):
    unique, counts = np.unique(bortle_map, return_counts=True)
    stats = dict(zip(unique, counts))

    total_pixels = sum(counts)

    print("--- Light Pollution Report ---")
    for level in range(1, 10):
        count = stats.get(level, 0)
        percentage = (count / total_pixels) * 100
        print(f"Bortle Class {level}: {percentage:.2f}% of area")

bortle_results = process_light_pollution(raster_path, geojson_path)
calculate_area_statistics(bortle_results)