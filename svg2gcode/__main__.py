"""
svg2gcode: convert an image to gcode.
"""

import sys
import argparse

from svg2gcode.svg_to_gcode.svg_parser import parse_file
from svg2gcode.svg_to_gcode.compiler import Compiler, interfaces

from svg2gcode import __version__

# Notes:
# - drawing objects (when using Inkscape for example) must be converted to a 'path' to be translated in a gcode sequence
# - images objects should NOT be converted a 'path'

def svg2gcode(args) -> int:
    """
    image2gcode: convert svg to gcode
    """
    try:
        # Instantiate a compiler, specifying the interface type and the speed at which the tool should move (for both image drawings and laser cutting).
        # For line drawings 'pass_depth' controls how far down the tool moves after every pass. Set it to 0 if your machine does not support Z axis movement.
        gcode_compiler = Compiler(interfaces.Gcode, params={'laser_power':args.cuttingpower,'movement_speed':args.cuttingspeed,
                            'maximum_laser_power':args.maxlaserpower,'pixel_size':args.pixelsize,'maximum_image_laser_power':args.imagepower,
                            'image_movement_speed':args.imagespeed,'fan':args.fan,'rapid_move':args.rapidmove,'showimage':args.showimage,
                            'x_axis_maximum_travel':args.xmaxtravel,'y_axis_maximum_travel':args.ymaxtravel})
        # emit gcode for svg
        gcode_compiler.compile_to_file(args.gcode, parse_file(args.svg), passes=1)

    except Exception as error:
        print(error)
        return 1

    return 0

def main() -> int:
    """
    main
    """
    # defaults
    pixelsize_default = 0.1
    imagespeed_default = 800
    cuttingspeed_default = 1000
    imagepower_default = 300
    cuttingpower_default = .85
    maxlaserpower_default = 1000
    xmaxtravel_default = 300
    ymaxtravel_default = 400

    # Define command line argument interface
    parser = argparse.ArgumentParser(description='Convert svg to gcode for GRBL v1.1 compatible diode laser engravers.')
    parser.add_argument('svg', type=str, help='svg file to be converted to gcode')
    parser.add_argument('gcode', type=str, help='gcode output file')
    parser.add_argument('--showimage', action='store_true', default=False, help='show b&w converted image' )
    parser.add_argument('--pixelsize', default=pixelsize_default, metavar="<default:" + str(pixelsize_default)+">",
        type=float, help="pixel size in mm (XY-axis): each image pixel is drawn this size")
    parser.add_argument('--imagespeed', default=imagespeed_default, metavar="<default:" + str(imagespeed_default)+">",
        type=int, help='image draw speed in mm/min')
    parser.add_argument('--cuttingspeed', default=cuttingspeed_default, metavar="<default:" + str(cuttingspeed_default)+">",
        type=int, help='cutting speed in mm/min')
    parser.add_argument('--imagepower', default=imagepower_default, metavar="<default:" +str(imagepower_default)+ ">",
        type=int, help="maximum laser power while drawing an image (as a rule of thumb set to 1/3 of the machine maximum)")
    parser.add_argument('--cuttingpower', default=cuttingpower_default, metavar="<default:" +str(cuttingpower_default)+ ">",
        type=int, help="percentage of maximum laser power for line drawings/cutting")
    parser.add_argument('--maxlaserpower', default=maxlaserpower_default, metavar="<default:" +str(maxlaserpower_default)+ ">",
        type=int, help="maximum laser power of laser cutter")
    parser.add_argument('--rapidmove', action='store_true', default=True, help='generate inbetween G0 moves' )
    parser.add_argument('--xmaxtravel', default=xmaxtravel_default, metavar="<default:" +str(xmaxtravel_default)+ ">",
        type=int, help="machine x-axis lengh in mm")
    parser.add_argument('--ymaxtravel', default=ymaxtravel_default, metavar="<default:" +str(ymaxtravel_default)+ ">",
        type=int, help="machine y-axis lengh in mm")
    parser.add_argument('--fan', action='store_true', default=False, help='set machine fan on' )
    parser.add_argument('-V', '--version', action='version', version='%(prog)s ' + __version__, help="show version number and exit")

    args = parser.parse_args()

    return svg2gcode(args)

if __name__ == '__main__':
    sys.exit(main())
