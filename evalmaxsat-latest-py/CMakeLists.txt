cmake_minimum_required(VERSION 3.15)
project(hermax_evalmaxsat_latest LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)

set(EVALMAXSAT_LIB_ABS "" CACHE FILEPATH "Absolute path to libEvalMaxSAT.a")
set(GLUCOSE_LIB_ABS "" CACHE FILEPATH "Absolute path to libglucose.a")
set(CADICAL_LIB_ABS "" CACHE FILEPATH "Absolute path to libcadical.a")
set(EVALMAXSAT_INC_DIR "" CACHE PATH "Include dir for EvalMaxSAT")
set(MALIB_INC_DIR "" CACHE PATH "Include dir for MaLib")
set(CADICAL_INC_DIR "" CACHE PATH "Include dir for cadical")
set(GLUCOSE_INC_DIR "" CACHE PATH "Include dir for glucose")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

include_directories(
    "${EVALMAXSAT_INC_DIR}"
    "${MALIB_INC_DIR}"
    "${CADICAL_INC_DIR}"
    "${GLUCOSE_INC_DIR}"
)

pybind11_add_module(evalmaxsat_latest MODULE NO_EXTRAS python/evalmaxsat_latest_bindings.cpp)

target_link_libraries(evalmaxsat_latest PRIVATE
  Python3::Module
  pybind11::module
  "${EVALMAXSAT_LIB_ABS}"
  "${GLUCOSE_LIB_ABS}"
  "${CADICAL_LIB_ABS}"
)

set_target_properties(evalmaxsat_latest PROPERTIES
  PREFIX ""
  OUTPUT_NAME "evalmaxsat_latest"
)
