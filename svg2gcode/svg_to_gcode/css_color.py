"""
    css color module
    currently only partially implemented
    (definition from  https://www.w3.org/TR/css-color-3/)
"""
import logging
import math
import re

logging.basicConfig(format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

css_color_keywords = {
    "aliceblue": { "hex": "#F0F8FF", "decimal": [240,248,255] },
    "antiquewhite": { "hex": "#FAEBD7", "decimal": [250,235,215] },
    "aqua": { "hex": "#00FFFF", "decimal": [0,255,255] },
    "aquamarine": { "hex": "#7FFFD4", "decimal": [127,255,212] },
    "azure": { "hex": "#F0FFFF", "decimal": [240,255,255] },
    "beige": { "hex": "#F5F5DC", "decimal": [245,245,220] },
    "bisque": { "hex": "#FFE4C4", "decimal": [255,228,196] },
    "black": { "hex": "#000000", "decimal": [0,0,0] },
    "blanchedalmond": { "hex": "#FFEBCD", "decimal": [255,235,205] },
    "blue": { "hex": "#0000FF", "decimal": [0,0,255] },
    "blueviolet": { "hex": "#8A2BE2", "decimal": [138,43,226] },
    "brown": { "hex": "#A52A2A", "decimal": [165,42,42] },
    "burlywood": { "hex": "#DEB887", "decimal": [222,184,135] },
    "cadetblue": { "hex": "#5F9EA0", "decimal": [95,158,160] },
    "chartreuse": { "hex": "#7FFF00", "decimal": [127,255,0] },
    "chocolate": { "hex": "#D2691E", "decimal": [210,105,30] },
    "coral": { "hex": "#FF7F50", "decimal": [255,127,80] },
    "cornflowerblue": { "hex": "#6495ED", "decimal": [100,149,237] },
    "cornsilk": { "hex": "#FFF8DC", "decimal": [255,248,220] },
    "crimson": { "hex": "#DC143C", "decimal": [220,20,60] },
    "cyan": { "hex": "#00FFFF", "decimal": [0,255,255] },
    "darkblue": { "hex": "#00008B", "decimal": [0,0,139] },
    "darkcyan": { "hex": "#008B8B", "decimal": [0,139,139] },
    "darkgoldenrod": { "hex": "#B8860B", "decimal": [184,134,11] },
    "darkgray": { "hex": "#A9A9A9", "decimal": [169,169,169] },
    "darkgreen": { "hex": "#006400", "decimal": [0,100,0] },
    "darkgrey": { "hex": "#A9A9A9", "decimal": [169,169,169] },
    "darkkhaki": { "hex": "#BDB76B", "decimal": [189,183,107] },
    "darkmagenta": { "hex": "#8B008B", "decimal": [139,0,139] },
    "darkolivegreen": { "hex": "#556B2F", "decimal": [85,107,47] },
    "darkorange": { "hex": "#FF8C00", "decimal": [255,140,0] },
    "darkorchid": { "hex": "#9932CC", "decimal": [153,50,204] },
    "darkred": { "hex": "#8B0000", "decimal": [139,0,0] },
    "darksalmon": { "hex": "#E9967A", "decimal": [233,150,122] },
    "darkseagreen": { "hex": "#8FBC8F", "decimal": [143,188,143] },
    "darkslateblue": { "hex": "#483D8B", "decimal": [72,61,139] },
    "darkslategray": { "hex": "#2F4F4F", "decimal": [47,79,79] },
    "darkslategrey": { "hex": "#2F4F4F", "decimal": [47,79,79] },
    "darkturquoise": { "hex": "#00CED1", "decimal": [0,206,209] },
    "darkviolet": { "hex": "#9400D3", "decimal": [148,0,211] },
    "deeppink": { "hex": "#FF1493", "decimal": [255,20,147] },
    "deepskyblue": { "hex": "#00BFFF", "decimal": [0,191,255] },
    "dimgray": { "hex": "#696969", "decimal": [105,105,105] },
    "dimgrey": { "hex": "#696969", "decimal": [105,105,105] },
    "dodgerblue": { "hex": "#1E90FF", "decimal": [30,144,255] },
    "firebrick": { "hex": "#B22222", "decimal": [178,34,34] },
    "floralwhite": { "hex": "#FFFAF0", "decimal": [255,250,240] },
    "forestgreen": { "hex": "#228B22", "decimal": [34,139,34] },
    "fuchsia": { "hex": "#FF00FF", "decimal": [255,0,255] },
    "gainsboro": { "hex": "#DCDCDC", "decimal": [220,220,220] },
    "ghostwhite": { "hex": "#F8F8FF", "decimal": [248,248,255] },
    "gold": { "hex": "#FFD700", "decimal": [255,215,0] },
    "goldenrod": { "hex": "#DAA520", "decimal": [218,165,32] },
    "gray": { "hex": "#808080", "decimal": [128,128,128] },
    "green": { "hex": "#008000", "decimal": [0,128,0] },
    "greenyellow": { "hex": "#ADFF2F", "decimal": [173,255,47] },
    "grey": { "hex": "#808080", "decimal": [128,128,128] },
    "honeydew": { "hex": "#F0FFF0", "decimal": [240,255,240] },
    "hotpink": { "hex": "#FF69B4", "decimal": [255,105,180] },
    "indianred": { "hex": "#CD5C5C", "decimal": [205,92,92] },
    "indigo": { "hex": "#4B0082", "decimal": [75,0,130] },
    "ivory": { "hex": "#FFFFF0", "decimal": [255,255,240] },
    "khaki": { "hex": "#F0E68C", "decimal": [240,230,140] },
    "lavender": { "hex": "#E6E6FA", "decimal": [230,230,250] },
    "lavenderblush": { "hex": "#FFF0F5", "decimal": [255,240,245] },
    "lawngreen": { "hex": "#7CFC00", "decimal": [124,252,0] },
    "lemonchiffon": { "hex": "#FFFACD", "decimal": [255,250,205] },
    "lightblue": { "hex": "#ADD8E6", "decimal": [173,216,230] },
    "lightcoral": { "hex": "#F08080", "decimal": [240,128,128] },
    "lightcyan": { "hex": "#E0FFFF", "decimal": [224,255,255] },
    "lightgoldenrodyellow": { "hex": "#FAFAD2", "decimal": [250,250,210] },
    "lightgray": { "hex": "#D3D3D3", "decimal": [211,211,211] },
    "lightgreen": { "hex": "#90EE90", "decimal": [144,238,144] },
    "lightgrey": { "hex": "#D3D3D3", "decimal": [211,211,211] },
    "lightpink": { "hex": "#FFB6C1", "decimal": [255,182,193] },
    "lightsalmon": { "hex": "#FFA07A", "decimal": [255,160,122] },
    "lightseagreen": { "hex": "#20B2AA", "decimal": [32,178,170] },
    "lightskyblue": { "hex": "#87CEFA", "decimal": [135,206,250] },
    "lightslategray": { "hex": "#778899", "decimal": [119,136,153] },
    "lightslategrey": { "hex": "#778899", "decimal": [119,136,153] },
    "lightsteelblue": { "hex": "#B0C4DE", "decimal": [176,196,222] },
    "lightyellow": { "hex": "#FFFFE0", "decimal": [255,255,224] },
    "lime": { "hex": "#00FF00", "decimal": [0,255,0] },
    "limegreen": { "hex": "#32CD32", "decimal": [50,205,50] },
    "linen": { "hex": "#FAF0E6", "decimal": [250,240,230] },
    "magenta": { "hex": "#FF00FF", "decimal": [255,0,255] },
    "maroon": { "hex": "#800000", "decimal": [128,0,0] },
    "mediumaquamarine": { "hex": "#66CDAA", "decimal": [102,205,170] },
    "mediumblue": { "hex": "#0000CD", "decimal": [0,0,205] },
    "mediumorchid": { "hex": "#BA55D3", "decimal": [186,85,211] },
    "mediumpurple": { "hex": "#9370DB", "decimal": [147,112,219] },
    "mediumseagreen": { "hex": "#3CB371", "decimal": [60,179,113] },
    "mediumslateblue": { "hex": "#7B68EE", "decimal": [123,104,238] },
    "mediumspringgreen": { "hex": "#00FA9A", "decimal": [0,250,154] },
    "mediumturquoise": { "hex": "#48D1CC", "decimal": [72,209,204] },
    "mediumvioletred": { "hex": "#C71585", "decimal": [199,21,133] },
    "midnightblue": { "hex": "#191970", "decimal": [25,25,112] },
    "mintcream": { "hex": "#F5FFFA", "decimal": [245,255,250] },
    "mistyrose": { "hex": "#FFE4E1", "decimal": [255,228,225] },
    "moccasin": { "hex": "#FFE4B5", "decimal": [255,228,181] },
    "navajowhite": { "hex": "#FFDEAD", "decimal": [255,222,173] },
    "navy": { "hex": "#000080", "decimal": [0,0,128] },
    "oldlace": { "hex": "#FDF5E6", "decimal": [253,245,230] },
    "olive": { "hex": "#808000", "decimal": [128,128,0] },
    "olivedrab": { "hex": "#6B8E23", "decimal": [107,142,35] },
    "orange": { "hex": "#FFA500", "decimal": [255,165,0] },
    "orangered": { "hex": "#FF4500", "decimal": [255,69,0] },
    "orchid": { "hex": "#DA70D6", "decimal": [218,112,214] },
    "palegoldenrod": { "hex": "#EEE8AA", "decimal": [238,232,170] },
    "palegreen": { "hex": "#98FB98", "decimal": [152,251,152] },
    "paleturquoise": { "hex": "#AFEEEE", "decimal": [175,238,238] },
    "palevioletred": { "hex": "#DB7093", "decimal": [219,112,147] },
    "papayawhip": { "hex": "#FFEFD5", "decimal": [255,239,213] },
    "peachpuff": { "hex": "#FFDAB9", "decimal": [255,218,185] },
    "peru": { "hex": "#CD853F", "decimal": [205,133,63] },
    "pink": { "hex": "#FFC0CB", "decimal": [255,192,203] },
    "plum": { "hex": "#DDA0DD", "decimal": [221,160,221] },
    "powderblue": { "hex": "#B0E0E6", "decimal": [176,224,230] },
    "purple": { "hex": "#800080", "decimal": [128,0,128] },
    "red": { "hex": "#FF0000", "decimal": [255,0,0] },
    "rosybrown": { "hex": "#BC8F8F", "decimal": [188,143,143] },
    "royalblue": { "hex": "#4169E1", "decimal": [65,105,225] },
    "saddlebrown": { "hex": "#8B4513", "decimal": [139,69,19] },
    "salmon": { "hex": "#FA8072", "decimal": [250,128,114] },
    "sandybrown": { "hex": "#F4A460", "decimal": [244,164,96] },
    "seagreen": { "hex": "#2E8B57", "decimal": [46,139,87] },
    "seashell": { "hex": "#FFF5EE", "decimal": [255,245,238] },
    "sienna": { "hex": "#A0522D", "decimal": [160,82,45] },
    "silver": { "hex": "#C0C0C0", "decimal": [192,192,192] },
    "skyblue": { "hex": "#87CEEB", "decimal": [135,206,235] },
    "slateblue": { "hex": "#6A5ACD", "decimal": [106,90,205] },
    "slategray": { "hex": "#708090", "decimal": [112,128,144] },
    "slategrey": { "hex": "#708090", "decimal": [112,128,144] },
    "snow": { "hex": "#FFFAFA", "decimal": [255,250,250] },
    "springgreen": { "hex": "#00FF7F", "decimal": [0,255,127] },
    "steelblue": { "hex": "#4682B4", "decimal": [70,130,180] },
    "tan": { "hex": "#D2B48C", "decimal": [210,180,140] },
    "teal": { "hex": "#008080", "decimal": [0,128,128] },
    "thistle": { "hex": "#D8BFD8", "decimal": [216,191,216] },
    "tomato": { "hex": "#FF6347", "decimal": [255,99,71] },
    "turquoise": { "hex": "#40E0D0", "decimal": [64,224,208] },
    "violet": { "hex": "#EE82EE", "decimal": [238,130,238] },
    "wheat": { "hex": "#F5DEB3", "decimal": [245,222,179] },
    "white": { "hex": "#FFFFFF", "decimal": [255,255,255] },
    "whitesmoke": { "hex": "#F5F5F5", "decimal": [245,245,245] },
    "yellow": { "hex": "#FFFF00", "decimal": [255,255,0] },
    "yellowgreen": { "hex": "#9ACD32", "decimal": [154,205,50] },
}

def hsl2rgb(hue, sat, light) -> [int,int,int]:
    """
        Convert 'hsl(' color notation to rgb.
        (definition from  https://www.w3.org/TR/css-color-3/)
        It returns an array of three numbers representing the red, green, and blue channels of the colors, normalized to the range [0, 1]
        (This means the return values for r,g and b must be multiplied by the color range (0..255) to get the actual rgb values)
    """
    hue = hue % 360

    if (hue < 0):
        hue += 360

    sat /= 100
    light /= 100

    def f(n):
        k = (n + hue/30) % 12
        a = sat * min(light, 1 - light)
        return light - a * max(-1, min(k - 3, 9 - k, 1))

    return [f(0), f(8), f(4)]

def hex2rgb(hexcolor: str) -> [int,int,int]:

    rgbcolor = int(hexcolor, 16)
    r = rgbcolor >> 16
    g = rgbcolor >> 8 & 255
    b = rgbcolor & 255

    return [r,g,b]

def parse_css_color(color: str) -> [int,int,int]:
    """
        parse css color to rgb
        (definition from  https://www.w3.org/TR/css-color-3/)

        accept '#hex', 'rgb(', 'rgba(', 'hsl(' and 'hsla(' color schemes.
    """
    float_re = '(\d*\.)?\d+'
    rgbcolor = 0

    if color in css_color_keywords:
        rgbcolor = css_color_keywords[color]["decimal"]
    else:
        hexcolor = re.search('#[A-Fa-f0-9]+', color)
        if hexcolor:
            hexcolor = re.search('[A-Fa-f0-9]+', hexcolor.group(0)).group(0)
            if len(hexcolor) == 3:
                hexcolor = hexcolor[0] + hexcolor[0] + hexcolor[1] + hexcolor[1] + hexcolor[2] + hexcolor[2]

            rgbcolor = hex2rgb(hexcolor)
        else:
            rgba = re.search(f"rgb(a)?\([0-9]+,[0-9]+,[0-9]+(,{float_re})?", color)
            # '(\d*\.)?\d+'
            if rgba:
                # set alpha to non transparant
                a = 1
                rgb = re.search(f"\([0-9]+,[0-9]+,[0-9]+(,{float_re})?", rgba.group(0)).group(0)[1:]

                commas_pos = [cpos for cpos, char in enumerate(rgb) if char == ',']
                r = int(rgb[0:commas_pos[0]])
                g = int(rgb[commas_pos[0]+1:commas_pos[1]])
                if len(commas_pos) == 3:
                    b = int(rgb[commas_pos[1]+1:commas_pos[2]])
                    a = float(rgb[commas_pos[2]+1:])
                else:
                    b = int(rgb[commas_pos[1]+1:])

                rgbcolor = [r * a, g * a, b * a]

            else:
                hsla = re.search(f"hsl(a)?\([0-9]+,[0-9]+,[0-9]+(,{float_re})?", color)
                if hsla:
                    # set alpha to non transparant
                    a = 1
                    hsl = re.search(f"\([0-9]+,[0-9]+,[0-9]+(,{float_re})?", hsla.group(0)).group(0)[1:]

                    commas_pos = [cpos for cpos, char in enumerate(hsl) if char == ',']
                    h = int(hsl[0:commas_pos[0]])
                    s = int(hsl[commas_pos[0]+1:commas_pos[1]])

                    if len(commas_pos) == 3:
                        l = int(hsl[commas_pos[1]+1:commas_pos[2]])
                        a = float(hsl[commas_pos[2]+1:])
                    else:
                        l = int(hsl[commas_pos[1]+1:])

                    rgbcolor = hsl2rgb(h, s, l)
                    rgbcolor = [int(rgbcolor[0] * 255 * a), int(rgbcolor[1] * 255 * a), int(rgbcolor[2] * 255 * a)]

    if not rgbcolor:
        logger.warn(f"Not a valid css color: '{color}', color set to 'black'!")
        rgbcolor = css_color_keywords['black']["decimal"]

    return rgbcolor

def rgb24tobw24(rgb24: int) -> int:
    """
        convert a 24 bit rgb (color) value to 24 bit grayscale
    """
    r = col >> 16;
    g = (col >> 8) & 0xff;
    b = col & 0xff;
    bnw = int(r * 0.299 + g * 0.587 + b * 0.114) & 0xff;
    return (bnw << 16) | (bnw << 8) | bnw;

def rgb24tobw8(rgb24: [int,int,int]) -> int:
    """
        convert a 24 bit rgb (color) value to 8 bit grayscale
    """
    return int(rgb24[0] * 0.299 + rgb24[1] * 0.587 + rgb24[2] * 0.114) & 0xff

def parse_css_color2bw8(color: str) -> int:
    """
    parse css color string to 8 bit b&w value
    (definition from  https://www.w3.org/TR/css-color-3/)

    accept '#hex', 'rgb(', 'rgba(', 'hsl(' and 'hsla(' color schemes.
    """
    return rgb24tobw8(parse_css_color(color))

if __name__ == '__main__':
    print("--------------------------------")
    print("keyword saddlebrown:", css_color_keywords["saddlebrown"]["hex"])
    print("--------------------------------")
    print("keyword saddlebrown (decimal):", css_color_keywords["saddlebrown"]["decimal"])
    print("--------------------------------")
    print(hsl2rgb(0,100,50))
    print("--------------------------------")
    print(hsl2rgb(120,100,50))
    print("--------------------------------")
    print("#hexcolor:", parse_css_color("#" + css_color_keywords["saddlebrown"]["hex"]))
    print("--------------------------------")
    print("#FBA:", parse_css_color("#FBA"))
    print("--------------------------------")
    print("hsl(120,100,50):", parse_css_color("hsl(120,100,50)"))
    print("--------------------------------")
    print("hsla(120,100,50,.5):", parse_css_color("hsla(120,100,50,.5)"))
    print("--------------------------------")
    print("hsla(120,100,50,.25):", parse_css_color("hsla(120,100,50,.25)"))
    print("--------------------------------")
    print("rgb(139,69,19):", parse_css_color("rgb(139,69,19)"))
    print("--------------------------------")
    print("rgba(139,69,19,.25):", parse_css_color("rgb(139,69,19,.25)"))
    print("--------------------------------")
