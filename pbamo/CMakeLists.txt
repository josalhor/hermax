cmake_minimum_required(VERSION 3.15)
project(hermax_pbamo LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(PBAMO_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/include")
set(PBAMO_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src")
set(PBAMO_CORE_SOURCES
    "${PBAMO_SRC_DIR}/mdd.cpp"
    "${PBAMO_SRC_DIR}/gswc.cpp"
    "${PBAMO_SRC_DIR}/ggpw.cpp"
    "${PBAMO_SRC_DIR}/gmto.cpp"
    "${PBAMO_SRC_DIR}/rggt.cpp"
    "${PBAMO_SRC_DIR}/registry.cpp")

if(HERMAX_CORE_ARCHIVE)
    add_library(pbamo_core STATIC IMPORTED GLOBAL)
    set_target_properties(pbamo_core PROPERTIES IMPORTED_LOCATION "${HERMAX_CORE_ARCHIVE}")
else()
    add_library(pbamo_core STATIC ${PBAMO_CORE_SOURCES})
    target_include_directories(pbamo_core PUBLIC "${PBAMO_INCLUDE_DIR}" "${PBAMO_SRC_DIR}")
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

add_library(_pbamo MODULE src/pbamo_capi.cpp)
target_include_directories(_pbamo PRIVATE "${PBAMO_INCLUDE_DIR}" "${PBAMO_SRC_DIR}")
target_link_libraries(_pbamo PRIVATE Python3::Module pbamo_core)
set_target_properties(_pbamo PROPERTIES
    PREFIX ""
    OUTPUT_NAME "_pbamo"
    SUFFIX "${PYTHON_EXTENSION_SUFFIX}"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}")
