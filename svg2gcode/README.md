# svg2gcode

A commandline steering program that enables laser cutting of svg drawings```<svg:path ..>tags``` and combined engraving of svg images```<svg:image ..>tags```.
It is based on library SvgToGcode (*fork*: https://github.com/johannesnoordanus/SvgToGcode) which should be installed <sup>(*)</sup>.

Drawings and images can be composed using Inkscape (for example) and saved to a .svg file. This file can be converted to gcode by svg2gcode.
Gcode produced in this way has the advantage that drawings and images have the same - relative - position and orientation as can be seen on the composer window.
This makes combined cutting and engraving as easy as orientating the (wood) slab once.

Controlling laser power, pixel size and other settings can be done via commandline parameters (see below) or within Inkscape using the XMLeditor.
Image attributes ```gcode_pixelsize```, ```gcode_maxpower``` and ```gcode_speed``` can be set per object (they must be created: use **+**). Note that this overrides explicit or default commandline settings.

**Tip**: use commandline program grblhud (https://github.com/johannesnoordanus/grblhud) to have full control over gcode execution.  




### Install:
```
> 
> pip install svg2gcode
```
<sup>(*)</sup> Note that library *svg_to_gcode* is included in this package. 
### Usage:
See notes below.
```
$ svg2gcode --help
usage: svg2gcode.py [-h] [--showimage] [--pixelsize <default:0.1>] [--imagespeed <default:800>] [--cuttingspeed <default:1000>] [--imagepower <default:300>]
                    [--cuttingpower <default:0.85>] [--maxlaserpower <default:1000>] [--rapidmove] [--xmaxtravel <default:300>] [--ymaxtravel <default:400>] [--fan] [-V]
                    svg gcode

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
                        maximum laser power while drawing an image (as a rule of thumb set to 1/3 of the machine maximum)
  --cuttingpower <default:0.85>
                        percentage of maximum laser power for line drawings/cutting
  --maxlaserpower <default:1000>
                        maximum laser power of laser cutter
  --rapidmove           generate inbetween G0 moves
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
  > svg2gcode ambachtmanlogo.svg logo.gc
  > ..
  > ls *.gc 
  > logo.gc             # all drawings
  > logo_images.gc      # all images
```   
 - drawing objects - within the composer - must be converted to a```path```to be translated to a gcode sequence
 - also, image objects should **not** be converted a ```path```
