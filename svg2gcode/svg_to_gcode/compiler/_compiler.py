import os
import re
import logging
import math
import copy

from io import BytesIO
from typing import Any

import base64
import numpy as np

from svg2gcode.svg_to_gcode.compiler.interfaces import Interface
from svg2gcode.svg_to_gcode.geometry import Curve
from svg2gcode.svg_to_gcode.geometry import LineSegmentChain, Vector, RasterImage
from svg2gcode.svg_to_gcode import DEFAULT_SETTING
from svg2gcode.svg_to_gcode import TOLERANCES, SETTING, check_setting

from svg2gcode import __version__
from datetime import datetime
from PIL import Image

from image2gcode.boundingbox import Boundingbox
from image2gcode.image2gcode import Image2gcode

#logging.basicConfig(format="[%(levelname)s] %(message)s (%(name)s:%(lineno)s)")
logging.basicConfig(format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Compiler:
    """
    The Compiler class handles the process of drawing geometric objects using interface commands and assembling the
    resulting numerical control code.
    """

    def __init__(self, interface_class: Interface, custom_header: list[str] =None, custom_footer: list[str] =None,
                 params: dict[str, Any] = None):
        """

        :param interface_class: Specify which interface to use. The most common is the gcode interface.
        :param custom_header: A list of commands to be executed before all generated commands.
        :param custom_footer: A list of commands to be executed after all generated commands.
                              Default [laser_off, program_end]
        :param settings: dictionary to specify "unit", "pass_depth", "dwell_time", "movement_speed", etc.
        """
        self.svg_file_name = None
        self.boundingbox = Boundingbox()
        self.interface = interface_class()

        # Round outputs to the same number of significant figures as the operational tolerance.
        self.precision = abs(round(math.log(TOLERANCES["operation"], 10)))

        if params is None or not check_setting(params):
            raise ValueError(f"Please set at least 'maximum_laser_power' and 'movement_speed' from {SETTING}")

        # save params
        self.params = params
	      # get default settings and update
        self.settings = copy.deepcopy(DEFAULT_SETTING)
        for key in params.keys():
            self.settings[key] = params[key]

        self.interface.set_machine_parameters(self.settings)

        if custom_header is None:
            custom_header = []

        if custom_footer is None:
            custom_footer = [self.interface.laser_off(), self.interface.program_end()]

        self.header = [self.interface.code_initialize(),
                       self.interface.set_unit(self.settings["unit"]),
                       self.interface.set_distance_mode(self.settings["distance_mode"])] + custom_header
        self.footer = custom_footer

        # path object gcode
        self.body: list[str] = []
        # image gcode
        self.gcode: list[str] = []

    def gcode_file_header(self):

        gcode = []

        if not self.check_bounds():
            if self.settings["distance_mode"] == "absolute" and self.check_axis_maximum_travel():
                logger.warn("Cut is not within machine bounds.")
                gcode += ["; WARNING: Cut is not within machine bounds of "
                          f"X[0,{self.settings['x_axis_maximum_travel']}], Y[0,{self.settings['y_axis_maximum_travel']}]\n",]
            elif not self.check_axis_maximum_travel():
                # logger.warn("Please define machine cutting area, set parameter: 'x_axis_maximum_travel' and 'y_axis_maximum_travel'")
                gcode += ["; WARNING: Please define machine cutting area, set parameter: 'x_axis_maximum_travel' and 'y_axis_maximum_travel'\n",]
            else:
                gcode += [f"; WARNING: distance mode is not absolute: {self.settings['distance_mode']}\n",]

	# add generator info and boundingbox for this code

        # get program parameters
        params = ''
        for k, v in self.params.items():
            if params != '':
                params += f",\n"
            if hasattr(v, 'name'):
                params += f";      {k}: {os.path.basename(v.name)}"
            else:
                params += f";      {k}: {v}"

        center = self.boundingbox.center()
        gcode += [ f";    svg2gcode {__version__} ({str(datetime.now()).split('.')[0]})",
                   f";    arguments: \n{params}",
                   f";    {self.boundingbox}",
                   f";    boundingbox center: (X{center[0]:.{0 if center[0].is_integer() else self.precision}f},"
                   f"Y{center[1]:.{0 if center[1].is_integer() else self.precision}f})" ]

        gcode += [ f";    GRBL 1.1, unit={self.settings['unit']}, {self.settings['distance_mode']} coordinates" ]

        return '\n'.join(gcode) + '\n'

    def compile(self, passes=1):

        """
        Assembles the code in the header, body and footer.

        :param passes: the number of passes that should be made. Every pass the machine moves_down (z-axis) by
        self.pass_depth and self.body is repeated.
        :return returns the assembled code. self.header + [self.body, -self.pass_depth] * passes + self.footer
        """
        if len(self.body) == 0:
            logger.debug("Compile with an empty body (no curves).")
            return ''

        gcode = []
        for i in range(passes):
            gcode += [f"; pass #{i+1}"]
            gcode.extend(self.body)

            if i < (passes - 1) and self.settings["pass_depth"] > 0:
                # If it isn't the last pass, turn off the laser and move down
                gcode.append(self.interface.laser_off())
                gcode.append(self.interface.set_relative_coordinates())
                gcode.append(self.interface.linear_move(z=-self.settings["pass_depth"]))
                gcode.append(self.interface.set_distance_mode(self.settings["distance_mode"]))

        gcode += [self.interface.laser_off()]

        # remove all ""
        gcode = filter(lambda command: len(command) > 0, gcode)

        return '\n'.join(gcode)

    def compile_images(self):

        """
        Assembles the code in the header, body and footer.
        """

        # laser off, fan on, M3 or M4 burn mode
        header_gc = ["M5","M8", 'M3' if self.settings["laser_mode"] == "constant" else 'M4']
        # laser off, fan off
        footer_gc = ["M5","M9"]

        return '\n'.join(header_gc + self.gcode + footer_gc)

    def compile_to_file(self, file_name: str, svg_file_name: str, curves: list[Curve], passes=1):
        """
        A wrapper for the self.compile method. Assembles the code in the header, body and footer, saving it to a file.

        :param file_name: the path to save the file.
        :param svg_file_name: the path to the original svg image.
        :param curves: SVG curves approximated by line segments.
        :param passes: the number of passes that should be made. Every pass the machine moves_down (z-axis) by
        self.pass_depth and self.body is repeated.
        """
        self.svg_file_name = svg_file_name

	# generate gcode for 'path' and 'image' svg tags (calculate bbox)
        self.append_curves(curves)

        header = '\n'.join(self.header) + '\n'

        if len(self.body) > 0:
            # write path objects
            with open(file_name, 'w') as file:
                emit_program_end = self.interface.program_end() if (self.settings["splitfile"] or len(self.gcode) == 0) else ""
                file.write(self.gcode_file_header() + header + self.compile(passes=passes) + '\n' + emit_program_end)
                logger.info(f"Generated {file_name}")
        else:
            logger.warn(f'No path (curve) data found, skipping "{file_name}"')

        image_file_name = file_name.rsplit('.',1)[0] + "_images." + file_name.rsplit('.',1)[1]
        if len(self.gcode) == 0:
            logger.warn(f'No image found, skipping "{image_file_name}"')
        else:
            if self.settings["splitfile"]:
                # emit image objects to <filename>_images.<gcext>
                with open(image_file_name, 'w') as file:
                    file.write(self.gcode_file_header() + header +  self.compile_images() + '\n' + self.interface.program_end() + '\n')
                    logger.info(f"Generated {image_file_name}")
            else:
                # emit images objects in same file
                open_mode = 'w' if len(self.body) == 0 else 'a+'
                with open(file_name, open_mode) as file:
                    file.write((self.gcode_file_header() if len(self.body) == 0 else "") + '\n' +  self.compile_images() + '\n' + self.interface.program_end() + '\n')
                    logger.info(f"Added image(s) to {file_name}")

    def append_line_chain(self, line_chain: LineSegmentChain):
        """
        Draws a LineSegmentChain by calling interface.linear_move() for each segment. The resulting code is appended to
        self.body
        """

        if line_chain.chain_size() == 0:
            logger.warn("Attempted to parse empty LineChain")
            return

        code = []
        start = line_chain.get(0).start

	      # Move to the next line_chain when the next line segment doesn't connect to the end of the previous one.
        if self.interface.position is None or abs(self.interface.position - start) > TOLERANCES["operation"]:
            if self.interface.position is None or self.settings["rapid_move"]:
                # move to the next line_chain: set laser off, rapid move to start of chain,
                # set movement (cutting) speed, set laser mode and power on
                code = [self.interface.laser_off(), self.interface.rapid_move(start.x, start.y),
                        self.interface.set_movement_speed(self.settings["movement_speed"]),
                        self.interface.set_laser_mode(self.settings["laser_mode"]), self.interface.set_laser_power_value(self.settings["laser_power"])]

                self.boundingbox.update(start)
            else:
                # move to the next line_chain: set laser mode, set laser power to 0 (cutting is off),
                # set movement speed, (no rapid) move to start of chain, set laser to power
                code = [self.interface.set_laser_mode(self.settings["laser_mode"]), self.interface.set_laser_power_value(0),
                        self.interface.set_movement_speed(self.settings["movement_speed"]), self.interface.linear_move(start.x, start.y),
                        self.interface.set_laser_power_value(self.settings["laser_power"])]

            if self.settings["dwell_time"] > 0:
                code = [self.interface.dwell(self.settings["dwell_time"])] + code

        for line in line_chain:
            code.append(self.interface.linear_move(line.end.x, line.end.y))
            # update bounding box
            self.boundingbox.update(line.end)

        self.body.extend(code)

    def isBase64(self, b64str):
        try:
            base64.b64decode(b64str)
            return True
        except Exception as e:
            return False

    def decode_base64(self, base64_string):
        """
        Get base64 image from either embedded data or file.
        :param base64_string: xlink:href field from SVG document
        """
        img_file = ''

        # note: file names (including path) do not have (re): '<>:;,*|\"' characters,
        #       base64 data has only '([A-Za-z0-9+/]{4})*' (multiples of 4 ended by '='
        #       character padding). So, char ':' which is part of either prefix, makes
        #       a match possible.

        # strip either 'file:...' or 'data:...' prefix (MIME part) from field 'xlink:href'
        is_link = not base64_string.startswith('data')
        fileordata = re.sub("(^file://|^data:[a-z0-9;/]+,)","", base64_string, flags=re.I)

        # if os.path.isfile(fileordata):
        if is_link:
            if fileordata.startswith(os.path.curdir):
                img_file = os.path.join(os.path.dirname(self.svg_file_name), fileordata)
            else:
                img_file = fileordata
            if not os.path.isfile(img_file):
                logger.error("Unable to find image : %s", img_file)
                return

        elif self.isBase64(fileordata):
            # convert to right form
            imgdata = base64.b64decode(fileordata)

            # open as binary file
            img_file = BytesIO(imgdata)
        else:
            # Neither file nor data
            logger.error("Unable to read image data: %s", base64_string[:30])
            return

        return Image.open(img_file)

    # convert a MIME base64 image image string
    def convert_image(self, image:str, img_attrib: dict[str, Any]):

        # get svg image attributes info or default
        pixelsize = img_attrib['gcode_pixelsize'] if 'gcode_pixelsize' in img_attrib else self.settings["pixel_size"]

        # convert image from base64 string
        img = self.decode_base64(image)

        # convert image to new size
        if img is not None:
            # add alpha channel
            img = img.convert("RGBA")

            # create a white background and add it to the image
            img_background = Image.new(mode = "RGBA", size = img.size, color = (255,255,255))
            img = Image.alpha_composite(img_background, img)

            # Note that the image resize action below is based on the following:
            # - the image data (linked file or embedded) has a certain source resolution (number of pixels WidthxHeight)
            # - image attributes 'width' and 'height' are in user units
            # - user units are default (Inkscape, others?) set to be mm (1 user unit is 1 mm)
            # - make sure this is the case (Inkscape: check the document settings and look at the 'scaling' parameter)
            # - if this is the case, we have images attributes 'width' and 'height' in mm
            # - so, for a given pixelsize, we need a 'width'/pixelsize x 'height'/pixelsize resolution to get to the correct
            #   width and height in mm after 'width' steps (same for height in the other direction)
            #   (note that the image conversion algorithm takes these steps)
            # - note that the source resolution does not seem to be taken into account and (so) does not matter.
            #   generally that is the case when the result of the calculation above results in downsampling of the source image
            #   (make it lower resolution), if the calculation results in upsampling of the source image (make it higher resolution)
            #   it does make a difference because the resized image can be blocky

            # convert image to black&white (without alpha) and new size)'
            img = img.resize((int(float(img_attrib['width'])/float(pixelsize)),
                            int(float(img_attrib['height'])/float(pixelsize))), Image.Resampling.LANCZOS).convert("L")

            if self.settings['showimage']:
                img.show()

            # convert to nparray for fast handling
            return np.array(img)

        return None

    def distance(self, A: (float,float),B: (float,float)):
        """
        Pythagoras
        """
        # |Ax - Bx|^2 + |Ay - By|^2 = C^2
        # distance = √C^2
        return math.sqrt(abs(A[0] - B[0])**2 + abs(A[1] - B[1])**2)

    def image2gcode(self, img_attrib: dict[str, Any], img=None, transformation = None):

        # create image conversion object
        convert = Image2gcode(transformation = transformation.apply_affine_transformation if transformation is not None else None)

        #
        # set arguments

        # get svg image attribute/object info (set in Inkscape for example) when available
        # else set tool invocation values
        arguments = {}
        arguments["pixelsize"] = img_attrib['gcode_pixelsize'] if 'gcode_pixelsize' in img_attrib else self.settings["pixel_size"]
        arguments["maxpower"] = img_attrib['gcode_maxpower'] if 'gcode_maxpower' in img_attrib else self.settings["maximum_image_laser_power"]
        arguments["poweroffset"] = img_attrib['gcode_poweroffset'] if 'gcode_poweroffset' in img_attrib else self.settings["image_poweroffset"]
        arguments["speed"] = img_attrib['gcode_speed'] if 'gcode_speed' in img_attrib else self.settings["image_movement_speed"]
        arguments["noise"] = img_attrib['gcode_noise'] if 'gcode_noise' in img_attrib else self.settings["image_noise"]
        arguments["speedmoves"] = img_attrib['gcode_speedmoves'] if 'gcode_speedmoves' in img_attrib else self.settings["rapid_move"]
        arguments["overscan"] = img_attrib['gcode_overscan'] if 'gcode_overscan' in img_attrib else self.settings["image_overscan"]
        arguments["showoverscan"] = img_attrib['gcode_showoverscan'] if 'gcode_showoverscan' in img_attrib else self.settings["image_showoverscan"]
        arguments["offset"] = (float(img_attrib['x']), float(img_attrib['y']))
        arguments["name"] = img_attrib['id']

        # get image parameters
        params = ''
        for k, v in arguments.items():
            if params != '':
                params += f",\n"
            params += f";      {k}: {v}"

        self.gcode += [f"; image:\n{params}"]

        # get gcode for image
        self.gcode += [convert.image2gcode(img, arguments)]

        # update bounding box info
        bbox_image = convert.bbox.get()
        self.boundingbox.update(bbox_image[0])
        self.boundingbox.update(bbox_image[1])

    def append_curves(self, curves: list[Curve]):
        """
        Draws curves.
        """
        for curve in curves:
            if isinstance(curve, RasterImage):
                # curve is 'image', draw it

                # convert image (scale and type)
                img = self.convert_image(curve.image, curve.img_attrib)

                if img is not None:
                    # Draw image by converting raster image scan lines to gcode, possibly applying tranformations on each pixel
                    self.image2gcode(curve.img_attrib, img, curve.transformation)
            else:
                # curve is 'path', draw it
                # Draws curves by approximating them as line segments and calling self.append_line_chain().
                # The resulting code is appended to self.body
                line_chain = LineSegmentChain()
                approximation = LineSegmentChain.line_segment_approximation(curve)
                line_chain.extend(approximation)
                self.append_line_chain(line_chain)

    def check_axis_maximum_travel(self):
        return self.settings["x_axis_maximum_travel"] is not None and self.settings["y_axis_maximum_travel"] is not None
        # logger.warn("Please define machine cutting area, set parameter: 'x_axis_maximum_travel' and 'y_axis_maximum_travel'")

    def check_bounds(self):
        """
        Check if line segments are within the machine cutting area. Note that machine coordinate mode must
        be absolute and machine parameters 'x_axis_maximum_travel' and 'y_axis_maximum_travel' are set, also
        bounding box must be in the positive quadrant.
        :return true when box is in machine area bounds, false otherwise
        """

        if self.settings["distance_mode"] == "absolute" and self.check_axis_maximum_travel():
            machine_max = Vector(self.settings["x_axis_maximum_travel"],self.settings["y_axis_maximum_travel"])
            bbox = self.boundingbox.get()
            # bbox[0] == lowerleft, bbox[1] == uperright, bbox[0/1][0] == x, bbox[0/1][1] == y
            #      lower left x and y >= 0 and upperright x and y <= resp. machine max x and y
            return (bbox[0][0] >= 0 and bbox[0][1] >=0
                    and bbox[1][0] * (25.4 if self.settings["unit"] == "inch" else 1) <= machine_max.x
                    and bbox[1][1] * (25.4 if self.settings["unit"] == "inch" else 1) <= machine_max.y)

        return False
