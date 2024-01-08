# svg2gcode

A commandline steering program that enables laser cutting of svg drawings```<svg:path ..>```tags and combined engraving of svg images```<svg:image ..>```tags.
It is based on library *SvgToGcode* (*fork*: *https://github.com/johannesnoordanus/SvgToGcode*)<sup>(*)</sup>.

Drawings and images can be composed using Inkscape (or other SVG image software) and saved to a *.svg* file. This file can then be converted to gcode by *svg2gcode*.
Gcode produced in this way has the advantage that drawings and images have the same - relative - position and orientation as can be seen on the composer window.
This makes combined cutting and engraving as easy as orientating the (wood) slab once.

SVG *path* and *image* objects are supported. Note that other drawing object must be converted to a *path* to be able to translate them to a gcode sequence.
Recently (version 3.0.0 and higher) support for *stroke* color and *stroke-width* attributes of SVG *path* objects is added.
This means that it is possible to make laser engravings of text (fonts) and other drawing objects having a border with a specific color.
It is even possible to use alpha channel for these drawing objects now.

Controlling laser power, pixel size and other settings can be done via commandline parameters (see below) or within Inkscape using the XMLeditor.
Image attributes ```gcode_pixelsize```, ```gcode_maxpower```, ```gcode_speed```, ```gcode_noise```, ```gcode_speedmoves```, ```gcode_overscan``` and ```gcode_showoverscan``` can be set per object.
(Image attributes can be added within the XMLeditor (Inkscape) by using the **+**).
Note that image attributes override explicit or default commandline settings.

You have full control of placing (locating) of the result gcode via options *--origin*, <i>--rotate</i> and *--scale*.
Option *--selfcenter* can be used to set the origin at the center of the image.
Note that gcode file headers contain compile information like the boundingbox and boundingbox center coordinates.

Version 2.0.0 and higher have important speed optimizations. Engravings run significantly faster and skip from one image zone to the other at maximum speed.
See options ```--speedmoves``` and ```--noise``` for example.

Version 3.0.0 and higher have support for 'stroke' (color) and 'stroke-width' attributes, this means that cutting a path works a bit different now. 
When the *stroke* attribute of a *path* is nonexistent or set to none, the path will be laser burned with the value set by option *--cuttingpower*.

Version 3.1.0 and higher have support for 'fill' (color) and 'fill-rule' attributes. Currently only fill rule 'evenodd' is supported.

Also, *svg2gcode* option ```--pathcut``` can be used to override all stroke attributes and force cutting of all *paths* of the SVG.
Option ```--nofill``` (not set by default) is added to disable path fills.

More info can be obtained by looking at the examples below and from program *image2gcode* and its documentation (for example about callibrating laser engravers).  
 
Please consider supporting me, so I can make this application better and add new functionality to it: <http://paypal.me/johannesnoordanus/5,00>

My next update will add fill-rule 'nonzero'.


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
- borders are drawn in parallel and in one go, following the *path* coordinates.
- fill has support for alpha channel and 'fill-opacity'
 
**Tip**: use commandline program *grblhud* *(https://github.com/johannesnoordanus/grblhud)* to have full control over gcode execution,
also, program *image2gcode* has similar capabilities but handles raster images files (like *png* and *jpg*) directly. 

**Tip2**: another program *LaserWeb* (not made by me) is quite capable and has an excelent 3D gcode visualizer, it is able to calculate 3D paths for CNC machines, including the bit diameter.

### Install:
```
> 
> pip install svg2gcode
```
<sup>(*)</sup> Note that an upgraded and corrected version of this library is included. 
### Usage:
```
> svg2gcode --help
usage: svg2gcode [-h] [--showimage] [--selfcenter] [--pixelsize <default:0.1>] [--imagespeed <default:800>] [--cuttingspeed <default:1000>] [--imagepower <default:300>]
                    [--poweroffset <default:0>] [--cuttingpower <default:850>] [--passes <default:1>] [--pass_depth <default:0>] [--rapidmove <default:10>] [--noise <default:0>]
                    [--overscan <default:0>] [--showoverscan] [--constantburn] [--origin delta-x delta-y] [--scale factor-x factor-y] [--rotate <default:0>] [--splitfile] [--pathcut]
                    [--xmaxtravel <default:300>] [--ymaxtravel <default:400>] [--fan] [-V]
                    svg gcode

Convert svg to gcode for GRBL v1.1 compatible diode laser engravers.

positional arguments:
  svg                   svg file to be converted to gcode
  gcode                 gcode output file

options:
  -h, --help            show this help message and exit
  --showimage           show b&w converted image
  --selfcenter          self center the gcode (--origin cannot be used at the same time)
  --pixelsize <default:0.1>
                        pixel size in mm (XY-axis): each image pixel is drawn this size
  --imagespeed <default:800>
                        image draw speed in mm/min
  --cuttingspeed <default:1000>
                        cutting speed in mm/min
  --imagepower <default:300>
                        maximum laser power while drawing an image (as a rule of thumb set to 1/3 of the machine maximum for a 5W laser)
  --poweroffset <default:0>
                        pixel intensity to laser power: shift power range [0-imagepower]
  --cuttingpower <default:850>
                        sets laser power of line (path) cutting
  --passes <default:1>  Number of passes (iterations) for line drawings, only active when pass_depth is set
  --pass_depth <default:0>
                        cutting depth in mm for one pass, only active for passes > 1
  --rapidmove <default:10>
                        generate G0 moves between shapes, for images: G0 moves when skipping more than 10mm (default), 0 is no G0 moves
  --noise <default:0>   reduces image noise by not emitting pixels with power lower or equal than this setting
  --overscan <default:0>
                        overscan image lines to avoid incorrect power levels for pixels at left and right borders, number in pixels, default off
  --showoverscan        show overscan pixels (note that this is visible and part of the gcode emitted!)
  --constantburn        use constant burn mode M3 (a bit more dangerous!), instead of dynamic burn mode M4
  --origin delta-x delta-y
                        translate origin by vector (delta-x,delta-y) in mm (default not set, option --selfcenter cannot be used at the same time)
  --scale factor-x factor-y
                        scale svg with (factor-x,factor-y) (default not set)
  --rotate <default:0>  number of degrees to rotate
  --splitfile           split gcode output of SVG path and image objects
  --pathcut             alway cut SVG path objects! (use laser power set with option --cuttingpower)
  --nofill              ignore SVG fill attribute
  --xmaxtravel <default:300>
                        machine x-axis lengh in mm
  --ymaxtravel <default:400>
                        machine y-axis lengh in mm
  --fan                 set machine fan on
  -V, --version         show version number and exit
```

You can also store those settings in `~/.config/svg2gcode.toml`, eg:

```
xmaxtravel= 400
ymaxtravel= 400
imagespeed = 6000
```

It can be used with any parameter which takes a value, and alows to persist your laser settings.

### Examples:
#### Cutting a SVG *path* element:

The svg below draws a triangle
```
    > cat line_hoek.svg
    <?xml version="1.0" encoding="UTF-8" standalone="no"?>
    <!-- Created with Inkscape (http://www.inkscape.org/) -->
    <svg
        height="80"
        width="80"
        xmlns="http://www.w3.org/2000/svg"
        xmlns:svg="http://www.w3.org/2000/svg">
        <path
            id="driehoek"
            style="fill:none;stroke:#A0A0A0;stroke-width:.1"
            d="M50 0 L25 60 L75 60 Z" />
    </svg>
    
    > svg2gcode --showimage line_hoek.svg line_hoek.gc
```
This generates gcode file *line_hoek.gc* (and shows the result in a separate viewer).
The first lines of the gcode file contain comment lines *;* as shown below.
```
    > head -n 25 line_hoek.gc
    ;    svg2gcode 3.0.0 (2023-12-03 12:11:58)
    ;    arguments: 
    ;      laser_power: 850,
    ;      movement_speed: 1000,
    ;      pixel_size: 0.1,
    ;      maximum_image_laser_power: 300,
    ;      image_movement_speed: 800,
    ;      fan: False,
    ;      rapid_move: 10,
    ;      showimage: True,
    ;      x_axis_maximum_travel: 300,
    ;      y_axis_maximum_travel: 400,
    ;      image_noise: 0,
    ;      pass_depth: 0.0,
    ;      laser_mode: dynamic,
    ;      splitfile: False,
    ;      image_poweroffset: 0,
    ;      image_overscan: 0,
    ;      image_showoverscan: False
    ;    Boundingbox: (X25.0,Y20.0:X75.0,Y80.0)
    ;    boundingbox center: (X50,Y50)
    ;    GRBL 1.1, unit=mm, absolute coordinates

```
Use *gcode2image* to get an acurate representation of the gcode when run on a lasercutter.
```
    > gcode2image --showimage --flip --showorigin --grid --showG0 line_hoek.gc line_hoek.png
```
This will show gray lines (not black) because a low power (burn) level is used that represent color *#A0A0A0* from the *stroke* attribute within the *.svg* file:
```
    style="fill:none;stroke:#A0A0A0;stroke-width:.1"
```
So the conversion generates an engraving for the *.svg* and will not burn the lines with power set by *svg2gcode* option *--cuttingpower*.
The gcode after conversion will look like this:
```
    ; delta: 0
    M5
    G0 X50 Y80
    ; Cut at F1000 mm/min, power S112
    M4
    G1 X25 Y20 S112 F1000
    G1 X75
    G1 X50 Y80
    M5
    M2
```
Look at the power setting, it is S112 (which is low on a scale of 0 to 1000 which is the default)
Note: to get options and defaults:
```
    > svg2gcode --help
```
#### How do we cut these lines?
Change the *style* attribute line - within file *line_hoek.svg* - to the following:
```
    style="fill:none;stroke:none;stroke-width:.1"
```
or add 'gcode-pathcut' to the style string: 
```
    style="fill:none;stroke:red;stroke-width:.1;gcode-pathcut:true"
```
(Note that this makes it possible to selectively cut path objects within the SVG.)
  
or add *svg2gcode* option *--pathcut* to override all path stroke attributes within the SVG document

Run *svg2gcode* (with same options) again.
Now the gcode after conversion will look like this:
```
    ; delta: 0
    M5
    G0 X50 Y80
    ; Cut at F1000 mm/min, power S850
    M4
    G1 X25 Y20 S850 F1000
    G1 X75
    G1 X50 Y80
    M5
    M2
```
Note the power setting, it is S850 now. This is a burn setting!

To iterate this; make more passes, because that is often needed when cutting thicker material, run:
```
    > svg2gcode --showimage --passes 10 --pass_depth 0.05 line_hoek.svg line_hoek.gc
```
This will generate gcode that makes 10 passes and moves the Z-axis 0.05 mm down each pass.
So it will cut with a total depth of 5 mm.

Don't worry if your lasercutter has no Z-axis, because this parameter will be ignored and the burn will repeat (at the same height) as specified.

If you have a CNC machine (which does have a Z-axis) you can mill in depth (so to speak), but you can also add - or switch to - a laser head and use the gcode to be able to really laser cut deeper!

#### Create two types of gcode file
One containing the drawings of the .svg, the other containing the images:      
```
    > svg2gcode --splitfile ambachtmanlogo.svg logo.gc
    > ..
    > ls *.gc 
    > logo.gc             # all drawings
    > logo_images.gc      # all images
```   

### Notes:
 - drawing objects - within the composer - must be converted to a```path```to be translated to a gcode sequence
 - also, image objects should **not** be converted to a ```path```
 - images must be linked or embedded using base64.
 - images can be in several formats (my tests included *.png* and  *.jpg* image files)
 - SVG source documents must be in unit 'mm' (and set to 1 'user unit' is 1 mm) which is the default for Inkscape (check document settings and look at the 'scaling' parameter)
