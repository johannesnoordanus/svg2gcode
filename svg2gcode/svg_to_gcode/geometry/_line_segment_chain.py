from svg2gcode.svg_to_gcode.geometry import Chain
from svg2gcode.svg_to_gcode.geometry import Curve, Line, Vector
from svg2gcode.svg_to_gcode import TOLERANCES


class LineSegmentChain(Chain):
    """
    The LineSegmentChain class inherits form the abstract Chain class. It represents a series of continuous straight
    line-segments.

    LineSegmentChains can be instantiated either conventionally or through the static method line_segment_approximation(),
    which approximates any Curve with a series of line-segments contained in a new LineSegmentChain instance.
    """
    def __repr__(self):
        return f"{type(self)}({len(self._curves)} curves: {[line.__repr__() for line in self._curves[:2]]}...)"

    def append(self, line2: Line):
        if self._curves:
            line1 = self._curves[-1]

            # Assert continuity
            if abs(line1.end - line2.start) > TOLERANCES['input']:
                raise ValueError(f"The end of the last line is different from the start of the new line"
                                 f"|{line1.end} - {line2.start}| >= {TOLERANCES['input']}")

            # Join lines
            line2.start = line1.end

        self._curves.append(line2)

    @staticmethod
    def clockwise(line_chain, delta: float = .1) -> bool:
        """
        Return true when line chain rotates clockwise using sample delta

        """
        # bbox_line_chain = bbox(line_chain)
        # bbox_delta_chain = bbox(delta_chain(line_chain, delta))
        # if bbox_delta_chain > bbox_line_chain:
        #       return true
        # return false
        pass

    @staticmethod
    def delta_chain(line_chain, offset: float) -> "LineSegmentChain":
        """
        Return a line chain offset to the given chain. If the chain rotates clockwise a positive offset
        results in a delta chain outwards of (enclosing) the given line chain.

        """
        delta_chain = LineSegmentChain()

        for line in line_chain:
            line_delta = Line.offset_line(offset, line)

            if delta_chain.chain_size():
                # calculate intersection of previous line and current line
                intersect = Line.line_intersection(delta_chain.get(-1), line_delta)
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
            intersect = Line.line_intersection(delta_chain.get(0), delta_chain.get(-1))
            if intersect is not None:
                # update start of loop
                start_loop = delta_chain.get(0)
                start_loop.start = intersect
                delta_chain.set(0, start_loop)

                # update end of loop
                end_loop = delta_chain.get(-1)
                end_loop.end = intersect
                delta_chain.set(-1, end_loop)

        return delta_chain

    @staticmethod
    def line_segment_approximation(shape, increment_growth=11 / 10, error_cap=None, error_floor=None)\
            -> "LineSegmentChain":
        """
        This method approximates any shape using straight line segments.

        :param shape: The shape to be approximated.
        :param increment_growth: the scale by which line_segments grow and shrink. Must be > 1.
        :param error_cap: the maximum acceptable deviation from the curve.
        :param error_floor: the maximum minimum deviation from the curve before segment length starts growing again.
        :return: A LineSegmentChain which approximates the given shape.
        """

        error_cap = TOLERANCES['approximation'] if error_cap is None else error_cap
        error_floor = (increment_growth - 1) * error_cap if error_floor is None else error_floor

        if error_cap <= 0:
            raise ValueError(f"This algorithm is approximate. error_cap must be a non-zero positive float. Not {error_cap}")

        if increment_growth <= 1:
            raise ValueError(f"increment_growth must be > 1. Not {increment_growth}")

        lines = LineSegmentChain()

        if isinstance(shape, Line):
            lines.append(shape)
            return lines

        t = 0
        line_start = shape.start
        increment = 5

        while t < 1:
            new_t = t + increment

            if new_t > 1:
                new_t = 1

            line_end = shape.point(new_t)
            line = Line(line_start, line_end, shape.path_attrib)

            distance = Curve.max_distance(shape, line, t_range1=(t, new_t))

            # If the error is too high, reduce increment and restart cycle
            if distance > error_cap:
                increment /= increment_growth
                continue

            # If the error is very low, increase increment but DO NOT restart cycle.
            if distance < error_floor:
                increment *= increment_growth

            lines.append(line)

            line_start = line_end
            t = new_t

        return lines
