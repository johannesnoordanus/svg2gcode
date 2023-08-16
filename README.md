# svg2gcode

A commandline steering program that enables laser cutting of svg drawings```<svg:path ..>tags``` and combined engraving of svg images```<svg:image ..>tags```.
It is based on library SvgToGcode (*fork*: https://github.com/johannesnoordanus/SvgToGcode) which should be installed <sup>(*)</sup>.

Drawings and images can be composed using Inkscape (for example) and saved to a *.svg* file. This file can be converted to gcode by *svg2gcode*.
Gcode produced in this way has the advantage that drawings and images have the same - relative - position and orientation as can be seen on the composer window.
This makes combined cutting and engraving as easy as orientating the (wood) slab once.

Controlling laser power, pixel size and other settings can be done via commandline parameters (see below) or within Inkscape using the XMLeditor.
Image attributes ```gcode_pixelsize```, ```gcode_maxpower```, ```gcode_speed```, ```gcode_noise``` and ```gcode_speedmoves``` can be set per object (they must be created: use **+**). Note that this overrides explicit or default commandline settings.

You have full control over the coordinate system of the result gcode file via option *--origin* and *--scale*.
Note that gcode file headers contain compile information like the boundingbox and boundingbox center coordinates.
Tip: boundingbox center can be used to set the origin (via option *--origin*) at the center.

Version 2.0.0 and above have important new speed optimizations. Engravings run significantly faster and skip from one image zone to the other at maximum speed. See options ```--speedmoves``` and ```--noise``` for example.

To summarize:

Optimized gcode
- draw pixels in one go until change of power
- emit X/Y coordinates only when they change
- emit linear move 'G1/G0' code minimally
- does not emit zero power (or below cutoff) pixels

General optimizations
- laser head has defered and sparse moves.
(XY locations are virtual, head does not always follow)
- moves at high speed (G0) over 10mm (default) or more zero pixels
- low burn levels (stray pixels) can be suppressed (default off)
- option *--constantburn* selects constant burn mode *M3* (for cutting and engraving) instead of default dynamic burn mode *M4*
 
**Tip**: use commandline program *grblhud* *(https://github.com/johannesnoordanus/grblhud)* to have full control over gcode execution,
also, program *image2gcode* has similar capabilities but handles raster images files (like *png* and *jpg*) directly. 

### Install:
```
> 
> pip install svg2gcode
```
<sup>(*)</sup> Note that this library is included. 
### Usage:
See notes below.
```
$ svg2gcode --help
usage: svg2gcode [-h] [--showimage] [--pixelsize <default:0.1>] [--imagespeed <default:800>]
                 [--cuttingspeed <default:1000>] [--imagepower <default:300>] [--cuttingpower <default:850>]
                 [--rapidmove <default:10>] [--noise <default:0>] [--constantburn] [--origin Xdelta Ydelta]
                 [--scale Xfactor Yfactor] [--splitfile] [--xmaxtravel <default:300>] [--ymaxtravel <default:400>]
                 [--fan] [-V] svg gcode

Convert svg to gcode for GRBL v1.1 compatible diode laser engravers.

positional arguments:
  svg                   svg file to be converted to gcode
  gcode                 gcode output file

options:
  -h, --help            show this help message and exit
  --showimage           show b&w converted image
  --pixelsize <default:0.1>
                        pixel size in mm (XY-axis): each image pixel is drawn this size
  --imagespeed <default:800>
                        image draw speed in mm/min
  --cuttingspeed <default:1000>
                        cutting speed in mm/min
  --imagepower <default:300>
                        maximum laser power while drawing an image (as a rule of thumb set to 1/3 of the
                        machine maximum for a 5W laser)
  --cuttingpower <default:850>
                        sets laser power of line drawings/cutting
  --rapidmove <default:10>
                        generate G0 moves between shapes, for images: G0 moves when skipping more than 10mm
                        (default), 0 is no G0 moves
  --noise <default:0>   reduces image noise by not emitting pixels with power lower or equal than this setting
  --constantburn        use constant burn mode M3 (a bit more dangerous!), instead of dynamic burn mode M4
  --origin Xdelta Ydelta
                        translate origin by (Xdelta,Ydelta) (default not set)
  --scale Xfactor Yfactor
                        scale svg with (Xfactor,Yfactor) (default not set)
  --splitfile           split gcode output of SVG path and image objects
  --xmaxtravel <default:300>
                        machine x-axis lengh in mm
  --ymaxtravel <default:400>
                        machine y-axis lengh in mm
  --fan                 set machine fan on
  -V, --version         show version number and exit

```
### Notes:
  - example command to create two types of gcode file, one containing the drawings of the .svg, the other containing the images:      
```
  > svg2gcode --splitfile ambachtmanlogo.svg logo.gc
  > ..
  > ls *.gc 
  > logo.gc             # all drawings
  > logo_images.gc      # all images
```   
 - drawing objects - within the composer - must be converted to a```path```to be translated to a gcode sequence
 - also, image objects should **not** be converted to a ```path```
 - images must be linked or embedded using base64.
 - images can be in several formats (my tests included *.png* and  *.jpg* image files)


