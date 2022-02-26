# (Offline) Lake Bathymetry Scanning
This project aims to divide a lake area into several regions, optimize the region size and shape and use path planning to calculate a WGS 84 conform path. This is one step of my universities [RoBiMo project](https://tu-freiberg.de/en/robimo) to automatically scan the subsurface of a lake by a [boat drone](https://www.youtube.com/watch?v=8xZVimh9f-8).
See an example scan in 3D at [sketchfab.com](https://sketchfab.com/3d-models/riesenstein-scientific-diving-center-freiberg-5f30ea70c20e447eb5e121b51e5ae3f7)!

### Motivation & Conditions:

A small boat drone with a bathymetric scanner can only move a certain distance until its battery is empty and needs a refill.
Dividing the lake into regions with a defined number of tiles is one step. Rearranging the grid around every drone's start point by the DARP algorithm in used to find an optimal solution considered the distance of every tile inside the lake area.

After finding the optimal regions a path planning algorithm has to find a way with the lowest number of turns and the highest number of longest possible line segments. This way through every region will be exportable as [WGS 84 (EPSG:4326)](https://en.wikipedia.org/wiki/World_Geodetic_System) path for usage in automatic path finding programs.  


### DARP: Divide Areas Algorithm for Optimal Multi-Robot Coverage Path Planning

This is a fork of the [DARP Python Project](https://github.com/alice-st/DARP) with its Java source the original [DARP Java Project](https://github.com/athakapo/DARP).

Look up the original project for further details, how the algorithm works and all links.

## What to expect from this project

Here is an example of the DARP calculation as animation which shows the ongoing rearranging of tiles every 5th iteration before reaching the final result.

Start parameters have been:
 * lake [Talsperre Malter](https://wiwosm.toolforge.org/osm-on-ol/kml-on-ol.php?lang=de&uselang=de&params=50.921944444444_N_13.653055555556_E_dim%3A1000_region%3ADE-SN_type%3Awaterbody&title=Talsperre_Malter&secure=1&zoom=15&lat=50.92194&lon=13.65306&layers=B000000FTFT)
 * map size `(774, 552)` tiles (every tile's edge length is 3 meter)
 * `(63,217),(113,195),(722,326)` as initial positions meaning 3 drone start points
 * `[0.3, 0.2, 0.5]` have been the potions (_no fixed number of tiles yet_)
 * random influence: `0.0001`
 * criterion variation: `0.01 `
 * importance `False`

| Talsperre Malter DARP animation                                                 | Talsperre Malter result image                                 |
|---------------------------------------------------------------------------------|----------------------------------------------------------------|
| ![TalsperreMalter_DARP_animation.gif](media/TalsperreMalter_DARP_animation.gif) | ![TalsperreMalter_result.jpg](media/TalsperreMalter_result.jpg) |

| Example grid generation                                 |
|---------------------------------------------------------|
| ![TalsperreMalter_grid](media/TalsperreMalter_grid.jpg) |

## Work in Progress
- [x] fix DARP algorithm
- [x] get rid of the element-wise matrix manipulation loops by using numpy
- [x] make area input size dynamical
- [x] clear project of bloat / unused code and array generations
- [x] gridding of geospacial data of any given lake(area) into tiles with a defined edge length (using [geopandas](https://geopandas.org/en/stable/getting_started/introduction.html) and [shapely](https://shapely.readthedocs.io/en/stable/project.html)) and use as input for DARP
- [x] using python [multiprocessing](https://docs.python.org/3/library/multiprocessing.html) to speed up the grid generation
- [x] generate gif animation and video of calculation process
- [x] speed up DARP calculations by using [numba](https://numba.readthedocs.io/en/stable/index.html)
- [x] optimize (numba jitted) code
- [ ] take defined number of tiles per drone start point as input (keep alternative `portions`?)
- [ ] transformation of path planning way for every region to WGS 84 path
- [ ] divide area even further: create layers for inner and outer region inside lake area / rework gridding
- [ ] using multiple CPU cores to calculate different areas
- [ ] _(optional) build GUI for users to define areas and (number of) layers manually_