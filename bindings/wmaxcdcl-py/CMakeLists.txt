cmake_minimum_required(VERSION 3.15)
project(hermax_wmaxcdcl LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(WMAXCDCL_CODE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../solvers/WMaxCDCL_Paper/WMaxCDCL/code")

set(WMAXCDCL_SOURCES
    "${WMAXCDCL_CODE_DIR}/mtl/MDD.cc"
    "${WMAXCDCL_CODE_DIR}/utils/Options.cc"
    "${WMAXCDCL_CODE_DIR}/utils/System.cc"
    "${WMAXCDCL_CODE_DIR}/core/Solver.cc"
    "${WMAXCDCL_CODE_DIR}/core/sattime.cc"
    "${WMAXCDCL_CODE_DIR}/simp/SimpSolver.cc"
)

if(HERMAX_CORE_ARCHIVE)
    add_library(wmaxcdcl_core STATIC IMPORTED GLOBAL)
    set_target_properties(wmaxcdcl_core PROPERTIES IMPORTED_LOCATION "${HERMAX_CORE_ARCHIVE}")
else()
    add_library(wmaxcdcl_core STATIC ${WMAXCDCL_SOURCES})
endif()

if(NOT HERMAX_CORE_ARCHIVE)
    target_include_directories(wmaxcdcl_core PUBLIC "${WMAXCDCL_CODE_DIR}")
    target_compile_definitions(wmaxcdcl_core PRIVATE __STDC_LIMIT_MACROS __STDC_FORMAT_MACROS)
endif()

if(HERMAX_CORE_ONLY)
    return()
endif()

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)
find_package(ZLIB REQUIRED)

pybind11_add_module(wmaxcdcl MODULE NO_EXTRAS python/wmaxcdcl_bindings.cpp)
target_include_directories(wmaxcdcl PRIVATE "${WMAXCDCL_CODE_DIR}")
target_compile_definitions(wmaxcdcl PRIVATE __STDC_LIMIT_MACROS __STDC_FORMAT_MACROS)
target_link_libraries(wmaxcdcl PRIVATE Python3::Module pybind11::module wmaxcdcl_core ZLIB::ZLIB)

set_target_properties(wmaxcdcl PROPERTIES
  PREFIX ""
  OUTPUT_NAME "wmaxcdcl"
)
set_target_properties(wmaxcdcl PROPERTIES CXX_STANDARD 14 CXX_STANDARD_REQUIRED ON)
