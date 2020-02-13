#!/bin/bash
# scrub.sh uses the autopep8 tool to clean up whitespace and other small bits

# E26  - Fix spacing after comment hash for inline comments.
# E265 - Fix spacing after comment hash for block comments.
# E266 - Fix too many leading '#' for block comments.
# E261 = double space before inline comment
# E501 = don't squeeze lines to fix max length
# E302 = don't go crazy with the double whitespace between funcs
# E401 = don't put imports on separate lines
# E305 = don't put two blank lines after the last function
# E309 = don't put a blank line after class declaration
# E731 = don't assign a lambda expression check.
# W690 = don't try to make code more compatible for python3. 2to3 will do this for us eventually

autopep8 \
    --in-place --recursive --aggressive \
    --ignore E26,E265,E266,E501,E302,E261,E401,E305,E309,E731,W690 \
    --exclude *.html \
    src/
