cmake_minimum_required(VERSION 3.15)
project(EvalMaxSAT LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find Python
find_package(Python3 COMPONENTS Interpreter REQUIRED)
find_package(Python3 COMPONENTS Development QUIET)

# Find pybind11
find_package(pybind11 REQUIRED)

add_subdirectory(lib/cadical)
add_subdirectory(lib/glucose)
add_subdirectory(lib/MaLib)
add_subdirectory(lib/EvalMaxSAT)
add_subdirectory(python) # Add the new python subdirectory
