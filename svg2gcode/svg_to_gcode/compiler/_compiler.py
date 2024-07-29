import os
import re
import logging
import math
import copy

from io import BytesIO
from typing import Any

import base64
from datetime import datetime
from PIL import Image
import numpy as np

from svg2gcode.svg_to_gcode.compiler.interfaces import Interface
from svg2gcode.svg_to_gcode.geometry import Curve
from svg2gcode.svg_to_gcode.geometry import LineSegmentChain, Vector, RasterImage
from svg2gcode.svg_to_gcode import DEFAULT_SETTING
from svg2gcode.svg_to_gcode import TOLERANCES, SETTING, check_setting

from svg2gcode.svg_to_gcode import css_color

from svg2gcode import __version__

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
	# get default settings
        self.settings = copy.deepcopy(DEFAULT_SETTING)
        # and update
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
                params += ",\n"
            if hasattr(v, 'name'):
                params += f";      {k}: {os.path.basename(v.name)}"
            else:
                params += f";      {k}: {v}"

        gcode += [ f";    svg2gcode {__version__} ({str(datetime.now()).split('.')[0]})",
                   f";    arguments: \n{params}",]
        if self.boundingbox.get():
            center = self.boundingbox.center()
            gcode += [ f";    {self.boundingbox}",
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

    def append_line_chain(self, line_chain: LineSegmentChain, step: float, color: int = None, speed: int = None):
        """
        Draws a LineSegmentChain (path) by calling interface.linear_move() for each segment.
        The resulting code is appended to self.body

        :param line_chain: path to draw.
        :param step: path offset (indicates that this path is offset to another path).
        :param color: laser intensity, 'laser_power' when set to 'None'.
        :param speed: laser head movement speed, 'movement_speed' when set to 'None'.
        """

        if line_chain.chain_size() == 0:
            logger.warn("Attempted to parse empty LineChain")
            return

        code = [f"\n; delta: {step}"]
        start = line_chain.get(0).start

        # set laser power to color value when svg attribute 'stroke' (color) is set
        laser_power = color if color is not None else self.settings["laser_power"]
        movement_speed = speed if speed is not None else self.settings["movement_speed"]

	# Move to the next line_chain when the next line segment doesn't connect to the end of the previous one.
        if self.interface.position is None or abs(self.interface.position - start) > TOLERANCES["operation"]:
            if self.interface.position is None or self.settings["rapid_move"]:
                # move to the next line_chain: set laser off, rapid move to start of chain,
                # set movement (cutting) speed, set laser mode and power on
                code += [self.interface.laser_off(), self.interface.rapid_move(start.x, start.y),
                        self.interface.set_movement_speed(movement_speed),
                        self.interface.set_laser_mode(self.settings["laser_mode"]), self.interface.set_laser_power_value(laser_power)]
            else:
                # move to the next line_chain: set laser mode, set laser power to 0 (cutting is off),
                # set movement speed, (no rapid) move to start of chain, set laser to power
                code += [self.interface.set_laser_mode(self.settings["laser_mode"]), self.interface.set_laser_power_value(0),
                        self.interface.set_movement_speed(movement_speed), self.interface.linear_move(start.x, start.y),
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

    def image2gcode(self, img_attrib: dict[str, Any], img=None, transformation = None, power = None):

        # create image conversion object
        convert = Image2gcode(transformation = transformation.apply_affine_transformation if transformation is not None else None, power = power)

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
        arguments["invert"] = img_attrib['invert'] if 'invert' in img_attrib else False

        # get image parameters
        params = ''
        for k, v in arguments.items():
            if params != '':
                params += ",\n"
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

        style = {'fill' : None, 'fill-rule': None, 'fill-opacity': None, 'stroke': None, 'stroke-width': None, 'stroke-opacity': None, 'pathcut': None}

        # parse style attribute

        if curve.path_attrib and 'style' in curve.path_attrib:
            style_str = curve.path_attrib['style']

            # parse fill
            if 'fill' in style_str:
                fill = re.search('fill:[^;]+;',style_str)
                if fill:
                    fill_str = fill.group(0)[5:-1]
                    if fill_str != 'none':
                        style['fill'] = fill_str
            # parse fill-rule
            if 'fill-rule' in style_str:
                fill_rule = re.search('fill-rule:#(evenodd|nonzero)',style_str)
                if fill_rule:
                    style['fill-rule'] = re.search('(evenodd|nonzero)', fill_rule.group(0)).group(0)
            # parse fill-opacity
            if 'fill-opacity' in style_str:
                fill_opacity = re.search('fill-opacity:(\d*\.)?\d+',style_str)
                if fill_opacity:
                    style['fill-opacity'] = re.search('(\d*\.)?\d+', fill_opacity.group(0)).group(0)
            # parse stroke
            if 'stroke' in style_str:
                stroke = re.search('stroke:[^;]+;',style_str)
                if stroke:
                    stroke_str = stroke.group(0)[7:-1]
                    if stroke_str != 'none':
                        style['stroke'] = stroke_str
            # parse stroke-width
            if 'stroke-width' in style_str:
                stroke_width = re.search('stroke-width:(\d*\.)?\d+',style_str)
                if stroke_width:
                    style['stroke-width'] = re.search('(\d*\.)?\d+', stroke_width.group(0)).group(0)
            # parse stroke-opacity
            if 'stroke-opacity' in style_str:
                stroke_opacity = re.search('stroke-opacity:(\d*\.)?\d+',style_str)
                if stroke_opacity:
                    style['stroke-opacity'] = re.search('(\d*\.)?\d+', stroke_opacity.group(0)).group(0)

            # parse pathcut
            if 'gcode-pathcut' in style_str:
                pathcut = re.search('gcode-pathcut:(true|false)',style_str)
                if pathcut:
                    style['pathcut'] = re.search('(true|false)', pathcut.group(0)).group(0)

        # parse other attributes

        # parse fill attribute
        if 'fill' in curve.path_attrib:
            if curve.path_attrib['fill'] != 'none':
                style['fill'] = curve.path_attrib['fill']
        if 'fill-rule' in curve.path_attrib:
            style['fill-rule'] = curve.path_attrib['fill-rule']
        # parse fill-opacity
        if 'fill-opacity' in curve.path_attrib:
            fill_opacity = re.search('fill-opacity:(\d*\.)?\d+',curve.path_attrib)
            if fill_opacity:
                style['fill-opacity'] = re.search('(\d*\.)?\d+', fill_opacity.group(0)).group(0)
        # parse stroke attribute
        if 'stroke' in curve.path_attrib:
            stroke_str = curve.path_attrib['stroke']
            if stroke_str != 'none':
                style['stroke'] = stroke_str
        # parse stroke-width attribute
        if 'stroke-width' in curve.path_attrib:
            style['stroke-width'] = curve.path_attrib['stroke-width']
        # parse stroke-opacity attribute
        if 'stroke-opacity' in curve.path_attrib:
            style['stroke-opacity'] = curve.path_attrib['stroke-opacity']

        # parse gcode_pathcut attribute
        if 'gcode_pathcut' in curve.path_attrib:
            style['pathcut'] = curve.path_attrib['gcode_pathcut']

        return style

    def color_coded_paths(self, set_color_coded = False) -> ():
        """
        Get color_coded info
        Return string tuple (pathignore, pathcut, pathengrave)
        """
        pathignore = None
        pathcut = None
        pathengrave = None

        if self.settings["color_coded"]:
            color_code = self.settings["color_coded"]

            # get css color names
            colors = str([*css_color.css_color_keywords])
            colors = re.sub("(,|\[|\]|\'| )", '', colors.replace(",", "|"))

            # get ignore (do not draw) colors
            colors_ignore_regex = "((" + colors + ") *= *ignore)+"
            match = re.findall(colors_ignore_regex, color_code)
            pathignore = [i[1] for i in match]

            # get cut colors
            colors_cut_regex = "((" + colors + ") *= *cut)+"
            match = re.findall(colors_cut_regex, color_code)
            pathcut = [i[1] for i in match]

            # get engrave colors
            colors_engrave_regex = "((" + colors + ") *= *engrave)+"
            match = re.findall(colors_engrave_regex, color_code)
            pathengrave = [i[1] for i in match]

            if set_color_coded:
                cced = ""
                for i in pathignore:
                    cced += f"{i} = ignore "
                for i in pathcut:
                    cced += f"{i} = cut "
                for i in pathengrave:
                    cced += f"{i} = engrave "

                # set color_coded option string to the actual version
                self.settings["color_coded"] = cced
                self.params["color_coded"] = cced

        return (pathignore, pathcut, pathengrave)

    def parse_color_coded(self, stroke_color: str = None) -> ():
        """
        Parse option --color_coded
        Return tuple (ignorepath, cutpath, engravepath)
        """
        if self.settings["color_coded"]:

            ignorepath = False
            cutpath = False
            engravepath = False

            # Get colo_coded info
            pathignore, pathcut, pathengrave = self.color_coded_paths();

            for color in pathignore:
                if css_color.rgb24equal(css_color.parse_css_color(stroke_color), css_color.css_color_keywords[color]["decimal"]):
                    # stroke color is ignored (no path is drawn)
                    ignorepath = True
                    break

            if not ignorepath:
                # cut path if option --color_coded is selected and stroke_color == "red"
                for color in pathcut:
                    if css_color.rgb24equal(css_color.parse_css_color(stroke_color), css_color.css_color_keywords[color]["decimal"]):
                        cutpath = True
                        break

                if not cutpath:
                    for color in pathengrave:
                        if css_color.rgb24equal(css_color.parse_css_color(stroke_color), css_color.css_color_keywords[color]["decimal"]):
                            engravepath = True
                            break

        return (ignorepath, cutpath, engravepath)

    def append_curves(self, curves: list[Curve]):
        """
        Draws curves.
        """

        def line_slope(p1: (int,int), p2: (int,int)):
            """Calculate the slope of the line p1p2"""
            x1, y1 = p1[0], p1[1]
            x2, y2 = p2[0], p2[1]

            if x1 == x2:
                return 1

            return (y1 - y2) / (x1 - x2)

        def line_offset(p1: (int,int), p2: (int,int)):
            """Calculate the offset of the line p1p2 from the origin"""
            x1, y1 = p1[0], p1[1]

            return y1 - line_slope(p1, p2) * x1

        def lline(x, slope, offset):
            y = slope * x + offset
            return round(y)

        def draw(img, start: (int,int), end: (int,int), color):
            """
            Draws a line from - and including - start (x,y) to - and including - end (x,y).
            """
            slope = line_slope(start, end)
            offset = line_offset(start, end)

            if slope == 1 and ((start[0] - end[0]) != (start[1] - end[1])):
                # vertical line (not a 45 degrees line)
                diy = 1 if end[1] > start[1] else -1
                for y2 in range(start[1], end[1] + diy, diy):
                    img[y2,start[0]] = color
            else:
                # non vertical line
                dix = 1 if end[0] > start[0] else -1
                prev = start
                for x in range(start[0], end[0] + dix, dix):
                    y = lline(x,slope,offset)
                    if abs(y - prev[1]) > 1:
                        di = 1 if y > prev[1] else -1
                        for y1 in range(prev[1] + di, y, di):
                            img[y1,x] = color

                    img[y,x] = color
                    prev = (x,y)

        def draw_line(img: np.array, p1: (int,int), p2: (int,int), gray: int):
            """
            Draws a line from - and including - p1 (x,y) to -and including p2 (x,y).
            """
            if not ((p1[0] < 0) or (p1[1] < 0) or (p2[0] < 0) or( p2[1] < 0)):
                pixel = 1/self.settings["pixel_size"]
                draw(img, (int(p1[0]*pixel),int(p1[1]*pixel)),(int(p2[0]*pixel),int(p2[1]*pixel)), gray)

        def render_pathwidth(line_chain: LineSegmentChain, steps: list[float], color: int = None, speed: int = None, boundingbox = None):
            """
            Render - generate gcode for - a path of certain 'width'.
            """
            # A path can be an 'engraving' or a 'cut'.
            for step in steps:      # step 'width'
                if step:
                    # calculate delta chain
                    delta_chain = LineSegmentChain.delta_chain(line_chain, step)

                    # Note that append_line_chain generates a path cut when inverse_bw and speed are set to None.
                    self.append_line_chain(delta_chain, step, color, speed)

                    # update boundingbox of this 'name_id'
                    for line in delta_chain:
                        boundingbox.update(line.start)
                        boundingbox.update(line.end)
                else:
                    # Note that append_line_chain generates a path cut when inverse_bw and speed are set to None.
                    self.append_line_chain(line_chain, 0, color, speed)
                    # update boundingbox of this 'name_id'
                    for line in line_chain:
                        boundingbox.update(line.start)
                        boundingbox.update(line.end)

        def get_style_info_of_line_chain(line_chain: LineSegmentChain) -> ():
            """
            Get style info of line_chain.
            Returns tuple (stroke_width, stroke_color, stroke_alpha, fill_color, fill_alpha, fill_rule)
            """
            # defaults
            stroke_width = 0
            stroke_color = ""
            stroke_alpha = None
            fill_color = None
            fill_alpha = None
            fill_rule = None

            # get style info for this line chain
            first_line_of_chain = line_chain.get(0)
            style = self.parse_style_attribute(first_line_of_chain)
            if style:
                if not (style['pathcut'] == 'true' or self.settings["pathcut"]) \
                    and style['stroke'] is not None and style['stroke'] != "none":
                    stroke_color = style['stroke']
                    if style['stroke-opacity'] is not None:
                        # fill opacity attribute overrides rgba property
                        stroke_alpha = float(style['stroke-opacity'])
                        if not (stroke_alpha >=0 and stroke_alpha <= 1):
                            logger.warn(f"Opacity value '{stroke_alpha}' should be in range [0.0..1.0]!")
                if style['stroke-width'] is not None and style['stroke-width'] != "none":
                    width = float(style['stroke-width'])
                    stroke_width = math.ceil(round(width/pixel_size, self.precision)/2)
                if style['fill'] is not None and style['fill'] != 'none':
                    # Invert b&w value and apply alpha channel - when available - to the inverted b&w value
                    # Library function image2gcode - as it is now - cannot invert a color value and then apply the alpha channel.
                    # Note that step 6 of '# Render svg fill attribute' below, sets option 'invert' of image2gcode to false to use fill_color directly.)
                    fill_color = Image2gcode.linear_power(css_color.parse_css_color2bw8(style['fill']), self.settings["maximum_image_laser_power"])
                    if style['fill-rule'] is not None:
                        fill_rule = style['fill-rule']
                        if fill_rule == "nonzero":
                            logger.warn(f"fill-rule 'nonzero' of object '{name_id}' is currently unsupported!")
                    if style['fill-opacity'] is not None:
                        # fill opacity attribute overrides rgba property
                        fill_alpha = float(style['fill-opacity'])
                        if not (fill_alpha >=0 and fill_alpha <= 1):
                            logger.warn(f"Opacity value '{fill_alpha}' should be in range [0.0..1.0]!")
                            fill_alpha = 1
                    else:
                        rgba = css_color.parse_css_color(style['fill'])
                        fill_alpha = 1
                        if len(rgba) == 4:
                            fill_alpha = rgba[3]
                    fill_color = fill_color * fill_alpha

            return (stroke_width, stroke_color, stroke_alpha, fill_color, fill_alpha, fill_rule)


        path_curves = {}
        pixel_size = float(self.settings["pixel_size"])

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
                if curve.path_attrib and 'id' in curve.path_attrib:
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

            steps = []
            fill_color = None
            fill_alpha = None
            fill_rule = None

            # set a boundingbox per 'name_id'
            boundingbox = Boundingbox()

            # Render svg 'stroke' attribute
            for line_chain in path_curves[name_id]:
                # get style info
                stroke_width, stroke_color, stroke_alpha, fill_color, fill_alpha, fill_rule = get_style_info_of_line_chain(line_chain)

                if len(stroke_color):
                    # Get steps (offsets) for the lines that make the border
                    steps = [0]
                    if stroke_width:
                        for delta in range(stroke_width):
                            if delta:
                                steps.append(round(delta * pixel_size, self.precision))
                                if not (delta == stroke_width and stroke_width % 2 != 0):
                                    steps.append(round(-delta * pixel_size, self.precision))

                    # Get stroke alpha channel (opacity)
                    # fill opacity attribute overrides rgba property
                    if stroke_alpha is None:
                        stroke_alpha = 1
                        rgba = css_color.parse_css_color(stroke_color)
                        if len(rgba) == 4:
                            stroke_alpha = rgba[3]

                    # engrave values
                    # set inversed b&w value (and apply alpha channel, when available)
                    inverse_bw = Image2gcode.linear_power(css_color.parse_css_color2bw8(stroke_color), \
                                                          self.settings["maximum_image_laser_power"]) * stroke_alpha
                    # set laser head movement speed
                    speed = self.settings["image_movement_speed"]

                    # handle option color_coded
                    if self.settings["color_coded"]:
                        # get color_coded info
                        ignorepath, cutpath, engravepath = self.parse_color_coded(stroke_color)

                        if not ignorepath:

                            if cutpath:
                                # color_coded set cut path for this stroke_color
                                self.body.extend([f"\n; --color_coded cut path '{name_id}', color '{stroke_color}'"])
                                render_pathwidth(line_chain, [0], None, None, boundingbox)
                            else:
                                # engrave path ...
                                pathignore, pathcut, pathengrave = self.color_coded_paths()

                                # ... if color_coded did not set engrave (at all) or set engrave for this stroke_color
                                if len(pathengrave) == 0 or engravepath:
                                    if len(pathengrave) == 0:
                                        self.body.extend([f"\n; --color_coded: engrave not set, path '{name_id}', color '{stroke_color}'"])
                                    else:
                                        self.body.extend([f"\n; --color_coded: engrave path '{name_id}', color '{stroke_color}'"])
                                    render_pathwidth(line_chain, steps, inverse_bw, speed, boundingbox)
                        else:
                            self.body.extend([f"\n; --color_coded: ignore path '{name_id}', color '{stroke_color}'"])

                    else:
                        # color_coded isn't set: engrave path
                        self.body.extend([f"\n; engrave path '{name_id}', color '{stroke_color}'"])
                        render_pathwidth(line_chain, steps, inverse_bw, speed, boundingbox)
                else:
                    # line stroke isn't set: cut path
                    self.body.extend([f"\n; no stroke color: cut path '{name_id}'"])
                    render_pathwidth(line_chain, [0], None, None, boundingbox)

            # Render svg 'fill' attribute
            if not self.settings["nofill"] and fill_color is not None and boundingbox.get() is not None:
                # fill a path
                # this is done in 6 steps:
                # step 1: create two raster images matching the bbox
                # step 2: add marker lines just inside the line chains of the path
                # step 3: scan the marker image lines and apply 'evenodd' fill
                #         (fill rule 'nonzero' to be implemented later on see note below)
                # step 4: draw white borders to erase fill overlap
                # step 5: filter stray pixels (to remove noise from the action above)
                # step 6: generate gcode from image_fill (by execution function image2gcode)

                self.body.extend([f"\n; fill path '{name_id}'"])

                # get bounding box info from the path border
                lowerleft = boundingbox.get()[0]
                upperright = boundingbox.get()[1]

                # normalize origin to (0.0)
                vdXY = Vector(-lowerleft.x, -lowerleft.y)
                dXY = (-lowerleft.x, -lowerleft.y)

                # get raster image dimensions
                img_height = math.ceil((upperright.y - lowerleft.y)/pixel_size)
                img_width = math.ceil((upperright.x - lowerleft.x)/pixel_size)

                # default scan error (step 3 below)
                scan_error = 4

                # step 1: create two raster images matching the bbox
                # init
                image_mark = np.full([img_height + 2, img_width + scan_error], 255, dtype=np.uint8)
                image_fill = np.full([img_height + 2, img_width + scan_error], 0, dtype=np.uint8)

                # step 2: add marker lines just inside the line chains of the path
                # - determine the inside of the line chain
                # - draw marker lines
                for line_chain in path_curves[name_id]:
                    # Note that a svg object with a specific name_id can have multiple line_chains that
                    # together, define one shape (circumference). When this the case the boundingbox
                    # inside/outside method below is not fullproof. This can be solved to stitch together
                    # the line chain parts (TODO)

                    # - determine the inside of the line chain
                    # Compare the bbox of the line chain with that of a delta line chain a
                    # fixed distance (offset) from the base line chain. Initially we do not know if the
                    # delta line chain is inside or outside the base line chain, but when we compare
                    # the bbox sizes we know.
                    # Note that this method can be used to determine if a line chain is drawn clockwise
                    # or anti-clockwise because a posive delta offset should be 'outside' the line chain
                    # in this case (depending on the definition/calculation of the delta function).
                    # we can use this to implement the other svg fill rule: 'nonzero'.
                    bbox = Boundingbox()
                    for line in line_chain:
                        bbox.update(line.start + vdXY)
                        bbox.update(line.end + vdXY)
                    bbox_size = bbox.size()

                    bbox = Boundingbox()
                    delta_chain = LineSegmentChain.delta_chain(line_chain, pixel_size * 2)
                    for line in delta_chain:
                        bbox.update(line.start + vdXY)
                        bbox.update(line.end + vdXY)
                    bbox_deltasize =  bbox.size()

                    # compare bboxes and set inside offset
                    inside = 1
                    if bbox_deltasize > bbox_size:
                        inside = -1

                    # Note that some tuning is going on here.
                    # This can be remedied in several ways:
                    # - use draw lines that have a thickness?
                    # - use a higher resolution (pixel grid) to reduce the 'rounding' errors
                    offsets = [inside * .5 * pixel_size, inside * pixel_size, inside * 1.5 * pixel_size, inside * 2 * pixel_size]
                    # Note that the system sometimes returns line_chains having 1 point and thus having no size, this is 'solved'
                    # below, but should not happen (TODO). It is also assumed that line_chain parts that define one shape have
                    # similar sizes (TODO).
                    if bbox_size > 0 and bbox_size < 6:
                        # small area, less margin for error
                        scan_error = 1
                        del offsets[-2:]

                    ## direct gcode: update this, see note step 3
                    # draw border lines of a specific marker color within line chain
                    # Note that the marker values are just a choice and only have to be consistent
                    # with the algorithm used (step 3)
                    if bbox_size > 0.0:
                        for offset in offsets:
                            # make a line chain just one pixel inside the base (step 0) line chain
                            delta_chain = LineSegmentChain.delta_chain(line_chain, offset)
                            for line in delta_chain:
                                draw_line(image_mark, line.start + vdXY, line.end + vdXY, 128)

                    # draw the line chain border using another marker color
                    for line in line_chain:
                        draw_line(image_mark, line.start + vdXY, line.end + vdXY, 10)

                # step 3: scan the marker image lines and and apply 'evenodd' fill
                #         (fill rule 'nonzero' to be implemented later on)
                #    for each line (y):
                #        for each point (x) on the line:
                #           scan from left to right or reverse:
                #               for markers (border,inside border) and apply rule
                #               'evenodd' to fill when an even number of borders
                #               is crossed, untill odd
                # Note that image 'image_fill' is filled (not 'image_mark') to make sure marks stay in place.

                # Note that the fill algorithm can be adapted to support direct rendering of gcode (instead of rendering via 'image_fill' and
                # function 'image2gcode', converting a raster image to gcode). This reduces the number of steps needed: steps 4, 5 and 6 can
                # be left out. It does need a few adaptations in the previous steps, namely drawing the line chain border (color '10') in full width
                # (instead of 1 pixel) and draw the 'inside' line (color 128) one pixel further. In addition to this uncomment the '## direct gcode'
                # lines of step 3 to activate gcode rendering.

                ## direct gcode
                ## code = [f"\n; fill '{name_id}'"]
                ## code += [self.interface.set_laser_power_value(Image2gcode.linear_power(fill_color, self.settings["maximum_image_laser_power"]))]

                go_right = True
                # start scanning to the right
                for y in range(image_mark.shape[0]):
                    evenodd = 0

                    if go_right:
                        # scan to the right
                        x = 0
                        start = None
                        while x < image_mark.shape[1]:
                            if image_mark[y,x] == 10 :
                                # found a border
                                x_b = x
                                ## direct gcode
                                ## update line below, to be able to skip empty (value 255) pixels
                                # scan border, possibly having multiple pixels.
                                while x_b < image_mark.shape[1] and image_mark[y,x_b] == 10:
                                    x_b += 1

                                xscan_b = x - 1
                                while xscan_b > 0 and xscan_b > (x - scan_error) and (image_mark[y,xscan_b] != 10 and image_mark[y,xscan_b] != 128):
                                    xscan_b -= 1
                                xscan_a = x_b
                                while xscan_a < image_mark.shape[1] and xscan_a < (x_b + scan_error) and (image_mark[y,xscan_a] != 10 and image_mark[y,xscan_a] != 128):
                                    xscan_a += 1

                                if xscan_b >= 0 and image_mark[y,xscan_b] == 128:
                                    # found border
                                    if evenodd % 2 == 0:
                                        start = (x * pixel_size, y * pixel_size)
                                        ## direct gcode
                                        ## code += [self.interface.rapid_move(start[0] - dXY[0], start[1] - dXY[1])]
                                    else:
                                        draw_line(image_fill, start + dXY, (x * pixel_size, y * pixel_size) + dXY, fill_color)
                                        ## direct gcode
                                        ## code += [self.interface.linear_move(x * pixel_size - dXY[0], y * pixel_size - dXY[1])]
                                    evenodd = evenodd + 1
                                if xscan_a < image_mark.shape[1] and image_mark[y,xscan_a] == 128:
                                    # found border
                                    if evenodd % 2 == 0:
                                        start = (x * pixel_size, y * pixel_size)
                                        ## direct gcode
                                        ## code += [self.interface.rapid_move(start[0] - dXY[0], start[1] - dXY[1])]
                                    else:
                                        draw_line(image_fill, start + dXY, (x_b * pixel_size, y * pixel_size) + dXY, fill_color)
                                        ## direct gcode
                                        ## code += [self.interface.linear_move(x_b * pixel_size - dXY[0], y * pixel_size - dXY[1])]
                                    evenodd = evenodd + 1
                                #if x_b > x:
                                x = x_b - 1
                            x += 1
                    else:
                        # scan to the left
                        start = None
                        x = image_mark.shape[1] - 1
                        while x >= 0:
                            if image_mark[y,x] == 10:
                                # found a border
                                ## direct gcode
                                ## update line below, to be able to skip empty (value 255) pixels
                                # scan border, possibly having multiple pixels.
                                x_b = x
                                while x_b >= 0 and image_mark[y,x_b] == 10:
                                    x_b -= 1

                                xscan_b = x_b
                                while xscan_b > 0 and xscan_b > (x_b - scan_error) and (image_mark[y,xscan_b] != 10 and image_mark[y,xscan_b] != 128):
                                    xscan_b -= 1
                                xscan_a = x + 1
                                while xscan_a < image_mark.shape[1] and xscan_a < (x + scan_error) and (image_mark[y,xscan_a] != 10 and image_mark[y,xscan_a] != 128):
                                    xscan_a += 1

                                if xscan_a < image_mark.shape[1] and image_mark[y,xscan_a] == 128:
                                    # found border
                                    if evenodd % 2 == 0:
                                        start = (x * pixel_size, y * pixel_size)
                                        ## direct gcode
                                        ## code += [self.interface.rapid_move(start[0] - dXY[0], start[1] - dXY[1])]
                                    else:
                                        draw_line(image_fill, start + dXY, (x * pixel_size, y * pixel_size) + dXY, fill_color)
                                        ## direct gcode
                                        ## code += [self.interface.linear_move(x * pixel_size - dXY[0], y * pixel_size - dXY[1])]
                                    evenodd = evenodd + 1
                                if xscan_b >= 0 and image_mark[y,xscan_b] == 128:
                                    # found border
                                    if evenodd % 2 == 0:
                                        start = (x * pixel_size, y * pixel_size)
                                        ## direct gcode
                                        ## code += [self.interface.rapid_move(start[0] - dXY[0], start[1] - dXY[1])]
                                    else:
                                        draw_line(image_fill, start + dXY, (x_b * pixel_size, y * pixel_size) + dXY, fill_color)
                                        ## direct gcode
                                        ## code += [self.interface.linear_move(x_b * pixel_size - dXY[0], y * pixel_size - dXY[1])]
                                    evenodd = evenodd + 1
                                #if x_b < x:
                                x = x_b + 1
                            x -= 1

                    # switch scan direction
                    go_right = not go_right

                ## direct gcode
                ## self.body.extend(code)

                ## direct gcode: ignore this step
                # step 4: draw white borders to erase fill overlap

                # 4a: make half steps to 'completely' erase the overlap
                halfsteps = copy.deepcopy(steps)
                for step in steps:
                    if step:
                        sign = -1 if step >= 0 else 1
                        halfsteps.append(round(step + sign * pixel_size/2, self.precision))

                # 4b: erase
                for line_chain in path_curves[name_id]:
                    for step in halfsteps:
                        if step:
                            delta_chain = LineSegmentChain.delta_chain(line_chain, step)
                            for line in delta_chain:
                                draw_line(image_fill, line.start + vdXY, line.end + vdXY, 0)
                        else:
                            for line in line_chain:
                                draw_line(image_fill, line.start + vdXY, line.end + vdXY, 0)

                ## direct gcode: ignore this step
                # step 5: filter stray pixels (to remove noise from the action above)
                for y in range(image_fill.shape[0]):
                    for x in range(image_fill.shape[1]):
                        if image_fill[y,x] != 0:
                            if x > 1 and x < (image_fill.shape[1] - 1) and y > 1 and y < (image_fill.shape[0] - 1):
                                if image_fill[y,x+1] == 0 and image_fill[y,x-1] == 0 and image_fill[y+1,x] == 0 and image_fill[y-1,x] == 0:
                                    image_fill[y,x] = 0

                ## direct gcode: ignore this step
                # step 6: generate gcode from image_fill
                img_attrib = {}
                img_attrib['id'] = name_id
                # Set speedmove to a short distance to be able to view it correctly using a viewer like LaserWeb.
                # (image2gcode converts movements without writing to 'G1 S0' gcodes which viewers show in a specific
                #  writing color, speedmoves uses gcode G0 to move without writing which viewers show in another color)
                #img_attrib['gcode_speedmoves'] = 0.1
                img_attrib['x'] = -dXY[0]
                img_attrib['y'] = -dXY[1]
                img_attrib['invert'] = False

                ## direct gcode: ignore this step
                # start gcode fill
                self.image2gcode(img_attrib, image_fill)

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

        if self.settings["distance_mode"] == "absolute" and self.check_axis_maximum_travel() and self.boundingbox.get():
            machine_max = Vector(self.settings["x_axis_maximum_travel"],self.settings["y_axis_maximum_travel"])
            bbox = self.boundingbox.get()

            # bbox[0] == lowerleft, bbox[1] == uperright, bbox[0/1][0] == x, bbox[0/1][1] == y
            #      lower left x and y >= 0 and upperright x and y <= resp. machine max x and y
            return (bbox[0][0] >= 0 and bbox[0][1] >=0
                    and bbox[1][0] * (25.4 if self.settings["unit"] == "inch" else 1) <= machine_max.x
                    and bbox[1][1] * (25.4 if self.settings["unit"] == "inch" else 1) <= machine_max.y)

        return False
