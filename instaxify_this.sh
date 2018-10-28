#!/bin/bash

if [[ $# -lt 1 ]]; then
    echo "Usage: $(basename $0) <image>"
    exit 1
fi
imagename=$1
image="input/$1"

if [[ ! -r $image ]]; then
    echo "Unable to read specified image '$image'."
    exit 1
fi


# mogrify -path OUTPUT_PATH -filter Triangle -define filter:support=2 -thumbnail OUTPUT_WIDTH -unsharp 0.25x0.25+8+0.065 -dither None -posterize 136 -quality 82 -define jpeg:fancy-upsampling=off -define png:compression-filter=5 -define png:compression-level=9 -define png:compression-strategy=1 -define png:exclude-chunk=all -interlace none -colorspace sRGB -strip image

# mogrify -path OUTPUT_PATH -filter Triangle -define filter:support=2 -thumbnail OUTPUT_WIDTH -unsharp 0.25x0.25+8+0.065 -dither None -quality 82 -interlace none -colorspace sRGB image
# can we use a 640x640 to resize it to the right size?

OUTPUT_PATH="output/"
OUTPUT_WIDTH="640x640"
COMPLETED_PATH="completed/"

# Unsharp mask parameters (RADIUSxSIGMA+GAIN+THRESHOLD)
# radius - The radius of the Gaussian, in pixels, not counting the center pixel (default 0).
# sigma - The standard deviation of the Gaussian, in pixels (default 1.0).
# gain - The fraction of the difference between the original and the blur image that is added back into the original (default 1.0).
# threshold - The threshold, as a fraction of QuantumRange, needed to apply the difference amount (default 0.05).
UNSHARP="0.25x0.25+8+0.065"
UNSHARP="1.69x1.5+1+0.07"
UNSHARP="0x0.5+2+0"
UNSHARP="0x0.5+5+0"
QUALITY=100

# create output directory if it doesn't exist
if [[ ! -e $OUTPUT_PATH ]]; then
    mkdir -p $OUTPUT_PATH
fi

# create completed directory if it doesn't exist
if [[ ! -e $COMPLETED_PATH ]]; then
    mkdir -p $COMPLETED_PATH
fi

#time mogrify -path $OUTPUT_PATH -filter Triangle -define filter:support=2 -thumbnail $OUTPUT_WIDTH -unsharp $UNSHARP -dither None -quality $QUALITY -interlace none -colorspace sRGB $image


# Converting profile; profile needs a little bit of work
# convert SOURCE.jpg -strip -profile calibration/instax-sp1_00.icc  -intent perceptive|relative -black-point-compensation -profile /usr/share/color/icc/colord/sRGB.icc instax_OUTPUT.jpg 
#PROFILE=instax_CCDC_fujixt1_srgb.icc
PROFILE=calibration/instax-sp1_00.icc
SRGB=calibration/sRGB.icm
INTENT=absolute


mogrify -path $OUTPUT_PATH -filter Triangle -define filter:support=2 -thumbnail $OUTPUT_WIDTH -unsharp $UNSHARP -dither None -quality $QUALITY -interlace none -colorspace sRGB -strip -profile $PROFILE -intent $INTENT -black-point-compensation -profile $SRGB $image
rc=$?

echo "$(date '+%Y%m%d %H:%M:%S') Instaxify - $image [$rc]"

if [[ rc -eq 0 ]]; then
    mv $image $COMPLETED_PATH
fi
