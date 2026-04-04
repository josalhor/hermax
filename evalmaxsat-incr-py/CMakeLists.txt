cmake_minimum_required(VERSION 3.15)
project(hermax_evalmaxsat_incr LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)
find_package(Threads REQUIRED)

set(EVALMAXSAT_INCR_LIB_ABS "" CACHE FILEPATH "Absolute path to libipamirEvalMaxSAT2022.a")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

include_directories(
    "${CMAKE_CURRENT_SOURCE_DIR}/../EvalMaxSAT2022"
)

pybind11_add_module(evalmaxsat_incr MODULE NO_EXTRAS python/evalmaxsat_incr_bindings.cpp)

find_package(ZLIB REQUIRED)

target_link_libraries(evalmaxsat_incr PRIVATE
  Python3::Module
  pybind11::module
  "${EVALMAXSAT_INCR_LIB_ABS}"
  ZLIB::ZLIB
  Threads::Threads
)

set_target_properties(evalmaxsat_incr PROPERTIES
  PREFIX ""
  OUTPUT_NAME "evalmaxsat_incr"
)
