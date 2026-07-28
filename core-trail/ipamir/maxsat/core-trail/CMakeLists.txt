cmake_minimum_required(VERSION 3.15)
project(coretrail_native LANGUAGES CXX)

find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 REQUIRED)

pybind11_add_module(coretrail_native MODULE NO_EXTRAS
  src/python/module.cc
  src/core/coretrail_solver.cc
  src/core/glucose_backend.cc
  third_party/glucose-syrup-4.1/core/Solver.cc
  third_party/glucose-syrup-4.1/utils/Options.cc
  third_party/glucose-syrup-4.1/utils/System.cc)

target_compile_features(coretrail_native PRIVATE cxx_std_17)
target_compile_definitions(coretrail_native PRIVATE Glucose=RC2Glucose)
target_include_directories(coretrail_native PRIVATE
  include
  third_party/glucose-syrup-4.1
  third_party/cardenc)
target_link_libraries(coretrail_native PRIVATE Python3::Module pybind11::module)
set_target_properties(coretrail_native PROPERTIES PREFIX "" OUTPUT_NAME "coretrail_native")
