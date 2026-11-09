cmake_minimum_required(VERSION 3.15)
project(hermax_urmaxsat_comp_py LANGUAGES CXX)

# --------------------------------------------------------
# Python C API module
# --------------------------------------------------------
find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)


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
# Build Python C API module
# --------------------------------------------------------
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '')"
  OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT PYTHON_EXTENSION_SUFFIX)
  message(FATAL_ERROR "Could not determine the Python extension suffix")
endif()

add_library(urmaxsat_comp_py MODULE python/urmaxsat_comp_bindings.cpp)
set_target_properties(urmaxsat_comp_py PROPERTIES SUFFIX "${PYTHON_EXTENSION_SUFFIX}")
target_compile_features(urmaxsat_comp_py PRIVATE cxx_std_17)

# --------------------------------------------------------
# Link static libs directly (no runtime dependencies)
# --------------------------------------------------------
find_library(GMP_LIBRARY gmp REQUIRED)

target_link_libraries(urmaxsat_comp_py PRIVATE
  Python3::Module
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
