#!/bin/sh
python setup.py build

# set the mantidpython to use - default to system installed nightly
if [ $1 ]; then
    MANTIDPYTHON="$1"
else
    MANTIDPYTHON=mantidpythonnightly
fi

# check that a valid mantidpython was specified
if [ ! $(command -v $MANTIDPYTHON) ]; then
    echo "Failed to find mantidpython \"$MANTIDPYTHON\""
    exit -1
fi

# let people know what is going on and launch it
echo "Using \"$(which $MANTIDPYTHON)\""
# tests/QuickCalibration.py Doesn't appear to be a test
PYTHONPATH=`pwd`/build/lib $MANTIDPYTHON --classic -m pytest -vv tests/unit
# tests/gui core dumps
