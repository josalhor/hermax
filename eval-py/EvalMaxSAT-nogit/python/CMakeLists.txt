cmake_minimum_required(VERSION 3.15)

project(hermax.core.eval_py LANGUAGES CXX)

pybind11_add_module(hermax.core.eval_py MODULE NO_EXTRAS evalmaxsat_bindings.cpp)
target_link_libraries(hermax.core.eval_py PRIVATE EvalMaxSAT)
set_target_properties(hermax.core.eval_py PROPERTIES OUTPUT_NAME "eval_py")

target_include_directories(hermax.core.eval_py PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../lib/EvalMaxSAT/src
    ${CMAKE_CURRENT_SOURCE_DIR}/../lib/cadical/src
    ${CMAKE_CURRENT_SOURCE_DIR}/../lib/glucose/src
    ${CMAKE_CURRENT_SOURCE_DIR}/../lib/MaLib/src
    ${CMAKE_CURRENT_BINARY_DIR}/_deps/pybind11-src/include # Explicitly add pybind11 include directory
)

# Removed install command, setup.py will handle installation
