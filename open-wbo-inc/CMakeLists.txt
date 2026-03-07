cmake_minimum_required(VERSION 3.15)
project(hermax.core.openwbo_inc LANGUAGES CXX)

# --- Find Python correctly ---
find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)

# Set C++ standard
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Define include directories
include_directories(
    .
    solvers/glucose4.1
)

# Define source files
file(GLOB SOURCES
    "*.cc"
    "algorithms/*.cc"
    "encodings/*.cc"
    "graph/*.cc"
    "clusterings/*.cc"
)

file(GLOB_RECURSE GLUCOSE_SOURCES
    "solvers/glucose4.1/core/*.cc"
    "solvers/glucose4.1/simp/*.cc"
    "solvers/glucose4.1/utils/*.cc"
)

list(FILTER SOURCES EXCLUDE REGEX "/Main\\.cc$")
list(FILTER GLUCOSE_SOURCES EXCLUDE REGEX "solvers/glucose4\\.1/simp/Main\\.cc$")
list(APPEND SOURCES ${GLUCOSE_SOURCES})

# Create the Python module
pybind11_add_module(openwbo_inc MODULE NO_EXTRAS openwbo_bindings.cpp ${SOURCES})

# Use modern link targets
target_link_libraries(openwbo_inc PRIVATE Python3::Module pybind11::module)

add_definitions(-D __STDC_LIMIT_MACROS -D __STDC_FORMAT_MACROS -D SIMP)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DNSPACE=Glucose")

# Force-include a shim header
target_compile_options(openwbo_inc PRIVATE
    -include ${CMAKE_CURRENT_SOURCE_DIR}/cmake/ns_compat.h
)

# Link against GMP
find_library(GMP_LIBRARY gmp)
find_library(GMPXX_LIBRARY gmpxx)

if(GMP_LIBRARY)
    target_link_libraries(openwbo_inc PRIVATE ${GMP_LIBRARY})
    if(GMPXX_LIBRARY)
        target_link_libraries(openwbo_inc PRIVATE ${GMPXX_LIBRARY})
    endif()
else()
    if(APPLE)
        if(EXISTS "/opt/homebrew/include")
            target_include_directories(openwbo_inc PRIVATE "/opt/homebrew/include")
        elif(EXISTS "/usr/local/include")
            target_include_directories(openwbo_inc PRIVATE "/usr/local/include")
        endif()
    endif()
endif()

# Ensure the .pyd lands where setuptools expects (Windows treats it as RUNTIME)
set_target_properties(openwbo_inc PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
)
