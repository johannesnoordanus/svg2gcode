## RUN test files.

The vector graphics *.svg* files in this directory are used by me to verify the validity of *svg2gcode*.
The outcome of the invocations below - the Gcode *.gc* files - should be similar for the same version of *svg2gcode*, in this case version 4.0.
Note that you can see the version of *svg2gcode* that produced the *.gc* file by looking at the header within this file.

```
 > svg2gcode --showimage kye_circle_paws_orig.svg kye_circle_paws_orig.gc
 > svg2gcode --showimage kye_circle_paws_orig\ copy.svg kye_circle_paws_orig\ copy.gc
 > svg2gcode letterandsigns.svg letterandsigns.gc
```

After running the above you can check the results against the accompanied zip file: *gcode_output.zip*. <br>
The result should be similar apart from things like the date etc.
It is also possible to check the result visually by running *gcode2image* and in a web-browser using ncviwer.com.
### In the first case run it so:
```
> gcode2image --showimage --flip kye_circle_paws_orig.gc kye_circle_paws_orig.png
> gcode2image --showimage --flip kye_circle_paws_orig\ copy.gc kye_circle_paws_orig.png
> gcode2image --showimage --flip letterandsigns.gc letterandsigns.png
``` 

### In the second case, type *ncviewer.com* in your browser search bar and type *enter*.

You can now drop any Gcode file on the left code pane (window) and look at the result.
This view is very precise and you can zoom in to see the very fine details, like exact line spacing and joining of the end point and exact fill in of the objects.
