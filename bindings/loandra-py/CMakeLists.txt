cmake_minimum_required(VERSION 3.15)
project(hermax.core.loandra LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(LOANDRA_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../solvers/Loandra/code")

include_directories(
    "${LOANDRA_ROOT}"
    "${LOANDRA_ROOT}/solvers/glucose4.1"
)

file(GLOB SOURCES
    "${LOANDRA_ROOT}/*.cc"
    "${LOANDRA_ROOT}/algorithms/*.cc"
    "${LOANDRA_ROOT}/encodings/*.cc"
    "${LOANDRA_ROOT}/graph/*.cc"
    "${LOANDRA_ROOT}/clusterings/*.cc"
)

file(GLOB_RECURSE GLUCOSE_SOURCES
    "${LOANDRA_ROOT}/solvers/glucose4.1/core/*.cc"
    "${LOANDRA_ROOT}/solvers/glucose4.1/simp/*.cc"
    "${LOANDRA_ROOT}/solvers/glucose4.1/utils/*.cc"
)

list(FILTER SOURCES EXCLUDE REGEX "/Main\\.cc$")
list(FILTER SOURCES EXCLUDE REGEX "/algorithms/Alg_CBLIN\\.cc$")
list(FILTER SOURCES EXCLUDE REGEX "/algorithms/Alg_OLL_ITER\\.cc$")
list(FILTER GLUCOSE_SOURCES EXCLUDE REGEX "solvers/glucose4\\.1/simp/Main\\.cc$")
list(APPEND SOURCES ${GLUCOSE_SOURCES})
list(APPEND SOURCES loandra_native.cpp)

if(HERMAX_CORE_ARCHIVE)
    add_library(loandra_core STATIC IMPORTED GLOBAL)
    set_target_properties(loandra_core PROPERTIES IMPORTED_LOCATION "${HERMAX_CORE_ARCHIVE}")
else()
    add_library(loandra_core STATIC ${SOURCES})
endif()
if(NOT HERMAX_CORE_ARCHIVE)
    target_compile_definitions(loandra_core PRIVATE
        __STDC_LIMIT_MACROS
        __STDC_FORMAT_MACROS
        SIMP
        NSPACE=Glucose
    )

    target_compile_options(loandra_core PRIVATE
        -include ${CMAKE_CURRENT_SOURCE_DIR}/cmake/ns_compat.h
    )
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

add_library(loandra MODULE python/loandra_bindings.cpp)
set_target_properties(loandra PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")
target_link_libraries(loandra PRIVATE Python3::Module loandra_core)

find_library(GMP_LIBRARY gmp)
find_library(GMPXX_LIBRARY gmpxx)
if(GMP_LIBRARY)
    target_link_libraries(loandra PRIVATE ${GMP_LIBRARY})
    if(GMPXX_LIBRARY)
        target_link_libraries(loandra PRIVATE ${GMPXX_LIBRARY})
    endif()
else()
    if(APPLE)
        if(EXISTS "/opt/homebrew/include")
            target_include_directories(loandra PRIVATE "/opt/homebrew/include")
        elseif(EXISTS "/usr/local/include")
            target_include_directories(loandra PRIVATE "/usr/local/include")
        endif()
    endif()
endif()

set_target_properties(loandra PROPERTIES
  PREFIX ""
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
  OUTPUT_NAME "loandra"
)
