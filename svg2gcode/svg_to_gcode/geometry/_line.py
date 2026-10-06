"""
Implementation of a line abstracted from Curve
"""
import math

from svg2gcode.svg_to_gcode.geometry import Vector
from svg2gcode.svg_to_gcode.geometry import Curve
from svg2gcode.svg_to_gcode import formulas

# A line segment
class Line(Curve):
    """The Line class inherits from the abstract Curve class and describes a straight line segment."""

    __slots__ = 'slope', 'offset', 'path_attrib'

    # class variable
    SMALL = float("1e-4")

    def __init__(self, start, end, path_attrib = None):
        self.start = start
        self.end = end

        self.slope = formulas.line_slope(start, end)
        self.offset = formulas.line_offset(start, end)
        self.path_attrib = path_attrib

    def __repr__(self):
        return f"Line(start:{self.start}, end:{self.end}, slope:{self.slope}, offset:{self.offset}, attrib:{self.path_attrib})"

    def length(self):
        """ get line length """
        return formulas.line_length(self.start,self.end)

    def point(self, t):
        x = self.start.x + t * (self.end.x - self.start.x)
        y = self.slope * x + self.offset

        return Vector(x, y)

    def derivative(self, t = None):
        return self.slope

    def sanity_check(self):
        return True

    @staticmethod
    def offset_line(offset: float, line, precision = 6) -> tuple[(Vector,Vector)]:
        """
        Offset a line perpendicular to the given line.
        """
        def perpendicular(line) -> tuple[(int,int)]:
            """
            Get sign of vector perpendicular to the given line,
            pointing outwards for a clockwise rotation.
            Return (sign x, sign y)
            """
            d_x = line.end.x - line.start.x
            d_y = line.end.y - line.start.y
            # normalize to values 0 or 1 (with sign)
            d_x = 0 if d_x == 0 else d_x/abs(d_x)
            d_y = 0 if d_y == 0 else d_y/abs(d_y)
            return (-d_y, d_x)

        delta_sign = perpendicular(line)

        # if line.slope ~ 0:
        if abs(line.slope) < Line.SMALL:
            # vertical line
            delta_x = 0
            delta_y = delta_sign[1] * offset
        #elif line.slope ~ 1:
        elif abs(line.slope - 1) < Line.SMALL:
            # horizontal line
            delta_x = delta_sign[0] * offset
            delta_y = 0
        else:
            # calculate orthogonal line of 'offset' length:
            #
            # (1)  y = 1/slope * x                          (line formula   )
            # (2)  x^2 + y^2                = offset^2      (Pythagoras     )
            # (3)  x^2 + (1/slope * x)^2    = offset^2      (substitue 'y'  )
            # (4)  (1 + (1/slope)^2) * x^2  = offset^2      (reorder        )
            # (5)  x^2 = offset^2 / (1 + (1/slope)^2)       (get 'x'        )
            # slope
            inv_slope = abs((1/line.slope))
            delta_x = round(math.sqrt((offset ** 2) / (1 + inv_slope ** 2)), precision)
            delta_y = round(inv_slope * delta_x, precision)

            # normalize offset
            offset = 0 if offset == 0 else offset/abs(offset)
            delta_x = delta_sign[0] * offset * delta_x
            delta_y = delta_sign[1] * offset * delta_y

        # add delta vector to line start and end vectors
        return Line(line.start + Vector(delta_x, delta_y), line.end + Vector(delta_x, delta_y))

    @staticmethod
    def horizontal_line_intersection(y, l1, precision = 6) -> Vector | None:
        """
        Horizontal line intersection
        Return intersection point of y and l1 or None when lines do not intersect or overlap.

        """
        x1, y1 = l1.start
        x2, y2 = l1.end

        if min(y1,y2) < y < max(y1,y2):
            x = x1 + (y - y1) * (x2 - x1)/(y2 - y1)
            if min(x1, x2) <= x <= max(x1, x2):
                return Vector(round(x, precision),round(y,precision))

        return None

    @staticmethod
    def line_intersection(l1, l2, strict = False, precision = 6) -> Vector | None:
        """
        Line intersection (https://en.wikipedia.org/wiki/Line–line_intersection)
        Return intersection point or None when lines do not intersect.
        When strict is set to True the intersection point must be on both line segments.

        """
        x1, y1 = l1.start
        x2, y2 = l1.end
        x3, y3 = l2.start
        x4, y4 = l2.end

        # denomintor
        d = (x1 - x2)*(y3 - y4) - (y1 - y2)*(x3 - x4)

        # Note that the cutoff below is needed to eliminate propagation of rounding errors.
        # The equations below are inherently sensitive to rounding errors at certain inputs.
        if abs(d) < 10**-precision:
            # no intersection
            return None

        intersect = Vector( round(((x1*y2 - y1*x2) * (x3 - x4) - (x1 - x2) * (x3*y4 - y3*x4))/d, precision),
                            round(((x1*y2 - y1*x2) * (y3 - y4) - (y1 - y2) * (x3*y4 - y3*x4))/d, precision) )
        if strict:
            # check intersect is on both line segments given a certain tolerance
            return intersect if ((min(x1, x2) - Line.SMALL) <= intersect.x <= (max(x1, x2) + Line.SMALL)      \
                                 and (min(x3, x4) - Line.SMALL) <= intersect.x <= (max(x3, x4) + Line.SMALL)  \
                                 and (min(y1, y2) - Line.SMALL) <= intersect.y <= (max(y1, y2) + Line.SMALL)  \
                                 and (min(y3, y4) - Line.SMALL) <= intersect.y <= (max(y3, y4) + Line.SMALL)) \
                             else None
        # lines intersect somewhere
        return intersect
