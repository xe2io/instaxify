#!/bin/bash

SCRIPT_DIR=$(readlink -f $(dirname $0))
INPUT_DIR="input"
INSTAXIFY="$SCRIPT_DIR/instaxify_this.sh"

inotifywait --format '%f' -m -e close_write $INPUT_DIR | while read FILE
do
    $INSTAXIFY $FILE
done
