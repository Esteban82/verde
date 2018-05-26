"""
Gridding with splines and weights
=================================

Biharmonic spline interpolation is based on estimating vertical forces acting
on an elastic sheet that yield deformations in the sheet equal to the observed
data. The results are equivalent to using :class:`verde.ScipyGridder` with
``method='cubic'`` but the interpolation is usually slower.
The advantage of using :class:`verde.Spline` is that you can assign weights to
the data to incorporate the data uncertainties or variance into the gridding.

In this example, we'll use :class:`verde.BlockMean` to decimate the data
because it can calculate weights based on the data uncertainty from input data
and pass it along to the spline.
"""
import matplotlib.pyplot as plt
from matplotlib.colors import PowerNorm
import cartopy.crs as ccrs
import cartopy.feature as cfeature
# We need these two classes to set proper ticklabels for Cartopy maps
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter
import pyproj
import numpy as np
import verde as vd

# We'll test this on the California vertical GPS velocity data because it comes
# with the uncertainties
data = vd.datasets.fetch_california_gps()
coordinates = (data.longitude.values, data.latitude.values)

# Use a Mercator projection for our Cartesian gridder
projection = pyproj.Proj(proj='merc', lat_ts=data.latitude.mean())

# Now we can chain a block weighted mean and weighted spline together. We'll
# use uncertainty propagation to calculate the new weights from block mean
# because our data vary smoothly but have different uncertainties.
spacing = 5/60   # 5 arc-minutes which we'll approximate to 5*111e3 meters
chain = vd.Chain([
    ('mean', vd.BlockMean(spacing=spacing*111e3, uncertainty=True)),
    ('spline', vd.Spline(damping=1e-10))])
print(chain)

# Weights need to 1/uncertainty**2 for the error propagation in BlockMean to
# work
chain.fit(projection(*coordinates), data.velocity_up, weights=1/data.std_up**2)

# Create a grid of the vertical velocity and mask it to only show points close
# to the actual data.
region = vd.get_region(coordinates)
grid = chain.grid(region=region, spacing=spacing, projection=projection,
                  dims=['latitude', 'longitude'], data_names=['velocity'])
mask = vd.distance_mask(np.meshgrid(grid.longitude, grid.latitude),
                        (data.longitude, data.latitude), maxdist=0.5)
grid = grid.where(~mask)


def setup_map(ax):
    "Set the proper ticks for a Cartopy map and draw land and water"
    ax.set_xticks(np.arange(-124, -115, 4), crs=crs)
    ax.set_yticks(np.arange(33, 42, 2), crs=crs)
    ax.xaxis.set_major_formatter(LongitudeFormatter())
    ax.yaxis.set_major_formatter(LatitudeFormatter())
    ax.set_extent(region, crs=crs)
    ax.add_feature(cfeature.LAND, facecolor='gray')
    ax.add_feature(cfeature.OCEAN)


fig, axes = plt.subplots(1, 2, figsize=(9, 7),
                         subplot_kw=dict(projection=ccrs.Mercator()))
crs = ccrs.PlateCarree()
# Plot the data uncertainties
ax = axes[0]
ax.set_title('Data uncertainty')
setup_map(ax)
# Plot the uncertainties in mm/yr and using a power law for the color scale to
# highlight the smaller values
pc = ax.scatter(*coordinates, c=data.std_up*1000, s=20, cmap='magma',
                transform=crs, norm=PowerNorm(gamma=1/2))
cb = plt.colorbar(pc, ax=ax, orientation='horizontal', pad=0.05)
cb.set_label('uncertainty [mm/yr]')
# Plot the gridded velocities
ax = axes[1]
ax.set_title('Spline interpolated vertical velocity')
setup_map(ax)
maxabs = np.max(np.abs([data.velocity_up.min(),
                        data.velocity_up.max()]))*1000
pc = ax.pcolormesh(grid.longitude, grid.latitude, grid.velocity*1000,
                   cmap='seismic', vmin=-maxabs, vmax=maxabs, transform=crs)
cb = plt.colorbar(pc, ax=ax, orientation='horizontal', pad=0.05)
cb.set_label('vertical velocity [mm/yr]')
ax.scatter(*coordinates, c='black', s=0.5, alpha=0.1, transform=crs)
ax.coastlines()
plt.tight_layout()
plt.show()