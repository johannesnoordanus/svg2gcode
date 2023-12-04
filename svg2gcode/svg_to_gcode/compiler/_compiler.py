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
from svg2gcode.svg_to_gcode.geometry import LineSegmentChain, Line, Vector, RasterImage
from svg2gcode.svg_to_gcode import DEFAULT_SETTING
from svg2gcode.svg_to_gcode import TOLERANCES, SETTING, check_setting

from svg2gcode.svg_to_gcode import formulas
from svg2gcode.svg_to_gcode import css_color

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
            if self.settings["splitfile"]:
                logger.warn(f"No image found, skipping '{image_file_name}'")
            else:
                logger.warn(f"No image found in file '{svg_file_name}'")
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

    def orthogonal_offset(self, offset: float, line: Line) -> Line:

        def offset_direction(line: Line) -> (int,int):
            d_x = (line.end.x - line.start.x)
            d_y = (line.end.y - line.start.y)
            direction = (0,0)

            if d_x > 0 and d_y > 0:
                direction = (-1,1)
            elif d_x > 0 and d_y == 0:
                direction = (0,1)
            elif d_x < 0 and d_y == 0:
                direction = (0,-1)
            elif d_x < 0 and d_y < 0:
                direction = (1,-1)
            elif d_x == 0 and d_y < 0:
                direction = (1,0)
            elif d_x == 0 and d_y > 0:
                direction = (-1,0)
            elif d_x > 0 and d_y < 0:
                direction = (1,1)
            elif d_x < 0 and d_y > 0:
                direction = (-1,-1)

            return direction

        delta_sign = offset_direction(line)

        # calculate ortogonal line vector((0,0),(delta_x,delta_y)) of 'offset' length:
        # (1)  y = 1/slope * x
        #
        # of length offset:
        # (2)  x^2 + y^2                = offset^2     (Pythagoras)
        # (3)  x^2 + (1/slope * x)^2    = offset^2
        # (4)  (1 + (1/slope)^2) * x^2  = offset^2
        # (5)  x^2 = offset^2 / (1 + (1/slope)^2)

        if line.slope == 0:
            # vertical line
            delta_x = 0
            delta_y = delta_sign[1] * offset
        elif line.slope == 1:
            # horizontal line
            delta_x = delta_sign[0] * offset
            delta_y = 0
        else:
            # slope
            inv_slope = abs((1/line.slope))
            delta_x = round(math.sqrt((offset ** 2) / (1 + inv_slope ** 2)), self.precision)
            delta_y = round(inv_slope * delta_x, self.precision)

            # set right direction
            delta_x = delta_sign[0] * (-1 if (offset < 0) else 1) * delta_x
            delta_y = delta_sign[1] * (-1 if (offset < 0) else 1) * delta_y

        # add delta vector to line start and end vectors
        return Line(line.start + Vector(delta_x, delta_y), line.end + Vector(delta_x, delta_y), "offset")

    def append_line_chain(self, line_chain: LineSegmentChain, step: float, color: int = None):
        """
        Draws a LineSegmentChain by calling interface.linear_move() for each segment. The resulting code is appended to
        self.body
        """

        if line_chain.chain_size() == 0:
            logger.warn("Attempted to parse empty LineChain")
            return

        code = [f"\n; delta: {step}"]
        start = line_chain.get(0).start

        # set laser power to color value when svg attribute 'stroke' (color) is set
        laser_power = color if color is not None else self.settings["laser_power"]

	# Move to the next line_chain when the next line segment doesn't connect to the end of the previous one.
        if self.interface.position is None or abs(self.interface.position - start) > TOLERANCES["operation"]:
            if self.interface.position is None or self.settings["rapid_move"]:
                # move to the next line_chain: set laser off, rapid move to start of chain,
                # set movement (cutting) speed, set laser mode and power on
                code += [self.interface.laser_off(), self.interface.rapid_move(start.x, start.y),
                        self.interface.set_movement_speed(self.settings["movement_speed"]),
                        self.interface.set_laser_mode(self.settings["laser_mode"]), self.interface.set_laser_power_value(laser_power)]
            else:
                # move to the next line_chain: set laser mode, set laser power to 0 (cutting is off),
                # set movement speed, (no rapid) move to start of chain, set laser to power
                code += [self.interface.set_laser_mode(self.settings["laser_mode"]), self.interface.set_laser_power_value(0),
                        self.interface.set_movement_speed(self.settings["movement_speed"]), self.interface.linear_move(start.x, start.y),
                        self.interface.set_laser_power_value(laser_power)]

            self.boundingbox.update(start)

            if self.settings["dwell_time"] > 0:
                code += [self.interface.dwell(self.settings["dwell_time"])] + code

        for line in line_chain:
            code.append(self.interface.linear_move(line.end.x, line.end.y))
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

    def line_intersection(self, l1: Line, l2:Line) -> Vector:
        """
        Line intersection (https://en.wikipedia.org/wiki/Line–line_intersection)
        """
        x1, y1 = l1.start
        x2, y2 = l1.end
        x3, y3 = l2.start
        x4, y4 = l2.end

        # denomintor
        d = round((x1 - x2)*(y3 - y4) - (y1 - y2)*(x3 - x4), self.precision)

        # Note that the cutoff below is needed to eliminate line artifacts (spikes) of the render result.
        # This is due to calculation (precision) errors resulting in the y coordinate of the intersection to
        # be off by a factor (2,3, 10?). It might be that the rounding applied here is not correct, or/and
        # that the equations are inherently sensitive to rounding errors at certain inputs.
        # TODO: analize this
        if abs(d) < 0.01:
            # no intersection
            return None

        return Vector( round(((x1*y2 - y1*x2) * (x3 - x4) - (x1 - x2) * (x3*y4 - y3*x4))/d, self.precision),
                       round(((x1*y2 - y1*x2) * (y3 - y4) - (y1  - y2) * (x3*y4 - y3*x4))/d, self.precision) )

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

    def parse_style_attribute(self, curve: Curve) -> {}:
        """
        Parse style attribute.
        for example "fill:#F4CF84;fill-rule:evenodd;stroke:#D07735;"
        """

        style = {'fill' : None, 'fill-rule': None, 'stroke': None, 'stroke-width': None, 'pathcut': None}

        # parse style attribute

        if curve.path_attrib and 'style' in curve.path_attrib:
            style_str = curve.path_attrib['style']

            # parse fill
            if 'fill' in style_str:
                fill = re.search('fill:[^;]+;',style_str)
                if fill:
                    style['fill'] = fill.group(0)[5:-1]
            # parse fill-rule
            if 'fill-rule' in style_str:
                fill_rule = re.search('fill-rule:#(evenodd|nonzero)',style_str)
                if fill_rule:
                    style['fill-rule'] = re.search('(evenodd|nonzero)', fill_rule.group(0)).group(0)
            # parse stroke
            if 'stroke' in style_str:
                stroke = re.search('stroke:[^;]+;',style_str)
                if stroke:
                    style['stroke'] = stroke.group(0)[7:-1]
            # parse stroke-width
            if 'stroke-width' in style_str:
                stroke_width = re.search('stroke-width:(\d*\.)?\d+',style_str)
                if stroke_width:
                    style['stroke-width'] = re.search('(\d*\.)?\d+', stroke_width.group(0)).group(0)

            # parse pathcut
            if 'gcode-pathcut' in style_str:
                pathcut = re.search('gcode-pathcut:(true|false)',style_str)
                if pathcut:
                    style['pathcut'] = re.search('(true|false)', pathcut.group(0)).group(0)

        # parse other attributes

        # parse fill attribute
        if 'fill' in curve.path_attrib:
            style['fill'] = curve.path_attrib['fill']
        if 'fill-rule' in curve.path_attrib:
            style['fill-rule'] = curve.path_attrib['fill-rule']
        # parse stroke attribute
        if 'stroke' in curve.path_attrib:
            style['stroke'] = curve.path_attrib['stroke']
        # parse stroke-width attribute
        if 'stroke-width' in curve.path_attrib:
            style['stroke-width'] = curve.path_attrib['stroke-width']

        # parse gcode_pathcut attribute
        if 'gcode_pathcut' in curve.path_attrib:
            style['pathcut'] = curve.path_attrib['gcode_pathcut']

        return style

    def append_curves(self, curves: list[Curve]):
        """
        Draws curves.
        """
        path_curves = {}

        for curve in curves:
            if isinstance(curve, RasterImage):
                # curve is 'image', draw it

                # convert image (scale and type)
                img = self.convert_image(curve.image, curve.img_attrib)

                if img is not None:
                    # Draw image by converting raster image scan lines to gcode, possibly applying tranformations on each pixel
                    self.image2gcode(curve.img_attrib, img, curve.transformation)
            else:
                # curve is a 'path', approximate it (when needed) as line segments.
                # organize curves by 'name_id' to be able to apply fill/stroke color and
                # line width later on.

                curve_name_id = ""
                # parse id
                if curve.path_attrib:
                    curve_name_id = curve.path_attrib['id']

                if curve_name_id not in path_curves:
                    path_curves[curve_name_id] = []

                line_chain = LineSegmentChain()
                # approximate curve
                approximation = LineSegmentChain.line_segment_approximation(curve)
                line_chain.extend(approximation)

                # stitch chains when the next chain starts at the end of the previous chain
                if len(path_curves[curve_name_id]) and path_curves[curve_name_id][-1].get(-1).end == line_chain.get(0).start:
                    path_curves[curve_name_id][-1].extend(line_chain)
                else:
                    # add line segments to curves having this id
                    path_curves[curve_name_id].append(line_chain)

        # emit all paths (organized by name id)
        for name_id in path_curves:
            # for all line chains
            for line_chain in path_curves[name_id]:

                pixel_size = float(self.settings["pixel_size"])
                # default stroke width is one line (thickness)
                stroke_width = pixel_size

                first_line_of_chain = line_chain.get(0)

                width = 0
                stroke_color = ""
                style = self.parse_style_attribute(first_line_of_chain)
                if style:
                    if not (style['pathcut'] == 'true' or self.settings["pathcut"]) \
                        and style['stroke'] is not None and style['stroke'] != "none":
                        stroke_color = style['stroke']
                    if style['stroke-width'] is not None and style['stroke-width'] != "none":
                        stroke_width = float(style['stroke-width'])
                        width = int(round(stroke_width/pixel_size, self.precision))

                steps = [0]
                if len(stroke_color) and width:
                    for delta in range(width):
                        if delta:
                            steps.append(round(delta * pixel_size, self.precision))
                            if not (delta + 1 == width and width % 2 == 0):
                                steps.append(round(-delta * pixel_size, self.precision))

                for step in steps:
                    if step:
                        delta_chain = LineSegmentChain()

                        for line in line_chain:
                            line_delta = self.orthogonal_offset(step, line)

                            if delta_chain.chain_size():
                                # calculate intersection of previous line and current line
                                intersect = self.line_intersection(delta_chain.get(-1), line_delta)
                                large = 200
                                if intersect is not None:
                                    # set prev_line.end to intersect
                                    prev_line = delta_chain.get(-1)
                                    prev_line.end = intersect
                                    delta_chain.set(-1, prev_line)

                                    # set line_delta start to intersect
                                    line_delta.start = intersect
                                else:
                                    # connect line, to prevent ValueErrors from delta_chain.append() below
                                    line_delta.start = delta_chain.get(-1).end

                            delta_chain.append(line_delta)

                        # check if line chain is a loop
                        if line_chain.get(0).start == line_chain.get(-1).end:
                            # fix delta chain
                            intersect = self.line_intersection(delta_chain.get(0), delta_chain.get(-1))
                            if intersect is not None:
                                # update start of loop
                                start_loop = delta_chain.get(0)
                                start_loop.start = intersect
                                delta_chain.set(0, start_loop)

                                # update end of loop
                                end_loop = delta_chain.get(-1)
                                end_loop.end = intersect
                                delta_chain.set(-1, end_loop)

                        # linear_power(self, pixel: UInt8, maxpower: int, offset: int = 0, invert: bool = True) -> int
                        inverse_bw = Image2gcode.linear_power(css_color.parse_css_color2bw8(stroke_color), self.settings["maximum_image_laser_power"])
                        self.append_line_chain(delta_chain, step, inverse_bw)
                    else:
                        inverse_bw = Image2gcode.linear_power(css_color.parse_css_color2bw8(stroke_color), self.settings["maximum_image_laser_power"]) if len(stroke_color) else None
                        self.append_line_chain(line_chain, step, inverse_bw)

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
