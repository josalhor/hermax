cmake_minimum_required(VERSION 3.15)
project(hermax_evalmaxsat_latest LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(ZLIB REQUIRED)

set(EVALMAXSAT_LIB_ABS "" CACHE FILEPATH "Absolute path to libEvalMaxSAT.a")
set(GLUCOSE_LIB_ABS "" CACHE FILEPATH "Absolute path to libglucose.a")
set(CADICAL_LIB_ABS "" CACHE FILEPATH "Absolute path to libcadical.a")
set(EVALMAXSAT_ADAPTER_LIB_ABS "" CACHE FILEPATH "Absolute path to the cached Python-independent adapter archive")
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

execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '')"
  OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT PYTHON_EXTENSION_SUFFIX)
  message(FATAL_ERROR "Could not determine the Python extension suffix")
endif()

add_library(evalmaxsat_latest MODULE python/evalmaxsat_latest_bindings.cpp)
set_target_properties(evalmaxsat_latest PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")

target_link_libraries(evalmaxsat_latest PRIVATE
  Python3::Module
  ZLIB::ZLIB
  "${EVALMAXSAT_ADAPTER_LIB_ABS}"
  "${EVALMAXSAT_LIB_ABS}"
  "${GLUCOSE_LIB_ABS}"
  "${CADICAL_LIB_ABS}"
)

set_target_properties(evalmaxsat_latest PROPERTIES
  PREFIX ""
  OUTPUT_NAME "evalmaxsat_latest"
)
