""" This module is responsible for rendering vector graphics.

    Vector graphics image and path tags are rendered to Gcode.
    - Images are drawn in a raster image way by converting pixels to gcode via 'image2gcode'
    - paths are drawn in a vector graphics way including 'fill' and 'stroke'.
"""

import os
import re
import logging
import math
import copy

from io import BytesIO
from typing import Any

import base64
from datetime import datetime
from operator import itemgetter
from PIL import Image
import numpy as np
import numpy.typing as npt

from svg2gcode.svg_to_gcode.compiler.interfaces import Interface
from svg2gcode.svg_to_gcode.geometry import Curve
from svg2gcode.svg_to_gcode.geometry import Line, LineSegmentChain, Vector, RasterImage
from svg2gcode.svg_to_gcode import DEFAULT_SETTING
from svg2gcode.svg_to_gcode import TOLERANCES, SETTING, check_setting

from svg2gcode.svg_to_gcode import css_color
from svg2gcode.svg_to_gcode.svg_parser import NAMESPACES, ElementTreeParent

from svg2gcode import __version__

from image2gcode.boundingbox import Boundingbox # type: ignore[import-untyped]
from image2gcode.image2gcode import Image2gcode # type: ignore[import-untyped]

#logging.basicConfig(format="[%(levelname)s] %(message)s (%(name)s:%(lineno)s)")
logging.basicConfig(format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# fan codes
FAN_OFF = 0
FAN_CUT = 1
FAN_ENGRAVE = 4
FAN_ON = 8

class Compiler:
    """
    The Compiler class handles the process of drawing geometric objects using interface commands
    and assembling the resulting numerical control code.
    """

    def __init__(self, interface_class: type[Interface], custom_header: list[str] | None = None,
                 custom_footer: list[str] | None = None, params: dict[str, Any] | None = None):
        """

        :param interface_class: Specify which interface to use. The most common is the gcode interface.
        :param custom_header: A list of commands to be executed before all generated commands.
        :param custom_footer: A list of commands to be executed after all generated commands.
                              Default [laser_off, program_end]
        :param settings: dictionary to specify "unit", "pass_depth", "dwell_time", "movement_speed", etc.
        """
        self.svg_file_name: str | None = None
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

        # get fan code:
        fan_code = FAN_OFF
        fan_code |= FAN_CUT if self.settings['fan'] == "on_cut" else 0
        fan_code |= FAN_ENGRAVE if self.settings['fan'] == "on_engrave" else 0
        fan_code |= FAN_ON if self.settings['fan'] == "on" else 0

        # update in settings
        self.settings['fan'] = fan_code

        # set machine parameters in interface
        self.interface.set_machine_parameters(self.settings)

        if custom_header is None:
            custom_header = []

        if custom_footer is None:
            custom_footer = [self.interface.laser_off(), self.interface.program_end()]

        self.header = [self.interface.code_initialize(),
                       self.interface.set_unit(self.settings["unit"]),
                       self.interface.set_distance_mode(self.settings["distance_mode"])] + custom_header
        self.footer = custom_footer

        # path gcode
        self.body: list[str] = []
        # image gcode
        self.gcode: list[str] = []

    def gcode_file_header(self):
        """
        Helper function to generate information at the start of a gcode file.

        """

        gcode = []

        if not self.check_bounds():
            if self.settings["distance_mode"] == "absolute" and self.check_axis_maximum_travel():
                logger.warning("Cut is not within machine bounds.")
                gcode += ["; WARNING: Cut is not within machine bounds of "
                          f"X[0,{self.settings['x_axis_maximum_travel']}], Y[0,{self.settings['y_axis_maximum_travel']}]\n",]
            elif not self.check_axis_maximum_travel():
                # logger.warning("Please define machine cutting area, set parameter: 'x_axis_maximum_travel' and 'y_axis_maximum_travel'")
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

        gcode += [ f";    svg2gcode {__version__} ({str(datetime.now()).split('.',maxsplit=1)[0]})",
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
        :return returns the assembled g-code. [self.body, -self.pass_depth] * passes
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
                gcode.append(self.interface.laser_off(fan_off = False))
                gcode.append(self.interface.set_relative_coordinates())
                gcode.append(self.interface.linear_move(z=-self.settings["pass_depth"]))
                gcode.append(self.interface.set_distance_mode(self.settings["distance_mode"]))

        # remove all ""
        gcode = filter(lambda command: len(command) > 0, gcode)

        return '\n'.join(gcode)

    def compile_images(self):

        """
        Assembles the code in the header, body and footer.
        """

        # laser off, fan on or off, M3 or M4 burn mode
        header_gc = ["M5"]
        if (self.settings["fan"] == FAN_ON or self.settings["fan"] == FAN_ENGRAVE):
            # fan on
            header_gc += ['M8']
        else:
            # make sure fan is off
            header_gc += ['M9']

        header_gc += ['M3' if self.settings["laser_mode"] == "constant" else 'M4']

        return '\n'.join(header_gc + self.gcode)

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
        footer = '\n'.join(self.footer) + '\n'

        if len(self.body) > 0:
            # write path objects
            with open(file_name, 'w') as file:
                program_end = footer if (self.settings["splitfile"] or len(self.gcode) == 0) else ""
                file.write(self.gcode_file_header() + header + self.compile(passes=passes) + '\n' + program_end)
                logger.info(f"Path drawings written to '{file_name}'")
        else:
            logger.warning(f"No paths to draw, nothing to write to '{file_name}', skipping")

        image_file_name = file_name.rsplit('.',1)[0] + "_images." + file_name.rsplit('.',1)[1]
        if len(self.gcode) == 0:
            if self.settings["splitfile"]:
                logger.warning(f"No images to draw, nothing to write to '{image_file_name}', skipping")
        else:
            if self.settings["splitfile"]:
                # emit image objects to <filename>_images.<gcext>
                with open(image_file_name, 'w') as file:
                    file.write(self.gcode_file_header() + header + self.compile_images() + '\n' + footer)
                    logger.info(f"Image drawings written to '{image_file_name}'")
            else:
                # emit images objects in same file
                open_mode = 'w' if len(self.body) == 0 else 'a+'
                with open(file_name, open_mode) as file:
                    file.write((self.gcode_file_header() if len(self.body) == 0 else "") + '\n' +  self.compile_images() + '\n' + footer)
                    logger.info(f"Added image drawings to '{file_name}'")

    def append_line_chain(self, line_chain: LineSegmentChain, step: float, color: int | None = None, speed: int | None = None):
        """
        Draws a LineSegmentChain (path) by calling interface.linear_move() for each segment.
        The resulting code is appended to self.body

        :param line_chain: path to draw.
        :param step: path offset (indicates that this path is offset to another path).
        :param color: laser intensity, 'laser_power' when set to 'None'.
        :param speed: laser head movement speed, 'movement_speed' when set to 'None'.
        """

        if line_chain.chain_size() == 0:
            logger.warning("Attempted to parse empty LineChain")
            return

        code = [f"\n; delta: {step}"]
        start = line_chain.get(0).start

        # set laser power to color value when svg attribute 'stroke' (color) is set
        laser_power = color if color is not None else self.settings["laser_power"]
        movement_speed = speed if speed is not None else self.settings["movement_speed"]

        # set fan on or off for this engrave or cut
        if color is None and speed is None:
            # this is a cut
            fan_set = self.settings["fan"] == FAN_ON or self.settings["fan"] == FAN_CUT
        else:
            # this is an engrave
            fan_set = self.settings["fan"] == FAN_ON or self.settings["fan"] == FAN_ENGRAVE

	# Move to the next line_chain when the next line segment doesn't connect to the end of the previous one.
        if self.interface.position is None or abs(self.interface.position - start) > TOLERANCES["operation"]:
            if self.interface.position is None or self.settings["rapid_move"]:
                # move to the next line_chain: set laser off, rapid move to start of chain,
                # set movement (cutting) speed, set laser mode and power on
                code += [self.interface.laser_off(fan_off = False), self.interface.rapid_move(start.x, start.y),
                        self.interface.set_movement_speed(movement_speed),
                        self.interface.set_laser_mode(self.settings["laser_mode"]), self.interface.set_laser_power_value(laser_power,fan_on = fan_set)]
            else:
                # move to the next line_chain: set laser mode, set laser power to 0 (cutting is off),
                # set movement speed, (no rapid) move to start of chain, set laser to power
                code += [self.interface.set_laser_mode(self.settings["laser_mode"]), self.interface.set_laser_power_value(0,fan_off = False),
                        self.interface.set_movement_speed(movement_speed), self.interface.linear_move(start.x, start.y),
                        self.interface.set_laser_power_value(laser_power, fan_on = fan_set)]

            self.boundingbox.update(start)

            if self.settings["dwell_time"] > 0:
                code += [self.interface.dwell(self.settings["dwell_time"])] + code

        else:
            # set laser power and fan
            code += [self.interface.set_laser_power_value(laser_power, fan_on = fan_set)]

        for line in line_chain:
            code.append(self.interface.linear_move(line.end.x, line.end.y))
            self.boundingbox.update(line.end)

        self.body.extend(code)

    def isBase64(self, b64str) -> bool:
        """
        Wrapper function to check safely if we have base64 image data.
        :param b64str: xlink:href field from SVG document
        """
        try:
            base64.b64decode(b64str)
            return True
        except Exception:
            return False

    def decode_base64(self, base64_string) -> None | Image.Image :
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
                return None

        elif self.isBase64(fileordata):
            # convert to right form
            imgdata = base64.b64decode(fileordata)

            # open as binary file
            img_file = BytesIO(imgdata)
        else:
            # Neither file nor data
            logger.error("Unable to read image data: %s", base64_string[:30])
            return None

        return Image.open(img_file)

    def convert_image(self, image:str, img_attrib: dict[str, Any]) -> npt.NDArray[np.int8]:
        """
        Convert a MIME base64 image string to new size, black&white (without alpha)
        add 8 bit. Add a white background in the process.
        :param str: xlink:href field from SVG document
        :param img_sttrib: properties of image
        return: NDarray representing the image in black&white (without alpha)
        """

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

    def image2gcode(self, img_attrib: dict[str, Any], img = None, transformation = None, power = None):
        """
        Convert an image to gcode.
        Makes use of function image2gcode.
        :img_attrib: all relevant image attributes
        :img: image to convert
        :transformations: all transformations that must be appield to the image
        :power: gcode power level

        """

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
        arguments["invert"] = img_attrib['invert'] if 'invert' in img_attrib else True

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

    def parse_style_attribute(self, first_line_of_curve: Line) -> dict[str, int | float | str | None]:
        """
        Parse style attribute.
        for example "fill:#F4CF84;fill-rule:evenodd;stroke:#D07735;"
        """

        style: dict[str, str | int | float | None] = \
            {'fill' : None, 'fill-rule': None, 'fill-opacity': None, 'stroke': None, 'stroke-width': None, 'stroke-opacity': None, 'pathcut': None}

        def style_attribute(path_attrib):
            """
            Parse style attribute.
            for example "fill:#F4CF84;fill-rule:evenodd;stroke:#D07735;"
            """

            if path_attrib and 'style' in path_attrib:
                style_str = path_attrib['style']

                # parse fill
                if style['fill'] is None and 'fill' in style_str:
                    fill = re.search('fill:[^;]+;',style_str)
                    if fill:
                        fill_str = fill.group(0)[5:-1]
                        if fill_str != 'none':
                            style['fill'] = fill_str
                # parse fill-rule
                if style['fill-rule'] is None and 'fill-rule' in style_str:
                    fill_rule = re.search('fill-rule:#(evenodd|nonzero)',style_str)
                    if fill_rule:
                        style['fill-rule'] = re.search('(evenodd|nonzero)', fill_rule.group(0)).group(0)
                # parse fill-opacity
                if style['fill-opacity'] is None and 'fill-opacity' in style_str:
                    fill_opacity = re.search(r'fill-opacity:(\d*\.)?\d+',style_str)
                    if fill_opacity:
                        style['fill-opacity'] = re.search(r'(\d*\.)?\d+', fill_opacity.group(0)).group(0)
                # parse stroke
                if style['stroke'] is None and 'stroke' in style_str:
                    stroke = re.search('stroke:[^;]+;',style_str)
                    if stroke:
                        stroke_str = stroke.group(0)[7:-1]
                        if stroke_str != 'none':
                            style['stroke'] = stroke_str
                # parse stroke-width
                if style['stroke-width'] is None and 'stroke-width' in style_str:
                    stroke_width = re.search(r'stroke-width:(\d*\.)?\d+',style_str)
                    if stroke_width:
                        style['stroke-width'] = re.search(r'(\d*\.)?\d+', stroke_width.group(0)).group(0)
                # parse stroke-opacity
                if style['stroke-opacity'] is None and 'stroke-opacity' in style_str:
                    stroke_opacity = re.search(r'stroke-opacity:(\d*\.)?\d+',style_str)
                    if stroke_opacity:
                        style['stroke-opacity'] = re.search(r'(\d*\.)?\d+', stroke_opacity.group(0)).group(0)

                # parse pathcut
                if style['pathcut'] is None and 'gcode-pathcut' in style_str:
                    pathcut = re.search('gcode-pathcut:(true|false)',style_str)
                    if pathcut:
                        style['pathcut'] = re.search('(true|false)', pathcut.group(0)).group(0)

        def other_attributes(path_attrib):
            """
            Parse other attributes
            """

            # parse fill attribute
            if style['fill'] is None and 'fill' in path_attrib:
                if path_attrib['fill'] != 'none':
                    style['fill'] = path_attrib['fill']
            if style['fill-rule'] is None and 'fill-rule' in path_attrib:
                style['fill-rule'] = path_attrib['fill-rule']
            # parse fill-opacity
            if style['fill-opacity'] is None and 'fill-opacity' in path_attrib:
                fill_opacity = re.search(r'fill-opacity:(\d*\.)?\d+',path_attrib)
                if fill_opacity:
                    style['fill-opacity'] = re.search(r'(\d*\.)?\d+', fill_opacity.group(0)).group(0)
            # parse stroke attribute
            if style['stroke'] is None and 'stroke' in path_attrib:
                stroke_str = path_attrib['stroke']
                if stroke_str != 'none':
                    style['stroke'] = stroke_str
            # parse stroke-width attribute
            if style['stroke-width'] is None and 'stroke-width' in path_attrib:
                style['stroke-width'] = path_attrib['stroke-width']
            # parse stroke-opacity attribute
            if style['stroke-opacity'] is None and 'stroke-opacity' in path_attrib:
                style['stroke-opacity'] = path_attrib['stroke-opacity']

            # parse gcode_pathcut attribute
            if style['pathcut'] is None and 'gcode_pathcut' in path_attrib:
                style['pathcut'] = path_attrib['gcode_pathcut']


        # parse style attribute
        style_attribute(first_line_of_curve.path_attrib)

        # parse other attributes
        other_attributes(first_line_of_curve.path_attrib)

        # check missing attributes, if any
        if ElementTreeParent in first_line_of_curve.path_attrib:
            parent = first_line_of_curve.path_attrib[ElementTreeParent]

            # find first parent <g (group) tag, if any
            while parent and parent.tag != "{%s}g" % NAMESPACES["svg"]:
                if ElementTreeParent in parent.attrib:
                    parent = parent.attrib[ElementTreeParent]
                else:
                    parent = None

            if parent:
                # parse style attribute of parent '<g'
                style_attribute(parent.attrib)

                # parse other attributes of parent '<g'
                other_attributes(parent.attrib)

        return style

    @staticmethod
    def color_coded(color_coded: str) ->  tuple[(list[str],list[str],list[str])]:
        """
        Parse color_coded string to colors in subgroups.
        Return tuple of lists (pathignore, pathcut, pathengrave)
               each containing all colors for that group.
        """

        pathcut     = []
        pathignore  = []
        pathengrave = []

        # get ignore colors
        colors_ignore_regex = r"([^ ]* *= *ignore)+"
        match = re.findall(colors_ignore_regex, color_coded)
        if match:
            pathignore = [re.match(r"[^ ]*",i).group(0) for i in match]

        # get cut colors
        colors_cut_regex = r"([^ ]* *= *cut)+"
        match = re.findall(colors_cut_regex, color_coded)
        if match:
            pathcut = [re.match(r"[^ ]*",i).group(0) for i in match]

        # get engrave colors
        colors_engrave_regex = r"([^ ]* *= *engrave)+"
        match = re.findall(colors_engrave_regex, color_coded)
        if match:
            pathengrave = [re.match(r"[^ ]*",i).group(0) for i in match]

        return (pathignore, pathcut, pathengrave)

    def parse_color_coded(self, stroke_color: str | None = None) -> tuple[(bool,bool,bool)]:
        """
        Parse option --color_coded
        Return tuple (ignorepath, cutpath, engravepath)
        """
        if self.settings["color_coded"]:

            ignorepath = False
            cutpath = False
            engravepath = False

            allothercolors = "allothercolors"

            # Get color_coded info
            pathignore, pathcut, pathengrave = Compiler.color_coded(self.settings["color_coded"])

            for color in pathignore:
                if color != allothercolors and css_color.rgb24equal(css_color.parse_css_color(stroke_color), css_color.parse_css_color(color)):
                    # stroke color is ignored (no path is drawn)
                    ignorepath = True
                    break

            if not ignorepath:
                # cut path if option --color_coded is selected and stroke_color == "red"
                for color in pathcut:
                    if color != allothercolors and css_color.rgb24equal(css_color.parse_css_color(stroke_color), css_color.parse_css_color(color)):
                        cutpath = True
                        break

                if not cutpath:
                    for color in pathengrave:
                        if color != allothercolors and css_color.rgb24equal(css_color.parse_css_color(stroke_color), css_color.parse_css_color(color)):
                            engravepath = True
                            break

            if not (ignorepath or cutpath or engravepath):
                # stroke color isn't set in any path category
                # check if 'allothercolors' is set in a path category (can only be one category)
                ignorepath = allothercolors in pathignore
                cutpath = allothercolors in pathcut
                engravepath = allothercolors in pathengrave

        return (ignorepath, cutpath, engravepath)


    def check_axis_maximum_travel(self):
        """
        Check axes settings are set.

        """
        return self.settings["x_axis_maximum_travel"] is not None and self.settings["y_axis_maximum_travel"] is not None
        # logger.warning("Please define machine cutting area, set parameter: 'x_axis_maximum_travel' and 'y_axis_maximum_travel'")

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

    def append_curves(self, curves: list[Curve]):
        """
        Generates gcode for images and stroke and fill of paths.
        """

        def render_pathwidth(line_chain: LineSegmentChain, steps: list[float], color: int | None = None, speed: int | None = None, boundingbox = None):
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

        def get_style_info_of_line_chain(line_chain: LineSegmentChain) -> tuple[float,str,float,str,float,str,str]:
            """
            Get style info of line_chain.
            Returns tuple (stroke_width, stroke_color, stroke_alpha, fill_color, fill_alpha, fill_rule, pathcut)
            """
            # defaults
            stroke_width = 0.0
            stroke_color = ""
            stroke_alpha = None
            fill_color = None
            fill_alpha = None
            fill_rule = self.settings["fillrule"]

            # get style info for this line chain
            first_line_of_chain: Line = line_chain.get(0)
            style = self.parse_style_attribute(first_line_of_chain)

            if style:
                if style['stroke'] is not None and style['stroke'] != 'none':
                    stroke_color = style['stroke']
                    if style['stroke-opacity'] is not None:
                        # fill opacity attribute overrides rgba property
                        stroke_alpha = float(style['stroke-opacity'])
                        if not 0 <= stroke_alpha <= 1:
                            logger.warning(f"Opacity value '{stroke_alpha}' should be in range [0.0..1.0]!")
                            stroke_alpha = 1
                if style['stroke-width'] is not None and style['stroke-width'] != 'none':
                    width = float(style['stroke-width'])
                    stroke_width = math.ceil(round(width/pixel_size, self.precision)/2)
                if style['fill'] is not None and style['fill'] != 'none':
                    fill_color = style['fill']
                    if style['fill-rule'] is not None:
                        fill_rule = style['fill-rule']
                    if style['fill-opacity'] is not None:
                        # fill opacity attribute overrides rgba property
                        fill_alpha = float(style['fill-opacity'])
                        if not 0 <= fill_alpha <= 1:
                            logger.warning(f"Opacity value '{fill_alpha}' should be in range [0.0..1.0]!")
                            fill_alpha = 1

            return (stroke_width, stroke_color, stroke_alpha, fill_color, fill_alpha, fill_rule, style['pathcut'])

        def straighten_line_chain(line_chain: LineSegmentChain) -> LineSegmentChain:
            """
            Make lines that connect and have the same inclination, one line.
            :return: LineSegmentChain, can be empty chain_size == 0 when all moves are 'non moves'
            """
            straight_chain = LineSegmentChain()
            prev_line = None

            for line in line_chain:
                # skip non move lines
                if line.start != line.end:
                    # stitch lines when the next line starts at the end of the previous line and they have the same slope
                    if prev_line and prev_line.end == line.start and prev_line.derivative() == line.derivative():
                        new_line = Line(prev_line.start, line.end)
                        straight_chain.set(-1, new_line)
                        prev_line = new_line
                        continue

                    straight_chain.append(line)
                    prev_line = line

            return straight_chain

        def line_crosses_lefttoright(y, cross_line: Line, direction_right: bool) -> bool:
            """
            True when line crosses from left to right seen from a point on line 'y' in indicated direction.
            """
            if cross_line.start.y < y < cross_line.end.y:
                # line crosses y pointing upwards
                return not direction_right
            # line crosses Y pointing down
            return direction_right

        def get_steps(stroke_width, pixel_size) -> list[float]:
            """
            Get steps/offsets of - a multiple of - pixelsize around a line.
            """
            steps = [0.0]
            if stroke_width:
                for delta in range(stroke_width):
                    if delta:
                        steps.append(round(delta * pixel_size, self.precision))
                        if not (delta == stroke_width and stroke_width % 2 != 0):
                            steps.append(round(-delta * pixel_size, self.precision))
            return steps

        def get_all_intersections(path_curves, y, lefttoright: bool) -> list[tuple[Line,int]]:
            """
            Get all intersections of paths for this 'y'
            """
            intersections_info = []

            for line_chain in path_curves:

                # catternate all segmented lines and skip 'non move' lines
                line_chain = straighten_line_chain(line_chain)

                # Calculate all intersections of lines with this horizontal line y
                for line in line_chain:

                    # calculate intersections
                    intersection = Line.horizontal_line_intersection(y, line, self.precision)
                    if intersection is not None:
                        # intersections_info.append((intersection[0], line))
                        intersections_info.append((intersection[0], -1 if line_crosses_lefttoright(y, line, lefttoright) else 1))

            # Sort x values left to right or right to left needed for o.a. 'fill lines'.
            intersections_info.sort(key=itemgetter(0), reverse = not lefttoright)

            return intersections_info
        #
        # Main append_curves
        #

        path_curves: dict[str, LineSegmentChain] = {}
        pixel_size = float(self.settings["pixel_size"])

        # depending on the curve type generate gcode for images and paths
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

        # Emit fill and stroke for all paths (organized by name id)
        for name_id in path_curves:

            # set a boundingbox per 'name_id'
            boundingbox = Boundingbox()

            # Render svg 'fill' attribute
            if not self.settings["nofill"]:
                # fill a path

                # update boundingbox for this 'name_id'
                for line_chain in path_curves[name_id]:
                    for line in line_chain:
                        boundingbox.update(line.start)
                        boundingbox.update(line.end)

                # get bounding box info from the path border
                lowerleft = boundingbox.get().lowerleft
                upperright = boundingbox.get().upperright

                # assume style info is the same for paths with the same id
                (stroke_width,
                 stroke_color,
                 stroke_alpha,
                 fill_color,
                 fill_alpha,
                 fill_rule,
                 style_pathcut) = get_style_info_of_line_chain(path_curves[name_id][0])

                # gcode
                code = [f"\n; {fill_rule} fill '{name_id}'"]
                code += [self.interface.set_laser_mode(self.settings["laser_mode"])]
                code += [self.interface.set_movement_speed(self.settings["image_movement_speed"])]

                if fill_color is not None and len(fill_color):
                    # Get fill alpha channel (opacity)
                    # fill opacity attribute overrides rgba property
                    if fill_alpha is None:
                        fill_alpha = 1
                        rgba = css_color.parse_css_color(fill_color)
                        if len(rgba) == 4:
                            fill_alpha = rgba[3]

                    # engrave values
                    # set inversed b&w value (and apply alpha channel, when available)
                    inverse_bw = round(Image2gcode.linear_power(css_color.parse_css_color2bw8(fill_color),
                                                          self.settings["maximum_image_laser_power"]) * fill_alpha)
                    # set laser power and fan when 'on' or 'engrave'
                    code += [self.interface.set_laser_power_value(inverse_bw, fan_on = (self.settings["fan"] == FAN_ON or self.settings["fan"] == FAN_ENGRAVE))]

                    # fill from left to right and reverse
                    lefttoright = True
                    for y in np.arange(round(lowerleft.y, self.precision), round(upperright.y, self.precision), pixel_size):

                        # get intersection info of paths with line 'y'
                        intersections_info = get_all_intersections(path_curves[name_id], y, lefttoright)

                        # draw fill lines
                        prev_x = 0.0
                        evenodd_count = 0
                        nonzero_count = 0

                        # iterate over all intersections for this 'y'
                        for x in intersections_info:
                            # if prev_x and nonzero_count:
                            if evenodd_count if fill_rule == "evenodd" else nonzero_count:
                                # draw fill line
                                # move to start of fill line account for borders (do not overwrite)
                                code += [self.interface.rapid_move(prev_x, y)]
                                # fill from start to end
                                code += [self.interface.linear_move((x[0]), y)]

                            prev_x = x[0]

                            # evenodd rule toggle 1 -> 0 and 0 -> 1
                            evenodd_count = not evenodd_count
                            # nonzero rule add edge +1 clockwise or edge -1 counterclockwise (depending on direction of view)
                            nonzero_count += x[1]

                        # switch fill direction
                        lefttoright = not lefttoright

                    # turn laser and fan off
                    code += [self.interface.laser_off(fan_off = (self.settings["fan"] == FAN_ON or self.settings["fan"] == FAN_ENGRAVE))]
                    code += [f"\n; end {fill_rule} fill '{name_id}'\n"]
                    # append gcode
                    self.body.extend(code)

            # Render 'stroke' attribute
            for line_chain in path_curves[name_id]:
                steps = []

                # get style info
                (stroke_width,
                 stroke_color,
                 stroke_alpha,
                 fill_color,
                 fill_alpha,
                 fill_rule,
                 style_pathcut) = get_style_info_of_line_chain(line_chain)

                # catternate lines and remove all 'non move' lines.
                line_chain = straighten_line_chain(line_chain)

                if line_chain.chain_size() == 0:
                    # no lines need no drawing
                    continue

                if (style_pathcut is not None and style_pathcut == 'true') or self.settings["pathcut"]:
                    # cut path
                    self.body.extend([f"\n; cut path (pathcut set) '{name_id}'"])
                    render_pathwidth(line_chain, [0], None, None, boundingbox)
                elif stroke_color is not None and len(stroke_color):
                    # Get stroke alpha channel (opacity)
                    # stroke opacity attribute overrides rgba property
                    if stroke_alpha is None:
                        stroke_alpha = 1
                        rgba = css_color.parse_css_color(stroke_color)
                        if len(rgba) == 4:
                            stroke_alpha = rgba[3]

                    # engrave values
                    # set inversed b&w value (and apply alpha channel, when available)
                    inverse_bw = round(Image2gcode.linear_power(css_color.parse_css_color2bw8(stroke_color),
                                                          self.settings["maximum_image_laser_power"]) * stroke_alpha)
                    # set laser head movement speed
                    speed = self.settings["image_movement_speed"]

                    # handle option color_coded
                    if self.settings["color_coded"]:
                        # get color_coded info
                        ignorepath, cutpath, engravepath = self.parse_color_coded(stroke_color)

                        if not ignorepath:

                            if cutpath:
                                # color_coded set cut path for this stroke_color
                                self.body.extend([f"\n; --color_coded cut path '{name_id}' (with stroke color '{stroke_color}')"])
                                render_pathwidth(line_chain, [0], None, None, boundingbox)
                                self.body.extend([self.interface.laser_off(fan_off = (self.settings["fan"] == FAN_ON or self.settings["fan"] == FAN_CUT))])
                                self.body.extend([f"\n; end --color_coded: cut path '{name_id}'\n"])
                            elif inverse_bw:
                                if engravepath:

                                    # Get steps (offsets) for the lines that make the border
                                    steps = get_steps(stroke_width, pixel_size)

                                    self.body.extend([f"\n; --color_coded: engrave path '{name_id}' with stroke color '{stroke_color}'"])
                                    render_pathwidth(line_chain, steps, inverse_bw, speed, boundingbox)
                                    # turn laser and fan off
                                    self.body.extend([self.interface.laser_off(fan_off = (self.settings["fan"] == FAN_ON or self.settings["fan"] == FAN_ENGRAVE))])
                                    self.body.extend([f"\n; end --color_coded: engrave path '{name_id}'\n"])
                                else:
                                    self.body.extend([f"\n; --color_coded: engrave not set for stroke color '{stroke_color}' of  path '{name_id}'"])
                        else:
                            # ignore path
                            self.body.extend([f"\n; --color_coded: ignore path '{name_id}' with stroke color '{stroke_color}'"])

                    elif inverse_bw:
                        # Get steps (offsets) for the lines that make the border
                        steps = get_steps(stroke_width, pixel_size)

                        # color_coded isn't set: engrave path with stroke color
                        self.body.extend([f"\n; engrave path (default) '{name_id}' with stroke color '{stroke_color}'"])
                        render_pathwidth(line_chain, steps, inverse_bw, speed, boundingbox)
                        # turn laser and fan off
                        self.body.extend([self.interface.laser_off(fan_off = (self.settings["fan"] == FAN_ON or self.settings["fan"] == FAN_ENGRAVE))])
                        self.body.extend([f"\n; end engrave path '{name_id}'\n"])
                else:
                    # cannot engrave path (ignore)
                    self.body.extend([f"\n; cannot engrave path '{name_id}': no stroke color set"])
