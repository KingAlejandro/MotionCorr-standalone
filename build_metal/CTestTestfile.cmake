# CMake generated Testfile for 
# Source directory: /Users/alex.konstantinov/Documents/MotionCorr
# Build directory: /Users/alex.konstantinov/Documents/MotionCorr/build_metal
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test("SyntheticRegression" "/opt/homebrew/Caskroom/miniforge/base/bin/python3.13" "/Users/alex.konstantinov/Documents/MotionCorr/tests/test_synthetic_regression.py" "--binary" "/Users/alex.konstantinov/Documents/MotionCorr/build_metal/motioncorr")
set_tests_properties("SyntheticRegression" PROPERTIES  _BACKTRACE_TRIPLES "/Users/alex.konstantinov/Documents/MotionCorr/CMakeLists.txt;93;add_test;/Users/alex.konstantinov/Documents/MotionCorr/CMakeLists.txt;0;")
