# Minimal QNX 8.0 x86_64 toolchain file for the QNX Build Witness example.
# Source qnxsdp-env.sh before configuring, or pass absolute compiler paths.

set(CMAKE_SYSTEM_NAME QNX)
set(CMAKE_SYSTEM_PROCESSOR x86_64)

set(QNX_TARGET_ARCH "gcc_ntox86_64" CACHE STRING "QNX target architecture")
set(CMAKE_C_COMPILER qcc CACHE FILEPATH "QNX C compiler")
set(CMAKE_CXX_COMPILER q++ CACHE FILEPATH "QNX C++ compiler")

set(CMAKE_C_FLAGS_INIT "-V${QNX_TARGET_ARCH}")
set(CMAKE_CXX_FLAGS_INIT "-V${QNX_TARGET_ARCH}")

# Do not try to run cross-compiled test binaries on the host.
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

if(DEFINED ENV{QNX_TARGET})
  set(CMAKE_FIND_ROOT_PATH "$ENV{QNX_TARGET}")
endif()

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
