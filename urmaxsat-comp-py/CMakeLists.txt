cmake_minimum_required(VERSION 3.15)
project(hermax_urmaxsat_comp_py LANGUAGES CXX)

# --------------------------------------------------------
# pybind11 + Python
# --------------------------------------------------------
find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)

find_package(pybind11 REQUIRED)

# --------------------------------------------------------
# Paths injected from setup.py
# --------------------------------------------------------
set(UWR_LIB_ABS   "" CACHE FILEPATH "Absolute path to prebuilt libuwrmaxsat.a")
set(COMINISATPS_A_ABS "" CACHE FILEPATH "Absolute path to prebuilt lib_release.a for cominisatps")

if (NOT EXISTS "${UWR_LIB_ABS}")
  message(FATAL_ERROR "UWR_LIB_ABS not set/does not exist (expected .a file)")
endif()
if (NOT EXISTS "${COMINISATPS_A_ABS}")
  message(FATAL_ERROR "COMINISATPS_A_ABS not set/does not exist")
endif()

# --------------------------------------------------------
# Build settings
# --------------------------------------------------------
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)  # needed for static->shared link

# --------------------------------------------------------
# Build pybind module
# --------------------------------------------------------
pybind11_add_module(urmaxsat_comp_py MODULE NO_EXTRAS python/urmaxsat_comp_bindings.cpp)
target_compile_features(urmaxsat_comp_py PRIVATE cxx_std_17)

# --------------------------------------------------------
# Link static libs directly (no runtime dependencies)
# --------------------------------------------------------
find_library(GMP_LIBRARY gmp REQUIRED)

target_link_libraries(urmaxsat_comp_py PRIVATE
  Python3::Module
  pybind11::module
  "${UWR_LIB_ABS}"
  "${COMINISATPS_A_ABS}"
  ${GMP_LIBRARY}
)

# --------------------------------------------------------
# Output
# --------------------------------------------------------
set_target_properties(urmaxsat_comp_py PROPERTIES
  PREFIX ""
  OUTPUT_NAME "urmaxsat_comp_py"
)
