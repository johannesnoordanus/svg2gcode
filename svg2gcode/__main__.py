"""
svg2gcode: convert an image to gcode.
"""

import os
import sys
try:
    import tomllib
except ImportError:
    try:
        import toml
    except ImportError:
        print("Import error: either 'toml' must be installed (pip install toml) or python version must be 3.11 or higher!")
        sys.exit(1)
import argparse

from svg2gcode.svg_to_gcode.svg_parser import parse_file
from svg2gcode.svg_to_gcode.compiler import Compiler, interfaces

from svg2gcode import __version__

config_file = os.path.expanduser('~/.config/svg2gcode.toml')

# Notes:
# - drawing objects (when using Inkscape for example) must be converted to a 'path' to be translated in a gcode sequence
# - images objects should NOT be converted a 'path'

def svg2gcode(args) -> int:
    """
    svg2gcode: convert svg to gcode
    """

    def init_compiler(args):
        # Instantiate a compiler, specifying the interface type and the speed at which the tool should move (for both image drawings and laser cutting).
        # For line drawings 'pass_depth' controls how far down the tool moves after every pass. Set it to 0 if your machine does not support Z axis movement.
        return Compiler(interfaces.Gcode, params={'laser_power':args.cuttingpower,'movement_speed':args.cuttingspeed, 'pixel_size':args.pixelsize,
               'maximum_image_laser_power':args.imagepower, 'image_movement_speed':args.imagespeed, 'fan':args.fan,'rapid_move':args.rapidmove,
               'showimage':args.showimage, 'x_axis_maximum_travel':args.xmaxtravel,'y_axis_maximum_travel':args.ymaxtravel, 'image_noise':args.noise,
               'pass_depth':args.pass_depth, 'laser_mode':"constant" if args.constantburn else "dynamic", 'splitfile':args.splitfile, 'pathcut':args.pathcut,
               'nofill':args.nofill, 'image_poweroffset':args.poweroffset, 'image_overscan':args.overscan, 'image_showoverscan':args.showoverscan})

    compiler = init_compiler(args)

    # emit gcode for svg
    if args.selfcenter:
        print("pass 1")
    compiler.compile_to_file(args.gcode, args.svg, parse_file(args.svg, delta_origin=args.origin, scale_factor=args.scale, rotate_deg=args.rotate), passes=args.passes)

    if args.selfcenter:
        # remove output files(s)
        filename = args.gcode

        if os.path.isfile(filename):
            os.remove(filename)
        image_filename = filename.rsplit('.',1)[0] + "_images." + filename.rsplit('.',1)[1]
        if os.path.isfile(image_filename):
            os.remove(image_filename)

        center = compiler.boundingbox.center()
        center = (round(center[0], compiler.precision), round(center[1], compiler.precision))
        print(f"center: {center}")
        center = (-center[0], -center[1])

        # init compiler again
        compiler = init_compiler(args)

        # now run with origin set to center
        # emit gcode for svg
        print("pass 2")
        compiler.compile_to_file(args.gcode, args.svg, parse_file(args.svg, delta_origin=center, scale_factor=args.scale, rotate_deg=args.rotate), passes=args.passes)
        center = compiler.boundingbox.center()
        center = (round(center[0], compiler.precision), round(center[1], compiler.precision))
        print(f"new center: {center}")

    return 0

