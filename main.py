import rasterio
from rasterio.mask import mask
import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
import osmnx as ox
import os
import requests
import folium
from folium.raster_layers import ImageOverlay

# conf
REGION_NAME = "Lesser Poland Voivodeship, Poland"
DATA_DIR = "data"
RAW_DIR = os.path.join(DATA_DIR, "raw")
REF_DIR = os.path.join(DATA_DIR, "reference")
PROC_DIR = os.path.join(DATA_DIR, "processed")

for d in [RAW_DIR, REF_DIR, PROC_DIR]:
    os.makedirs(d, exist_ok=True)

GEOJSON_PATH = os.path.join(REF_DIR, 'voivodeship_border.geojson')
RASTER_PATH = os.path.join(RAW_DIR, 'viirs_data.tif')
MAP_OUTPUT_PATH = os.path.join(PROC_DIR, 'interactive_astromap.html')
HEATMAP_PATH = os.path.join(PROC_DIR, 'static_heatmap.png')


# analytics

def get_boundaries():
    # getting region boundaries
    if not os.path.exists(GEOJSON_PATH):
        print(f"[*] Downloading boundaries for {REGION_NAME}...")
        gdf = ox.geocode_to_gdf(REGION_NAME)
        gdf.to_file(GEOJSON_PATH, driver='GeoJSON')
    return GEOJSON_PATH


def calculate_bortle_scale(radiance):
    # bortle scale
    if radiance < 0.1: return 1
    if radiance > 10.0: return 9
    return np.digitize(radiance, [0.1, 0.5, 1.5, 3.0, 5.0, 7.0, 10.0]) + 1


def get_elevation_for_points(points):
    # elevation for points
    elevations = []
    print(f"[*] Querying Elevation API for {len(points)} candidate spots...")
    for lat, lon in points:
        try:
            url = f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
            response = requests.get(url, timeout=5).json()
            elevations.append(response['elevation'][0])
        except Exception:
            elevations.append(0)  # defaul value
    return elevations


def process_raster_data(raster_path, geojson_path):
    borders = gpd.read_file(geojson_path)
    with rasterio.open(raster_path) as src:
        borders = borders.to_crs(src.crs)
        # raster clipping
        out_image, out_transform = mask(src, borders.geometry, crop=True)
        out_image[out_image < 0] = 0  # remove data < 0
        return out_image[0], out_transform


def find_optimal_sites(data, transform, top_n=15):
    # finding optimal sites
    masked_data = np.where(data > 0, data, np.inf)
    flat_indices = np.argsort(masked_data.ravel())[:top_n]
    rows, cols = np.unravel_index(flat_indices, data.shape)

    candidates = []
    coords = []
    for r, c in zip(rows, cols):
        lon, lat = rasterio.transform.xy(transform, r, c)
        coords.append((lat, lon))
        candidates.append({'lat': lat, 'lon': lon, 'radiance': data[r, c]})

    elevs = get_elevation_for_points(coords)

    for i in range(len(candidates)):
        candidates[i]['elevation'] = elevs[i]
        candidates[i]['score'] = (1 / (candidates[i]['radiance'] + 0.1)) * (candidates[i]['elevation'] / 100)

    # 5 best
    return sorted(candidates, key=lambda x: x['score'], reverse=True)[:5]


def create_visualizations(data, best_spots, transform):
    # heatmap
    plt.figure(figsize=(10, 8))
    plt.imshow(np.log1p(data), cmap='magma')
    plt.title(f"Light Pollution Profile: {REGION_NAME}")
    plt.axis('off')
    plt.savefig(HEATMAP_PATH, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[*] Static heatmap saved to {HEATMAP_PATH}")

    # interactive map
    m = folium.Map(location=[best_spots[0]['lat'], best_spots[0]['lon']], zoom_start=8, tiles="CartoDB dark_matter")

    #
    h, w = data.shape
    lon_min, lat_max = transform * (0, 0)
    lon_max, lat_min = transform * (w, h)
    folium_bounds = [[lat_min, lon_min], [lat_max, lon_max]]

    norm_data = np.log1p(data)
    if norm_data.max() > 0:
        norm_data = norm_data / norm_data.max()

    cmap = plt.get_cmap('magma')
    rgba_data = cmap(norm_data)
    rgba_data[..., 3] = np.where(data > 0, 0.6, 0)

    ImageOverlay(
        image=rgba_data,
        bounds=folium_bounds,
        opacity=0.8,
        name="Light Pollution Intensity",
        zindex=1
    ).add_to(m)

    # best places
    for i, spot in enumerate(best_spots, 1):
        bortle = calculate_bortle_scale(spot['radiance'])
        info = f"<b>Rank #{i}</b><br>Bortle: {bortle}<br>Alt: {spot['elevation']}m<br>Radiance: {spot['radiance']:.4f}"
        folium.Marker(
            [spot['lat'], spot['lon']],
            popup=folium.Popup(info, max_width=200),
            icon=folium.Icon(color='purple', icon='star', prefix='fa'),
            zindex_offset=1000
        ).add_to(m)

    folium.LayerControl().add_to(m)
    m.save(MAP_OUTPUT_PATH)
    print(f"[*] Interactive map with overlay saved to {MAP_OUTPUT_PATH}")


if __name__ == "__main__":
    try:
        print(f"=== AstroGIS: Analysis for {REGION_NAME} ===")

        boundary_file = get_boundaries()

        if not os.path.exists(RASTER_PATH):
            raise FileNotFoundError(f"Missing VIIRS data at {RASTER_PATH}. Please download it from NASA/EOG.")

        img_data, img_transform = process_raster_data(RASTER_PATH, boundary_file)

        top_sites = find_optimal_sites(img_data, img_transform)

        print("\n[RESULT] Recommended Observation Sites:")
        for idx, s in enumerate(top_sites, 1):
            print(
                f" {idx}. Lat: {s['lat']:.4f}, Lon: {s['lon']:.4f} | Alt: {s['elevation']}m | Bortle: {calculate_bortle_scale(s['radiance'])}")

        create_visualizations(img_data, top_sites, img_transform)

        print("\n[SUCCESS] Project completed successfully.")

    except Exception as e:
        print(f"\n[CRITICAL ERROR] {e}")