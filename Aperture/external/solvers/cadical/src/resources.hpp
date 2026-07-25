#ifndef _resources_hpp_INCLUDED
#define _resources_hpp_INCLUDED

#include <cstdint>

namespace ApertureCaDiCaL {

double absolute_real_time ();
double absolute_process_time ();

uint64_t maximum_resident_set_size ();
uint64_t current_resident_set_size ();

} // namespace ApertureCaDiCaL

#endif // ifndef _resources_hpp_INCLUDED
