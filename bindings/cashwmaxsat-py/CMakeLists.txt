cmake_minimum_required(VERSION 3.15)
project(hermax_cashwmaxsat LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)

set(UWR_LIB_ABS   "" CACHE FILEPATH "Absolute path to libuwrmaxsat.a")
set(CADICAL_A_ABS "" CACHE FILEPATH "Absolute path to libcadical.a")
set(COMINISATPS_A_ABS "" CACHE FILEPATH "Absolute path to libcominisatps.a")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

pybind11_add_module(cashwmaxsat MODULE NO_EXTRAS python/cashwmaxsat_bindings.cpp)

find_library(GMP_LIBRARY gmp REQUIRED)

target_link_libraries(cashwmaxsat PRIVATE
  Python3::Module
  pybind11::module
  "${UWR_LIB_ABS}"
  "${CADICAL_A_ABS}"
  "${COMINISATPS_A_ABS}"
  ${GMP_LIBRARY}
)

set_target_properties(cashwmaxsat PROPERTIES
  PREFIX ""
  OUTPUT_NAME "cashwmaxsat"
)
