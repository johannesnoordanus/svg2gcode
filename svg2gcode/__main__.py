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
    svg2gcode: convert svg to gcode
    """
    try:
        # Instantiate a compiler, specifying the interface type and the speed at which the tool should move (for both image drawings and laser cutting).
        # For line drawings 'pass_depth' controls how far down the tool moves after every pass. Set it to 0 if your machine does not support Z axis movement.
        gcode_compiler = Compiler(interfaces.Gcode, params={'laser_power':args.cuttingpower,'movement_speed':args.cuttingspeed, 'pixel_size':args.pixelsize,
                        'maximum_image_laser_power':args.imagepower, 'image_movement_speed':args.imagespeed, 'fan':args.fan,'rapid_move':args.rapidmove,
                        'showimage':args.showimage, 'x_axis_maximum_travel':args.xmaxtravel,'y_axis_maximum_travel':args.ymaxtravel, 'image_noise':args.noise,
                        'laser_mode':"constant" if args.constantburn else "dynamic", 'splitfile':args.splitfile})
        # emit gcode for svg
        gcode_compiler.compile_to_file(args.gcode, parse_file(args.svg, delta_origin=args.origin, scale_factor=args.scale), passes=1)

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
    cuttingpower_default = 850
    xmaxtravel_default = 300
    ymaxtravel_default = 400
    rapidmove_default = 10
    noise_default = 0

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
        type=int, help="maximum laser power while drawing an image (as a rule of thumb set to 1/3 of the machine maximum for a 5W laser)")
    parser.add_argument('--cuttingpower', default=cuttingpower_default, metavar="<default:" +str(cuttingpower_default)+ ">",
        type=int, help="sets laser power of line drawings/cutting")
    parser.add_argument('--rapidmove', default=rapidmove_default, metavar="<default:" +str(rapidmove_default)+ ">",
        type=int, help='generate G0 moves between shapes, for images: G0 moves when skipping more than 10mm (default), 0 is no G0 moves' )
    parser.add_argument('--noise', default=noise_default, metavar="<default:" +str(noise_default)+ ">",
        type=int, help='reduces image noise by not emitting pixels with power lower or equal than this setting')
    parser.add_argument('--constantburn', action='store_true', default=False, help='use constant burn mode M3 (a bit more dangerous!), instead of dynamic burn mode M4')
    parser.add_argument('--origin', default=None, nargs=2, metavar=('Xdelta', 'Ydelta'),
        type=float, help="translate origin by (Xdelta,Ydelta) (default not set)")
    parser.add_argument('--scale', default=None, nargs=2, metavar=('Xfactor', 'Yfactor'),
        type=float, help="scale svg with (Xfactor,Yfactor) (default not set)")
    parser.add_argument('--splitfile', action='store_true', default=False, help='split gcode output of SVG path and image objects' )
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
