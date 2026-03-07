BUILD_DIR=build
MAXPRE=
USESCIP=
BIGWEIGHTS=
MINISATP_REL=-fPIC -O2 -U_ISOC23_SOURCE -D_DEFAULT_SOURCE -D_GNU_SOURCE -std=gnu++17 -O3 -D NDEBUG -Wno-strict-aliasing -D COMINISATPS -U_ISOC23_SOURCE -D_DEFAULT_SOURCE -D_GNU_SOURCE
MINISATP_FPIC=-fPIC
MINISAT_INCLUDE=-I/home/jsh7/pymaxsat2/urmaxsat-comp-py/cominisatps -I/home/jsh7/pymaxsat2/urmaxsat-comp-py/cominisatps/minisat -I/home/jsh7/pymaxsat2/urmaxsat-comp-py/cadical/src
MINISAT_LIB=-L/home/jsh7/pymaxsat2/urmaxsat-comp-py/cominisatps/simp -l_release