def main() -> int:
    """
    main
    """
    # defaults
    cfg = {
        "pixelsize_default": 0.1,
        "imagespeed_default": 800,
        "cuttingspeed_default": 1000,
        "imagepower_default": 300,
        "poweroffset_default": 0,
        "cuttingpower_default": 850,
        "xmaxtravel_default": 300,
        "ymaxtravel_default": 400,
        "rapidmove_default": 10,
        "noise_default": 0,
        "overscan_default": 0,
        "pass_depth_default": 0,
        "passes_default": 1,
        "rotate_default": 0,
    }

    if os.path.exists(config_file):
        with open(config_file, 'rb') as f:
            cfg.update({k + '_default': v for k,v in tomllib.load(f).items()})

    # Define command line argument interface
    parser = argparse.ArgumentParser(description='Convert svg to gcode for GRBL v1.1 compatible diode laser engravers.')
    parser.add_argument('svg', type=str, help='svg file to be converted to gcode')
    parser.add_argument('gcode', type=str, help='gcode output file')
    parser.add_argument('--showimage', action='store_true', default=False, help='show b&w converted image' )
    parser.add_argument('--selfcenter', action='store_true', default=False, help='self center the gcode (--origin cannot be used at the same time)' )
    parser.add_argument('--pixelsize', default=cfg["pixelsize_default"], metavar="<default:" + str(cfg["pixelsize_default"])+">",
        type=float, help="pixel size in mm (XY-axis): each image pixel is drawn this size")
    parser.add_argument('--imagespeed', default=cfg["imagespeed_default"], metavar="<default:" + str(cfg["imagespeed_default"])+">",
        type=int, help='image draw speed in mm/min')
    parser.add_argument('--cuttingspeed', default=cfg["cuttingspeed_default"], metavar="<default:" + str(cfg["cuttingspeed_default"])+">",
        type=int, help='cutting speed in mm/min')
    parser.add_argument('--imagepower', default=cfg["imagepower_default"], metavar="<default:" +str(cfg["imagepower_default"])+ ">",
        type=int, help="maximum laser power while drawing an image (as a rule of thumb set to 1/3 of the machine maximum for a 5W laser)")
    parser.add_argument('--poweroffset', default=cfg["poweroffset_default"], metavar="<default:" +str(cfg["poweroffset_default"])+ ">",
        type=int, help="pixel intensity to laser power: shift power range [0-imagepower]")
    parser.add_argument('--cuttingpower', default=cfg["cuttingpower_default"], metavar="<default:" +str(cfg["cuttingpower_default"])+ ">",
        type=int, help="sets laser power of line (path) cutting")
    parser.add_argument('--passes', default=cfg["passes_default"], metavar="<default:" +str(cfg["passes_default"])+ ">",
        type=int, help="Number of passes (iterations) for line drawings, only active when pass_depth is set")
    parser.add_argument('--pass_depth', default=cfg["pass_depth_default"], metavar="<default:" + str(cfg["pass_depth_default"])+">",
        type=float, help="cutting depth in mm for one pass, only active for passes > 1")
    parser.add_argument('--rapidmove', default=cfg["rapidmove_default"], metavar="<default:" + str(cfg["rapidmove_default"])+ ">",
        type=int, help='generate G0 moves between shapes, for images: G0 moves when skipping more than 10mm (default), 0 is no G0 moves' )
    parser.add_argument('--noise', default=cfg["noise_default"], metavar="<default:" +str(cfg["noise_default"])+ ">",
        type=int, help='reduces image noise by not emitting pixels with power lower or equal than this setting')
    parser.add_argument('--overscan', default=cfg["overscan_default"], metavar="<default:" +str(cfg["overscan_default"])+ ">",
        type=int, help="overscan image lines to avoid incorrect power levels for pixels at left and right borders, number in pixels, default off")
    parser.add_argument('--showoverscan', action='store_true', default=False, help='show overscan pixels (note that this is visible and part of the gcode emitted!)' )
    parser.add_argument('--constantburn', action='store_true', default=False, help='use constant burn mode M3 (a bit more dangerous!), instead of dynamic burn mode M4')
    parser.add_argument('--origin', default=None, nargs=2, metavar=('delta-x', 'delta-y'),
        type=float, help="translate origin by vector (delta-x,delta-y) in mm (default not set, option --selfcenter cannot be used at the same time)")
    parser.add_argument('--scale', default=None, nargs=2, metavar=('factor-x', 'factor-y'),
        type=float, help="scale svg with (factor-x,factor-y) (default not set)")
    parser.add_argument('--rotate', default=cfg["rotate_default"], metavar="<default:" +str(cfg["rotate_default"])+ ">",
        type=int, help="number of degrees to rotate")
    parser.add_argument('--splitfile', action='store_true', default=False, help='split gcode output of SVG path and image objects' )
    parser.add_argument('--pathcut', action='store_true', default=False, help='alway cut SVG path objects! (use laser power set with option --cuttingpower)' )
    parser.add_argument('--nofill', action='store_true', default=False, help='ignore SVG fill attribute' )
    parser.add_argument('--xmaxtravel', default=cfg["xmaxtravel_default"], metavar="<default:" +str(cfg["xmaxtravel_default"])+ ">",
        type=int, help="machine x-axis lengh in mm")
    parser.add_argument('--ymaxtravel', default=cfg["ymaxtravel_default"], metavar="<default:" +str(cfg["ymaxtravel_default"])+ ">",
        type=int, help="machine y-axis lengh in mm")
    parser.add_argument('--fan', action='store_true', default=False, help='set machine fan on' )
    parser.add_argument('-V', '--version', action='version', version='%(prog)s ' + __version__, help="show version number and exit")

    args = parser.parse_args()

##    try:
    if args.origin is not None and args.selfcenter:
        print("options --selfcenter and --origin cannot be used at the same time, program abort")
        return 1

    return svg2gcode(args)
####    except KeyboardInterrupt:
##        print(f"svg2gcode aborted!")
##    except Exception as error:
##        print(error)
##
##    return 1

if __name__ == '__main__':
    sys.exit(main())
