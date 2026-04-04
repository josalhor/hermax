cmake_minimum_required(VERSION 3.15)
project(hermax.core.tt_openwbo_inc LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(TT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../tt-open-wbo-inc/code")

include_directories(
    "${TT_ROOT}"
    "${TT_ROOT}/solvers/topor"
)

file(GLOB SOURCES
    "${TT_ROOT}/*.cc"
    "${TT_ROOT}/algorithms/*.cc"
    "${TT_ROOT}/encodings/*.cc"
    "${TT_ROOT}/graph/*.cc"
    "${TT_ROOT}/clusterings/*.cc"
)

file(GLOB_RECURSE TOPOR_SOURCES
    "${TT_ROOT}/solvers/topor/core/*.cc"
    "${TT_ROOT}/solvers/topor/mtl/*.cc"
    "${TT_ROOT}/solvers/topor/utils/*.cc"
    "${TT_ROOT}/solvers/topor/topor/*.cc"
)

list(FILTER SOURCES EXCLUDE REGEX "/Main\\.cc$")
list(FILTER TOPOR_SOURCES EXCLUDE REGEX "solvers/topor/topor/Main\\.cc$")
list(APPEND SOURCES ${TOPOR_SOURCES})

pybind11_add_module(tt_openwbo_inc MODULE NO_EXTRAS tt_openwbo_bindings.cpp ${SOURCES})
target_link_libraries(tt_openwbo_inc PRIVATE Python3::Module pybind11::module)

target_compile_definitions(tt_openwbo_inc PRIVATE
    __STDC_LIMIT_MACROS
    __STDC_FORMAT_MACROS
    NSPACE=ToporWrapper
    SOLVERNAME=\"IntelSATSolver\"
    VERSION=core
    CLSIND=uint32_t
    COMPRESS=false
)

target_link_libraries(tt_openwbo_inc PRIVATE gmp gmpxx)

set_target_properties(tt_openwbo_inc PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
)
