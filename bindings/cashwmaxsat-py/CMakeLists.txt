cmake_minimum_required(VERSION 3.15)
project(hermax_cashwmaxsat LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)

set(UWR_LIB_ABS   "" CACHE FILEPATH "Absolute path to libuwrmaxsat.a")
set(CADICAL_A_ABS "" CACHE FILEPATH "Absolute path to libcadical.a")
set(COMINISATPS_A_ABS "" CACHE FILEPATH "Absolute path to libcominisatps.a")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '')"
  OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT PYTHON_EXTENSION_SUFFIX)
  message(FATAL_ERROR "Could not determine the Python extension suffix")
endif()

add_library(cashwmaxsat MODULE python/cashwmaxsat_bindings.cpp)
set_target_properties(cashwmaxsat PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")

find_library(GMP_LIBRARY gmp REQUIRED)

target_link_libraries(cashwmaxsat PRIVATE
  Python3::Module
  "${UWR_LIB_ABS}"
  "${CADICAL_A_ABS}"
  "${COMINISATPS_A_ABS}"
  ${GMP_LIBRARY}
)

set_target_properties(cashwmaxsat PROPERTIES
  PREFIX ""
  OUTPUT_NAME "cashwmaxsat"
)
