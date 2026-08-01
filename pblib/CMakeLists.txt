cmake_minimum_required(VERSION 3.15)
project(hermax_pblib LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(PBLIB_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/pblib/pblib")
file(GLOB PBLIB_CORE_SOURCES
    "${PBLIB_ROOT}/*.cpp"
    "${PBLIB_ROOT}/encoder/*.cpp")

if(HERMAX_CORE_ARCHIVE)
    add_library(pblib_core STATIC IMPORTED GLOBAL)
    set_target_properties(pblib_core PROPERTIES IMPORTED_LOCATION "${HERMAX_CORE_ARCHIVE}")
else()
    add_library(pblib_core STATIC ${PBLIB_CORE_SOURCES})
    target_include_directories(pblib_core PUBLIC
        "${PBLIB_ROOT}"
        "${PBLIB_ROOT}/encoder")
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

if(NOT DEFINED HERMAX_PBLIB_ENABLE_PYINT_CACHE)
    set(HERMAX_PBLIB_ENABLE_PYINT_CACHE 1)
endif()

add_library(_pblib MODULE src/pblib_capi.cpp)
target_include_directories(_pblib PRIVATE
    "${PBLIB_ROOT}"
    "${PBLIB_ROOT}/encoder"
    "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_compile_definitions(_pblib PRIVATE
    HERMAX_PBLIB_ENABLE_PYINT_CACHE=${HERMAX_PBLIB_ENABLE_PYINT_CACHE})
target_link_libraries(_pblib PRIVATE Python3::Module pblib_core)
set_target_properties(_pblib PROPERTIES
    PREFIX ""
    OUTPUT_NAME "_pblib"
    SUFFIX "${PYTHON_EXTENSION_SUFFIX}"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}")
