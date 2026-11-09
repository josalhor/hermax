cmake_minimum_required(VERSION 3.15)
project(hermax.core.openwbo_inc LANGUAGES CXX)

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
list(APPEND SOURCES openwbo_inc_native.cpp)

file(GLOB_RECURSE GLUCOSE_SOURCES
    "solvers/glucose4.1/core/*.cc"
    "solvers/glucose4.1/simp/*.cc"
    "solvers/glucose4.1/utils/*.cc"
)

list(FILTER SOURCES EXCLUDE REGEX "/Main\\.cc$")
list(FILTER GLUCOSE_SOURCES EXCLUDE REGEX "solvers/glucose4\\.1/simp/Main\\.cc$")
list(APPEND SOURCES ${GLUCOSE_SOURCES})

if(HERMAX_CORE_ARCHIVE)
    add_library(openwbo_inc_core STATIC IMPORTED GLOBAL)
    set_target_properties(openwbo_inc_core PROPERTIES IMPORTED_LOCATION "${HERMAX_CORE_ARCHIVE}")
else()
    add_library(openwbo_inc_core STATIC ${SOURCES})
endif()
if(NOT HERMAX_CORE_ARCHIVE)
    target_compile_definitions(openwbo_inc_core PRIVATE
        __STDC_LIMIT_MACROS
        __STDC_FORMAT_MACROS
        SIMP
        NSPACE=Glucose
    )

    # Force-include a shim header
    target_compile_options(openwbo_inc_core PRIVATE
        -include ${CMAKE_CURRENT_SOURCE_DIR}/cmake/ns_compat.h
    )
endif()

if(HERMAX_CORE_ONLY)
    return()
endif()

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '')"
  OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT PYTHON_EXTENSION_SUFFIX)
  message(FATAL_ERROR "Could not determine the Python extension suffix")
endif()

add_library(openwbo_inc MODULE openwbo_bindings.cpp)
set_target_properties(openwbo_inc PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")
target_link_libraries(openwbo_inc PRIVATE Python3::Module openwbo_inc_core)

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
  PREFIX ""
)
