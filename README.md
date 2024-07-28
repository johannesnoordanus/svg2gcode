# svg2gcode

*svg2gcode* is a *WYSIWYG* converter of Scalable Vector Graphic *(SVG)* drawings. It is based on library *SvgToGcode* (*fork*: *https://github.com/johannesnoordanus/SvgToGcode*)<sup>(*)</sup>.

Drawings and images can be composed using Inkscape (or other *SVG* image software), saved to a *.svg* file and - *WYSIWYG* - converted to gcode.
Color coding can be used to mark what part(s) of the drawing to cut, engrave or even ignore.

Raster elements within a *SVG* drawing are converted pixel perfect, vector elements are drawn at the specified resolution.
Vector elements are converted including line width, fill and color, but note that colors (including alpha-channel) are converted to black and white.
(This is because laser engravings resemble black and white images.)
This means that it is possible to make laser engravings of text (fonts) and other drawing elements or even the entire vector drawing.

You have full control of placing (locating) of the gcode end result. You can for example translate, scale, rotate and have the origin at the image center.
*svg2gcode* produces highly optimised and accurate *gcode*. *gcode* file length is relatively short (because codes and coordinates are emitted sparsely) and laser drawing is sped up by speed moves and skipping of all empty parts.

More info can be obtained by looking at the documentation and examples below and the documentation of *image2gcode* (for example about calibration of laser engravers).

*svg2gcode* has three related programs: *image2gcode* mentioned above has similar capabilities but handles raster image files (like *png* and *jpg*) directly, *gcode2image* performs the inverse function and is capable of showing multiple writes (burns) to the same location and last *grblhud* which gives full control over gcode execution.

 -----

Please consider supporting me, so I can make this application better and add new functionality to it: <http://paypal.me/johannesnoordanus/5,00>

My next update will add *fill-rule* 'nonzero' (see information on *fill-rule* below).

<sup>(*)</sup> Note that an upgraded and corrected version of this library is included. 
### Supported SVG elements and attributes

*SVG* *path* and *image* elements (specific: ```<svg:path ..>```tags and images```<svg:image ..>```tags) are supported. Other drawing objects must be converted to a *path* first to be able to translate them to a gcode sequence.

Attributes *stroke* (color), *stroke-width*, *stroke_alpha*, *fill* (color), *fill-rule*, *fill_alpha* are supported.
Currently only value *evenodd* of *fill-rule* is supported.

### Important Commandline options

Option ```--color_coded``` can be used to specify what part(s) of the drawing to cut, engrave or even ignore. 
For example:
```
> svg2gcode --color_coded "black = ignore red = cut blue = engrave" paws.svg paws.gc
```
As a consequence all 'black' path elements will be ignored and will not appear after conversion, all red paths will be cut and all blue paths will be engraved (having color blue). 
The corresponding gcode file contains lines like below to indicated which 'black path' is skipped:
```
;    svg2gcode 3.2.8 (2024-07-28 11:39:27)
;    arguments:
;      laser_power: 850,
;      movement_speed: 1000,
...
;      image_showoverscan: False,
;      color_coded: black = ignore red = cut blue = engrave
;    Boundingbox: (X0.8,Y0.0:X5.1,Y4.3)
;    boundingbox center: (X2.951648,Y2.148172)
;    GRBL 1.1, unit=mm, absolute coordinates

; Machine settings:
;    rapid movement,
...
;    XY plane,
;    cutter compensation off,
;    coordinate system 1,
;    move 'unit'/min
G0 G17 G40 G54 G94

G21
G90
; pass #1

; --color_coded: ignore path 'path304-9-2-9-41-7', color '#000000'
```
Note that it doesn't matter if a specific color action is set but no corresponding path exits.
Note that multiple collors can be set per 'action': 
```
> svg2gcode --color_coded "black = ignore red = cut green = ignore blue = engrave orange = engrave yellow = cut" paws.svg paws.gc
```
Note that engraving is the default action, so if option *color_coded* isn't set or *color_coded* has no engrave color set, all paths having no other action set will be engraved (but see below). 

This makes it possible to make a drawing where all path elements are drawn in their respective colors to make an engraving of the entire vector drawing.
When you set the engrave action for a set of colors, only those colors will be engraved (having their respective colors), all other paths having no action set are ignored.
Also, when a path has no stroke attribute (or it is set to none) the element cannot be engraved (because it has no color) so it is interpreted as a cut action.

Option ```--pathcut``` can be used to override all stroke attributes and force cutting of all *paths* of the *SVG*.
Note that this option cannot be set at the same time as *--color_coded* above.

Option ```--nofill``` makes it possible to disable all path fills.
Options ```--origin --rotate --scale --selfcenter``` can be used to locate and transform the gcode image.
Option ```--speedmoves``` makes it possible to run engravings significantly faster and skip from one image zone to the other at maximum speed.
Option ```--noise``` suppresses stray pixels

Controlling laser power, pixel size and other settings can be done via commandline parameters but also via the following attributes (which can be set within the *.svg* file directly or within Inkscape using the XMLeditor):
```gcode_pixelsize```, ```gcode_maxpower```, ```gcode_speed```, ```gcode_noise```, ```gcode_speedmoves```, ```gcode_overscan``` and ```gcode_showoverscan``` can be set per vector element. (Image attributes can be added within the XMLeditor (Inkscape) by using the **+**).
Note that these attributes override explicit or default commandline settings.

### gcode optimizations

Optimized gcode
- draw pixels in one go until change of power
- emit X/Y coordinates only when they change
- emit linear move 'G1/G0' code minimally
- does not emit zero power (or below cutoff) pixels

General optimizations
- laser head has deferred and sparse moves.
(XY locations are virtual, head does not always follow)
- moves at high speed (G0) over 10mm (default) or more zero pixels
- low burn levels (stray pixels) can be suppressed (default off)
- default --constantburn mode *gcode M3*
- borders are drawn in parallel and in one go, following the *path* coordinates.
- fill has support for alpha channel and 'fill-opacity'
 

### Install:
```
> 
> pip install svg2gcode
```
Some linux distributions use a managed environment in which you cannot install python packages at will. Distribution Debian 12 and Manjaro have this limitation. You can setup a python *venv* and pip install *svg2gcode* in that or you can install systemwide using pipx:
```
> 
> pipx install svg2gcode
```

### Usage:
```
> svg2gcode --help
usage: runsvg2gcode [-h] [--showimage] [--selfcenter] [--pixelsize <default:0.1>] [--imagespeed <default:800>] [--cuttingspeed <default:1000>] [--imagepower <default:300>]
                    [--poweroffset <default:0>] [--cuttingpower <default:850>] [--passes <default:1>] [--pass_depth <default:0>] [--rapidmove <default:10>]
                    [--noise <default:0>] [--overscan <default:0>] [--showoverscan] [--constantburn | --no-constantburn] [--origin delta-x delta-y] [--scale factor-x factor-y]
                    [--rotate <default:0>] [--splitfile] [--pathcut] [--nofill] [--xmaxtravel <default:300>] [--ymaxtravel <default:400>] [--color_coded <default:"">] [--fan]
                    [-V]
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
  --constantburn, --no-constantburn
                        default constant burn mode (M3)
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
  --color_coded <default:"">
                        set action for path with specific stroke color "[color = [cut|engrave|ignore] *]*", example: --color_coded "black = ignore purple = cut blue = engrave"
  --fan                 set machine fan on
  -V, --version         show version number and exit
```

#### Configuration file:
You can also store svg2gcode settings in configuration file `~/.config/svg2gcode.toml` eg:

```
xmaxtravel= 400
ymaxtravel= 400
imagespeed = 6000
color_coded = "black = ignore purple = cut blue = engrave"
```
It can be used with any parameter which takes a value, and allows to persist your laser settings.
You can create this configuration file using an editor like vi or nano.
An alternative (quick) way to do that is to enter:
```
$ mkdir ~/.config
$ echo "xmaxtravel= 400
ymaxtravel= 400
imagespeed = 6000
color_coded = \"black = ignore purple = cut blue = engrave\"
" > ~/.config/svg2gcode.toml
```
(but use your own settings!)

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
Use *gcode2image* to get an accurate representation of the gcode when run on a lasercutter.
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
  
or add *svg2gcode* option *--pathcut* to override all path stroke attributes within the SVG document or use option *--color_coded* and set a cut action for the stroke color.

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

### Burn mode M3/M4:

Default *svg2gcode* uses constant burn mode *M3*. This can be changed by setting option *--no-constantburn* which selects burn mode *M4*. Mode *M4* is not suitable for engravings because it automatically compensates (laser)power for speed. This conflicts with the specific gcode settings given by *image2gcode* (called by *svg2gcode*) for each pixel. In fact some experiments show that *M4* causes loss of quality and image deterioration when speed is increased. On white oak images had too much black and grey which did not go away for substantially higher speed. When switched back to constant burn (*M3*) mode, the same high speed gave excellent images having a sepia (licht yellow brown) color tone.

### Notes:
 - drawing objects - within the composer - must be converted to a```path```to be translated to a gcode sequence
 - also, image objects should **not** be converted to a ```path```
 - images must be linked or embedded using base64.
 - images can be in several formats (my tests included *.png* and  *.jpg* image files)
 - SVG source documents must be in unit 'mm' (and set to 1 'user unit' is 1 mm) which is the default for Inkscape (check document settings and look at the 'scaling' parameter)
