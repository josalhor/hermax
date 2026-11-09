cmake_minimum_required(VERSION 3.15)
project(hermax_evalmaxsat_incr LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(Threads REQUIRED)

set(EVALMAXSAT_INCR_LIB_ABS "" CACHE FILEPATH "Absolute path to libipamirEvalMaxSAT2022.a")
set(EVALMAXSAT_INCR_ADAPTER_LIB_ABS "" CACHE FILEPATH "Absolute path to the cached Python-independent adapter archive")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

include_directories(
    "${CMAKE_CURRENT_SOURCE_DIR}/../../solvers/EvalMaxSAT2022"
)

execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '')"
  OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT PYTHON_EXTENSION_SUFFIX)
  message(FATAL_ERROR "Could not determine the Python extension suffix")
endif()

add_library(evalmaxsat_incr MODULE python/evalmaxsat_incr_bindings.cpp)
set_target_properties(evalmaxsat_incr PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")

find_package(ZLIB REQUIRED)

target_link_libraries(evalmaxsat_incr PRIVATE
  Python3::Module
  "${EVALMAXSAT_INCR_ADAPTER_LIB_ABS}"
  "${EVALMAXSAT_INCR_LIB_ABS}"
  ZLIB::ZLIB
  Threads::Threads
)

set_target_properties(evalmaxsat_incr PROPERTIES
  PREFIX ""
  OUTPUT_NAME "evalmaxsat_incr"
)
