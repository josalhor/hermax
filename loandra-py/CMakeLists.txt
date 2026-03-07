cmake_minimum_required(VERSION 3.15)
project(hermax.core.loandra LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(LOANDRA_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../Loandra/code")

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

pybind11_add_module(loandra MODULE NO_EXTRAS python/loandra_bindings.cpp ${SOURCES})
target_link_libraries(loandra PRIVATE Python3::Module pybind11::module)

add_definitions(-D __STDC_LIMIT_MACROS -D __STDC_FORMAT_MACROS -D SIMP)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DNSPACE=Glucose")

target_compile_options(loandra PRIVATE
    -include ${CMAKE_CURRENT_SOURCE_DIR}/cmake/ns_compat.h
)

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
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_LIBRARY_OUTPUT_DIRECTORY}"
  OUTPUT_NAME "loandra"
)
